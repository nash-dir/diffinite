"""파이프라인 오케스트레이터.

Collection → Parsing → Diff → Deep Compare → Report 전체 흐름을 조율하는
``run_pipeline()`` 함수를 제공한다. CLI에서 직접 호출.

실행 모드:
    - ``simple``: 1:1 파일 매칭 + diff + 보고서. Winnowing 미사용. 빠름.
    - ``deep``: 1:1 + N:M Winnowing 크로스매칭. 정밀.

보고서 형식:
    - ``--report-pdf``: 병합 PDF (북마크 + Bates 번호). 법정 제출용.
    - ``--report-html``: 독립형 HTML (자기 완결형 CSS/JS).
    - ``--report-md``: Markdown 요약 (CI/CD 통합용).

PDF 전략 (Divide-and-Conquer):
    대규모 파일 쌍에서 단일 PDF 변환 시 메모리 폭발을 방지하기 위해,
    파일별로 개별 PDF를 생성한 후 ``pypdf``로 병합한다.
    병합 시 파일별 북마크와 Bates 번호를 자동 추가.

의존:
    - ``collector.py``: 파일 수집 & 매칭
    - ``parser.py``: 주석 제거
    - ``differ.py``: Diff 계산 + HTML 생성
    - ``deep_compare.py``: N:M 크로스매칭
    - ``pdf_gen.py``: PDF 보고서 생성

호출관계:
    ``cli.main()`` → ``run_pipeline()``
    ``run_pipeline()`` → ``_generate_pdf/html/markdown_report()``
"""

from __future__ import annotations

import dataclasses
import datetime
import errno
import hashlib
import html as html_mod
import json
import logging
import math
import os
import platform
import re
import shutil
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from collections.abc import Sequence
from typing import Any, Callable, TypeVar

from diffinite import __version__
from diffinite.calibration import (
    assess_normalize_calibration,
    assess_normalize_metadata,
    resolve_threshold_deep,
    threshold_console_warning,
    threshold_disclosure,
)
from diffinite.collector import (
    FUZZY_THRESHOLD,
    SENSITIVE_MODES,
    SENSITIVE_PRESET_VERSION,
    CollectionPolicy,
    collect_files,
    match_files,
    sensitive_preset_rules,
)
from diffinite.notices import (
    CONTAINMENT_NOTE,
    INCONCLUSIVE_NOTICE,
    INTEGRITY_NOTICE,
    EXCLUDED_INPUTS_HEADING,
    analysis_status_rows,
    excluded_input_rows,
    exclusion_label,
    exclusion_reason,
    visible_controls,
    policy_config_rows,
    applicable_notices,
    item_reason_label,
    report_notice_texts,
    status_rows_as_lines,
)
from diffinite.deep_compare import exit_when_parent_dies, run_deep_compare
from diffinite.differ import compute_diff, generate_html_diff, read_file
from diffinite.evidence import (
    _logical_report_paths,
    _path_is_redirect,
    _sha256_file,
    _safe_relative_parts,
    compute_file_hashes,
    create_immutable_snapshot,
    create_evidence_bundle,
    SourceIntegrityError,
    verify_snapshot_matches_manifest,
    verify_sources_unchanged,
    write_manifest,
)
from diffinite.fingerprint import DEFAULT_K, DEFAULT_W, pygments_version
from diffinite.models import (
    AnalysisMetadata,
    AnalysisStatus,
    DeepMatchResult,
    DiffResult,
    FileHashEntry,
    count_label,
    deep_compare_comment_mode,
    hash_only_label,
    line_diff_comment_mode,
    line_match_label,
    name_similarity_label,
    overlap_label,
    size_label,
    threshold_label,
    threshold_source_label,
    truncation_note_text,
)
from diffinite.parser import (
    comment_extensions_for_pair,
    extensions_without_comment_rules,
)
from diffinite.parser import strip_comments as _strip_comments_fn
from diffinite.pdf_gen import (
    _build_annotation_html,
    _html_wrap,
    add_bates_numbers,
    build_cover_body,
    build_diff_page_html,
    build_hash_table_html,
    html_to_pdf,
    merge_with_bookmarks,
    pdf_conventions,
    signed_count,
    stamp_bates_inplace,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _tree_contains_redirect(root: Path) -> bool:
    """Inspect a tree without descending through a redirecting entry."""
    if _path_is_redirect(root):
        return True
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        parent = Path(dirpath)
        if any(_path_is_redirect(parent / name) for name in (*dirnames, *filenames)):
            return True
    return False


@dataclasses.dataclass(frozen=True)
class _OutputTarget:
    """One preflighted output and the filesystem kind it is allowed to have."""

    label: str
    path: Path
    is_directory: bool


@dataclasses.dataclass(frozen=True)
class _OutputRecord:
    target: _OutputTarget
    backup: Path | None


def _validate_live_output_target(target_spec: _OutputTarget) -> None:
    """Revalidate one output immediately before a filesystem mutation."""
    target = target_spec.path
    _reject_redirecting_components(target, label=target_spec.label)
    if not target.exists():
        if _path_is_redirect(target):
            raise SourceIntegrityError(f"Refusing output through symlink or junction: {target}")
        return
    if _path_is_redirect(target):
        raise SourceIntegrityError(f"Refusing output through symlink or junction: {target}")
    if target_spec.is_directory:
        if not target.is_dir():
            raise SourceIntegrityError(
                f"Expected output directory for {target_spec.label}: {target}"
            )
        if _tree_contains_redirect(target):
            raise SourceIntegrityError(
                f"Refusing output tree containing a symlink or junction: {target}"
            )
        return
    if not target.is_file():
        raise SourceIntegrityError(
            f"Expected regular output file for {target_spec.label}: {target}"
        )
    # POSIX/Windows st_nlink is the number of directory entries for the same
    # file record. Writing an existing multi-link output could mutate evidence
    # or a policy input through another name, so it is never an output target.
    if target.stat().st_nlink > 1:
        raise SourceIntegrityError(f"Refusing hard-linked output for {target_spec.label}: {target}")


class _OutputTransaction:
    """Restore the prior evidence set when an ordinary output step fails.

    Multiple paths cannot be replaced atomically by a portable filesystem API.
    This rollback guard nevertheless prevents handled rendering/publication
    failures from leaving a new report beside an old manifest or bundle.
    """

    def __init__(
        self,
        targets: list[_OutputTarget],
        *,
        cleanup: Callable[[], None] | None = None,
    ) -> None:
        self._backup_root = Path(tempfile.mkdtemp(prefix="diffinite_output_backup_"))
        self._recovery_path: Path | None = self._backup_root
        self._records: list[_OutputRecord] = []
        self._cleanup = cleanup
        self._cleanup_done = False
        self._active = True
        try:
            for index, target_spec in enumerate(
                sorted(targets, key=lambda item: item.path.as_posix())
            ):
                target = target_spec.path
                backup: Path | None = None
                _validate_live_output_target(target_spec)
                if target.exists():
                    backup = self._backup_root / str(index)
                    if target_spec.is_directory:
                        shutil.copytree(target, backup)
                    else:
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, backup)
                self._records.append(_OutputRecord(target_spec, backup))
        except BaseException as operation_error:
            shutil.rmtree(self._backup_root, ignore_errors=True)
            self._recovery_path = None
            self._active = False
            try:
                self._cleanup_resources()
            except BaseException as cleanup_error:
                raise cleanup_error from operation_error
            raise

    @property
    def recovery_path(self) -> Path | None:
        """Location of retained originals after an incomplete rollback."""
        return self._recovery_path

    def _cleanup_resources(self) -> None:
        """Release analysis resources exactly once before success or rollback."""
        if self._cleanup_done:
            return
        if self._cleanup is not None:
            self._cleanup()
        self._cleanup_done = True

    def run(
        self,
        operation: Callable[..., _T],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """Run one output mutation and roll the whole set back on failure."""
        try:
            for record in self._records:
                _validate_live_output_target(record.target)
            return operation(*args, **kwargs)
        except BaseException as operation_error:
            try:
                self.rollback()
            except BaseException as rollback_error:
                raise rollback_error from operation_error
            raise

    def rollback(self) -> None:
        if not self._active:
            return
        rollback_errors: list[str] = []
        for record in sorted(
            self._records,
            key=lambda item: len(item.target.path.parts),
            reverse=True,
        ):
            target = record.target.path
            try:
                if not target.exists() and not _path_is_redirect(target):
                    continue
                if _path_is_redirect(target):
                    raise SourceIntegrityError("path became a symlink or junction")
                if record.target.is_directory:
                    if not target.is_dir():
                        raise SourceIntegrityError("path is no longer a directory")
                    if _tree_contains_redirect(target):
                        raise SourceIntegrityError("directory now contains a symlink or junction")
                    shutil.rmtree(target)
                else:
                    if not target.is_file():
                        raise SourceIntegrityError("path is no longer a regular file")
                    target.unlink()
            except Exception as exc:
                rollback_errors.append(f"cannot clear {target}: {exc}")

        for record in self._records:
            target = record.target.path
            backup = record.backup
            if backup is None:
                continue
            try:
                if target.exists() or _path_is_redirect(target):
                    raise SourceIntegrityError("replacement path is still occupied")
                target.parent.mkdir(parents=True, exist_ok=True)
                if record.target.is_directory:
                    shutil.copytree(backup, target)
                else:
                    shutil.copy2(backup, target)
            except Exception as exc:
                rollback_errors.append(f"cannot restore {target}: {exc}")

        try:
            self._cleanup_resources()
        except Exception as exc:
            rollback_errors.append(f"cannot clean analysis snapshot: {exc}")

        self._active = False
        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise SourceIntegrityError(
                "Output rollback was incomplete; recovery backup retained at "
                f"{self._backup_root}: {details}"
            )

        try:
            shutil.rmtree(self._backup_root)
            self._recovery_path = None
        except OSError as exc:
            logger.warning(
                "Rollback succeeded but recovery backup cleanup failed at %s: %s",
                self._backup_root,
                exc,
            )

    def commit(self) -> None:
        if self._active:
            try:
                self._cleanup_resources()
            except BaseException as operation_error:
                try:
                    self.rollback()
                except BaseException as rollback_error:
                    raise rollback_error from operation_error
                raise
            self._active = False
            try:
                shutil.rmtree(self._backup_root)
                self._recovery_path = None
            except OSError as exc:
                logger.warning(
                    "Could not remove completed output backup %s: %s",
                    self._backup_root,
                    exc,
                )


def _collect_report_artifacts(
    report_pdf: str | None,
    report_html: str | None,
    report_md: str | None,
    report_json: str | None,
    *,
    results: list[DiffResult],
    preserve_tree: bool,
    no_merge: bool,
    metrics_only: bool,
    separate_uncompared_path: str | None,
    current_unreadable_log: str | None,
) -> list[str]:
    """Return exactly the artifacts this run was required to generate.

    Split trees are compared with the deterministic expected filename set.
    Scanning a live tree and trusting every matching file could admit a stale or
    concurrently injected artifact into the manifest and evidence bundle.
    """
    artifacts: set[Path] = set()
    generated_paths: list[str | None] = [report_json]
    if not metrics_only:
        generated_paths.append(report_md)
        if not no_merge:
            generated_paths.extend((report_pdf, report_html))
    primary_paths = [Path(path) for path in generated_paths if path]
    for path in primary_paths:
        artifacts.add(path)
        if path in {Path(p) for p in (report_pdf, report_html) if p}:
            for suffix in (".sha256", ".sig"):
                artifacts.add(Path(f"{path}{suffix}"))

    if report_pdf and not metrics_only and not no_merge:
        artifacts.add(Path(report_pdf).with_suffix(".csv"))

    if no_merge and not metrics_only:
        expected_split_trees: dict[Path, set[Path]] = {}
        for anchor, artifact_suffix in (
            (report_pdf, ".pdf"),
            (report_html, ".html"),
        ):
            if not anchor:
                continue
            path = Path(anchor)
            output_tree = path.parent / f"{path.stem}_files"
            expected = expected_split_trees.setdefault(output_tree, set())
            expected.add(
                output_tree / ("000_cover.pdf" if artifact_suffix == ".pdf" else "index.html")
            )
            for index, result in enumerate(results, 1):
                if preserve_tree:
                    rel = PurePosixPath(result.match.rel_path_a)
                    entry = output_tree / "entries" / str(rel).replace("/", os.sep)
                    expected.add(Path(f"{entry}{artifact_suffix}"))
                else:
                    safe_name = Path(result.match.rel_path_a).name.replace(" ", "_")
                    expected.add(output_tree / f"{index:03d}_{safe_name}{artifact_suffix}")

        for output_tree, expected in expected_split_trees.items():
            actual = (
                {item for item in output_tree.rglob("*") if item.is_file()}
                if output_tree.is_dir()
                else set()
            )
            if actual != expected:
                missing = sorted(
                    item.relative_to(output_tree).as_posix() for item in expected - actual
                )
                unexpected = sorted(
                    item.relative_to(output_tree).as_posix() for item in actual - expected
                )
                raise SourceIntegrityError(
                    f"Split-report artifact set mismatch for {output_tree}: "
                    f"missing={missing}, unexpected={unexpected}"
                )
            artifacts.update(expected)

    if separate_uncompared_path:
        artifacts.add(Path(separate_uncompared_path))
    if current_unreadable_log:
        artifacts.add(Path(current_unreadable_log))

    return [str(path) for path in sorted(artifacts, key=lambda item: item.as_posix())]


def _resolved(path: str | Path) -> Path:
    """Resolve a prospective path without requiring it to exist."""
    return Path(path).expanduser().resolve(strict=False)


def _lexical_absolute(path: str | Path) -> Path:
    """Return an absolute path without dereferencing filesystem redirects."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _reject_redirecting_components(path: Path, *, label: str) -> None:
    """Reject an output whose existing lexical path crosses a redirect."""
    absolute = _lexical_absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if _path_is_redirect(current):
            raise SourceIntegrityError(f"Unsafe {label} path uses a symlink or junction: {current}")


def _paths_overlap(first: Path, second: Path) -> bool:
    """Return whether either resolved path contains the other."""
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def _validate_output_boundaries(
    dir_a: str,
    dir_b: str,
    *,
    report_pdf: str | None,
    report_html: str | None,
    report_md: str | None,
    report_json: str | None,
    manifest_path: str,
    bundle_path: str | None,
    unreadable_log: str | None,
    ignore_file: str | None,
    filter_json: str | None,
    pdf_font: str | None,
    no_merge: bool,
    metrics_only: bool,
    show_bates_number: bool,
    uncompared_mode: str,
) -> list[_OutputTarget]:
    """Reject output graphs that can mutate inputs or collide with each other.

    This must run before collection because a report created below a source root
    would both overwrite evidence bytes and change the set being analyzed.
    """
    source_roots: list[tuple[Path, Path]] = []
    for label, source in (("source A", dir_a), ("source B", dir_b)):
        lexical_source = _lexical_absolute(source)
        try:
            resolved_source = lexical_source.resolve(strict=True)
        except OSError as exc:
            raise SourceIntegrityError(f"Cannot resolve {label} root: {exc}") from exc
        if not resolved_source.is_dir():
            raise SourceIntegrityError(f"{label} root is not a directory: {source}")
        source_roots.append((lexical_source, resolved_source))

    file_outputs: list[tuple[str, Path]] = [("manifest", _lexical_absolute(manifest_path))]
    split_outputs: list[tuple[str, Path]] = []

    if report_json:
        file_outputs.append(("JSON report", _lexical_absolute(report_json)))
    if not metrics_only:
        if report_md:
            file_outputs.append(("Markdown report", _lexical_absolute(report_md)))
        if report_html:
            html_path = _lexical_absolute(report_html)
            if no_merge:
                split_outputs.append(
                    ("HTML split-report directory", html_path.parent / f"{html_path.stem}_files")
                )
                file_outputs.extend(
                    (
                        ("obsolete merged HTML anchor", html_path),
                        (
                            "obsolete merged HTML checksum",
                            _lexical_absolute(f"{report_html}.sha256"),
                        ),
                        (
                            "obsolete merged HTML compatibility checksum",
                            _lexical_absolute(f"{report_html}.sig"),
                        ),
                    )
                )
            else:
                file_outputs.extend(
                    (
                        ("HTML report", html_path),
                        ("HTML checksum", _lexical_absolute(f"{report_html}.sha256")),
                        (
                            "HTML compatibility checksum",
                            _lexical_absolute(f"{report_html}.sig"),
                        ),
                    )
                )
        if report_pdf:
            pdf_path = _lexical_absolute(report_pdf)
            if no_merge:
                split_outputs.append(
                    ("PDF split-report directory", pdf_path.parent / f"{pdf_path.stem}_files")
                )
                file_outputs.extend(
                    (
                        ("obsolete merged PDF anchor", pdf_path),
                        ("obsolete merged PDF exhibit index", pdf_path.with_suffix(".csv")),
                        (
                            "obsolete merged PDF checksum",
                            _lexical_absolute(f"{report_pdf}.sha256"),
                        ),
                        (
                            "obsolete merged PDF compatibility checksum",
                            _lexical_absolute(f"{report_pdf}.sig"),
                        ),
                    )
                )
            else:
                file_outputs.extend(
                    (
                        ("PDF report", pdf_path),
                        ("PDF exhibit index", pdf_path.with_suffix(".csv")),
                        ("PDF checksum", _lexical_absolute(f"{report_pdf}.sha256")),
                        (
                            "PDF compatibility checksum",
                            _lexical_absolute(f"{report_pdf}.sig"),
                        ),
                    )
                )
                if show_bates_number:
                    file_outputs.append(
                        (
                            "PDF Bates staging file",
                            pdf_path.with_name(f"{pdf_path.stem}.bates_tmp.pdf"),
                        )
                    )

    if bundle_path:
        file_outputs.extend(
            (
                ("evidence bundle", _lexical_absolute(bundle_path)),
                (
                    "evidence bundle checksum",
                    _lexical_absolute(f"{bundle_path}.sha256"),
                ),
            )
        )
    if unreadable_log:
        file_outputs.append(("unreadable-file log", _lexical_absolute(unreadable_log)))
    if uncompared_mode == "separate":
        first_report = next(
            (path for path in (report_pdf, report_html, report_md, report_json) if path),
            "report",
        )
        first_path = _lexical_absolute(first_report)
        file_outputs.append(
            (
                "uncompared-file list",
                first_path.with_name(f"{first_path.stem}_uncompared.txt"),
            )
        )

    candidates: list[tuple[_OutputTarget, Path]] = []
    for label, output in file_outputs:
        _reject_redirecting_components(output, label=label)
        resolved_output = output.resolve(strict=False)
        if output.exists() and not output.is_file():
            raise SourceIntegrityError(
                f"Unsafe output for {label}: expected a regular file, found a directory "
                f"or special entry at {output}"
            )
        if output.is_file() and output.stat().st_nlink > 1:
            raise SourceIntegrityError(f"Unsafe hard-linked output for {label}: {output}")
        candidates.append((_OutputTarget(label, output, False), resolved_output))
    for label, output_dir in split_outputs:
        _reject_redirecting_components(output_dir, label=label)
        resolved_output = output_dir.resolve(strict=False)
        if output_dir.exists() and not output_dir.is_dir():
            raise SourceIntegrityError(
                f"Unsafe output for {label}: expected a directory at {output_dir}"
            )
        candidates.append((_OutputTarget(label, output_dir, True), resolved_output))

    for target_spec, resolved_output in candidates:
        for lexical_root, resolved_root in source_roots:
            if _paths_overlap(target_spec.path, lexical_root) or _paths_overlap(
                resolved_output, resolved_root
            ):
                raise SourceIntegrityError(
                    f"Unsafe output path for {target_spec.label}: {target_spec.path} "
                    "overlaps a source input root"
                )

    read_inputs = [
        (label, _lexical_absolute(path))
        for label, path in (
            ("ignore file", ignore_file),
            ("filter JSON", filter_json),
            ("PDF font", pdf_font),
        )
        if path
    ]
    for target_spec, resolved_output in candidates:
        for input_label, input_path in read_inputs:
            resolved_input = input_path.resolve(strict=False)
            if _paths_overlap(target_spec.path, input_path) or _paths_overlap(
                resolved_output, resolved_input
            ):
                raise SourceIntegrityError(
                    f"Unsafe output collision: {target_spec.label} overlaps {input_label}"
                )

    unique_candidates: list[tuple[_OutputTarget, Path]] = []
    for candidate, resolved_candidate in candidates:
        duplicate_index = next(
            (
                index
                for index, (prior, prior_resolved) in enumerate(unique_candidates)
                if candidate.path == prior.path or resolved_candidate == prior_resolved
            ),
            None,
        )
        if duplicate_index is None:
            unique_candidates.append((candidate, resolved_candidate))
            continue
        prior, _prior_resolved = unique_candidates[duplicate_index]
        if candidate.is_directory and prior.is_directory:
            unique_candidates[duplicate_index] = (
                _OutputTarget(
                    f"{prior.label} / {candidate.label}",
                    prior.path,
                    True,
                ),
                resolved_candidate,
            )
            continue
        raise SourceIntegrityError(
            f"Unsafe output collision: {candidate.label} and {prior.label} "
            f"resolve to {candidate.path}"
        )

    for index, (first, first_resolved) in enumerate(unique_candidates):
        for second, second_resolved in unique_candidates[index + 1 :]:
            if _paths_overlap(first.path, second.path) or _paths_overlap(
                first_resolved, second_resolved
            ):
                raise SourceIntegrityError(
                    f"Unsafe output ancestor collision: {first.label} at {first.path} "
                    f"overlaps {second.label} at {second.path}"
                )
    return [
        candidate
        for candidate, _resolved_candidate in sorted(
            unique_candidates,
            key=lambda item: item[0].path.as_posix(),
        )
    ]


def _display_label(alias: str | None, directory: str) -> str:
    """Report label for an input root: the alias, else the folder name.

    A drive or UNC share root has an empty ``.name``; fall back to the
    resolved root itself (e.g. ``Z:\\``) so the label is never empty.
    """
    if alias:
        return alias
    resolved = Path(directory).resolve()
    return resolved.name or str(resolved)


def _reject_unencodable_names(label: str, names: Any) -> None:
    """Refuse names that cannot be written as UTF-8 (lone UTF-16 surrogates).

    NTFS allows such names and Python surfaces them as lone surrogates. Every
    report writer encodes strict UTF-8, so the run would otherwise crash after
    the full analysis without naming the file. Evidence names must not be
    altered, so they are rejected here instead of being replaced.
    """
    for name in sorted(names):
        try:
            name.encode("utf-8")
        except UnicodeEncodeError:
            raise RuntimeError(
                f"Cannot report {label} {ascii(name)}: the name contains a lone "
                "UTF-16 surrogate and cannot be written as UTF-8. Rename the file "
                "(or exclude it with an ignore pattern) and re-run."
            ) from None


def _disclosable_name(name: str) -> str:
    """An excluded input's name as reports can write it.

    An excluded file is not evidence, so a name that is not valid UTF-8 (a lone
    UTF-16 surrogate on NTFS) is disclosed with the surrogate written as a
    ``\\udXXX`` escape instead of refusing the run.
    """
    return name.encode("utf-8", "backslashreplace").decode("utf-8")


def _collection_failure(side: str, root: str, raw_path: str) -> dict[str, str]:
    """Convert collector diagnostics to a stable, root-relative disclosure."""
    path_text = raw_path
    reason = "unreadable or skipped during collection"
    marker = " (skipped: "
    if marker in path_text and path_text.endswith(")"):
        path_text, detail = path_text.rsplit(marker, 1)
        reason = f"skipped: {detail[:-1]}"

    root_path = _resolved(root)
    candidate = Path(path_text)
    if candidate.is_absolute():
        resolved_candidate = candidate.resolve(strict=False)
        try:
            relative = resolved_candidate.relative_to(root_path).as_posix()
        except ValueError:
            relative = resolved_candidate.name
    else:
        logical = PurePosixPath(path_text.replace("\\", "/"))
        relative = logical.as_posix()
        if logical.is_absolute() or any(part in {".", ".."} for part in logical.parts):
            relative = logical.name
    return {"side": side, "path": relative, "reason": reason}


def _format_collection_failures(failures: list[dict[str, str]]) -> list[str]:
    return [f"{item['side']}:{item['path']} ({item['reason']})" for item in failures]


def _verify_source_state(
    side: str,
    root: str,
    expected_files: list[str],
    expected_hashes: list[FileHashEntry],
    expected_collection_failures: list[dict[str, str]],
    policy: CollectionPolicy,
    expected_excluded: list[dict[str, str]] | None = None,
) -> list[str]:
    """Describe source-set or byte changes using privacy-safe relative paths."""
    current_errors: list[str] = []
    current_excluded: list[dict[str, str]] = []
    current_files = collect_files(
        root, unreadable_list=current_errors, policy=policy, excluded_list=current_excluded
    )
    current_failures = [_collection_failure(side, root, item) for item in current_errors]

    changes = [f"{side}:added:{path}" for path in sorted(set(current_files) - set(expected_files))]
    changes.extend(
        f"{side}:removed:{path}" for path in sorted(set(expected_files) - set(current_files))
    )
    changes.extend(
        f"{side}:modified:{path}" for path in verify_sources_unchanged(root, expected_hashes)
    )

    expected_diagnostics = {
        (item["path"], item["reason"])
        for item in expected_collection_failures
        if item["side"] == side
    }
    current_diagnostics = {(item["path"], item["reason"]) for item in current_failures}
    changes.extend(
        f"{side}:new-collection-failure:{path} ({reason})"
        for path, reason in sorted(current_diagnostics - expected_diagnostics)
    )
    changes.extend(
        f"{side}:resolved-collection-failure:{path} ({reason})"
        for path, reason in sorted(expected_diagnostics - current_diagnostics)
    )
    if expected_excluded is not None:
        # The disclosed exclusion list must still describe the inputs.
        def _key(item: dict[str, str]) -> tuple[str, str, str]:
            return (_disclosable_name(item["path"]), item["kind"], item["rule"])

        before = {_key(item) for item in expected_excluded if item.get("side", side) == side}
        after = {_key(item) for item in current_excluded}
        changes.extend(f"{side}:newly-excluded:{key[0]}" for key in sorted(after - before))
        changes.extend(f"{side}:no-longer-excluded:{key[0]}" for key in sorted(before - after))
    return changes


def _is_generated_split_artifact(relative: PurePosixPath) -> bool:
    """Recognize paths that a released split-report generator can create."""
    if relative.as_posix() in {"index.html", "000_cover.pdf"}:
        return True
    if relative.parts and relative.parts[0] == "entries":
        return relative.suffix.lower() in {".html", ".pdf"}
    # Flat generators use ``idx:03d``; indices naturally grow beyond three
    # digits after the 999th pair, so accept three or more leading digits.
    return bool(re.fullmatch(r"[0-9]{3,}_.+\.(?:html|pdf)", relative.as_posix()))


def _verify_replaceable_split_tree(output_dir: Path, prior_manifest: Path) -> None:
    """Refuse to delete a tree unless its files are verified prior artifacts."""
    entries = list(output_dir.rglob("*"))
    if not entries:
        return
    unsupported = sorted(
        path.relative_to(output_dir).as_posix()
        for path in entries
        if not path.is_file() and not path.is_dir()
    )
    if unsupported:
        raise SourceIntegrityError(
            f"Refusing to replace split-report tree containing special entries: {unsupported}"
        )
    files = {path for path in entries if path.is_file()}
    relative_files = {PurePosixPath(path.relative_to(output_dir).as_posix()) for path in files}
    unknown = sorted(
        path.as_posix() for path in relative_files if not _is_generated_split_artifact(path)
    )
    if unknown:
        raise SourceIntegrityError(
            f"Refusing to replace split-report tree containing unknown files: {unknown}"
        )

    allowed_directories: set[Path] = set()
    for file_path in files:
        parent = file_path.parent
        while parent != output_dir:
            allowed_directories.add(parent)
            parent = parent.parent
    unknown_directories = sorted(
        path.relative_to(output_dir).as_posix()
        for path in entries
        if path.is_dir() and path not in allowed_directories
    )
    if unknown_directories:
        raise SourceIntegrityError(
            "Refusing to replace split-report tree containing unowned directories: "
            f"{unknown_directories}"
        )

    _reject_redirecting_components(prior_manifest, label="prior split-report manifest")
    if (
        not prior_manifest.is_file()
        or _path_is_redirect(prior_manifest)
        or prior_manifest.stat().st_nlink > 1
    ):
        raise SourceIntegrityError(
            "Refusing to replace a non-empty split-report tree without a safe prior manifest"
        )
    try:
        manifest = json.loads(prior_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceIntegrityError(
            "Refusing to replace a split-report tree with an unreadable prior manifest"
        ) from exc
    report_entries = manifest.get("reports") if isinstance(manifest, dict) else None
    if not isinstance(report_entries, list):
        raise SourceIntegrityError(
            "Refusing to replace a split-report tree with an invalid prior manifest"
        )

    prefix = f"{output_dir.name}/"
    expected: dict[str, str] = {}
    for entry in report_entries:
        if not isinstance(entry, dict):
            continue
        logical = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(logical, str) or not logical.startswith(prefix):
            continue
        if not isinstance(digest, str) or logical in expected:
            raise SourceIntegrityError(
                "Refusing to replace a split-report tree with ambiguous prior hashes"
            )
        expected[logical] = digest

    actual_logical = {f"{output_dir.name}/{path.as_posix()}" for path in relative_files}
    if actual_logical != set(expected):
        raise SourceIntegrityError(
            "Refusing to replace a split-report tree not exactly covered by its prior manifest"
        )
    for file_path in files:
        logical = f"{output_dir.name}/{file_path.relative_to(output_dir).as_posix()}"
        if _sha256_file(file_path) != expected[logical]:
            raise SourceIntegrityError(
                f"Refusing to replace a modified prior split-report artifact: {logical}"
            )


def _prepare_split_output_tree(output_dir: Path, prior_manifest: Path) -> None:
    """Start a split report only after proving the old tree is tool-owned."""
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return
    if not output_dir.is_dir() or output_dir.is_symlink():
        raise RuntimeError(f"Refusing unsafe split-report output: {output_dir}")

    if _tree_contains_redirect(output_dir):
        raise RuntimeError(f"Refusing split-report tree containing symlinks: {output_dir}")
    _verify_replaceable_split_tree(output_dir, prior_manifest)
    shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


# Shared with deep_compare's pool so every worker pool watches its parent.
_exit_when_parent_dies = exit_when_parent_dies


def _can_open(path: str) -> bool:
    """True when the file can be opened for reading."""
    try:
        open(path, "rb").close()
    except OSError:
        return False
    return True


def _read_error_text(exc: BaseException) -> str:
    """Per-pair error text for a file that could not be read (not a decode failure)."""
    if isinstance(exc, PermissionError):
        return "Access Denied (PermissionError)"
    # errno name rather than strerror: strerror is localized and would make
    # the report text differ between machines.
    errno_name = errno.errorcode.get(getattr(exc, "errno", None) or -1)
    return f"Read error ({type(exc).__name__}{': ' + errno_name if errno_name else ''})"


def _process_match_chunk(
    worker_id: int,
    chunk: list,
    dir_a: str,
    dir_b: str,
    encoding: str | None,
    binary_handling: str,
    strip_comments: bool,
    squash_blanks: bool,
    by_word: bool,
    autojunk: bool,
    metrics_only: bool,
    collapse_identical: bool,
    detect_moved: bool,
    max_file_size_mb: float = 10.0,
    normalize_ws: bool = False,
    max_diff_html_size_mb: float = 2.0,
) -> tuple[list[DiffResult], list[int], list[str], list[dict[str, str]]]:
    """Diff one chunk of matched pairs.

    Returns ``(results, line_counts, unreadable, excluded)``. ``excluded`` lists
    the pairs that ``--binary-handling exclude`` left uncompared, as
    ``{"file_a", "file_b", "reason"}`` dicts, so the caller can disclose them.
    A pair whose file could not be read is never excluded: it always yields an
    error result, whatever the binary-handling policy.
    ``worker_id`` is kept for call compatibility; nothing is printed per worker.
    """
    results = []
    line_counts = []
    unreadable = []
    excluded: list[dict[str, str]] = []
    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()

    # No per-worker progress is written to stdout: the pipeline's "Step" log
    # lines on stderr are the progress signal (the extension shows those).
    for m in chunk:
        abs_a = str(root_a / m.rel_path_a)
        abs_b = str(root_b / m.rel_path_b)
        # Each file is stripped with its own language's comment rules — the same
        # rule the Deep Compare channel applies — so a cross-extension pair
        # (e.g. .py vs .js) is not parsed with the other file's grammar.
        # A side whose extension has no comment rules (Foo.java vs
        # Foo.java.orig) borrows its partner's rules; Deep Compare receives the
        # same pairs (``comment_pairs``) and applies the same helper.
        ext_a, ext_b = comment_extensions_for_pair(
            Path(m.rel_path_a).suffix.lower(), Path(m.rel_path_b).suffix.lower()
        )

        max_bytes = int(max_file_size_mb * 1024 * 1024)
        size_a = os.path.getsize(abs_a) if os.path.exists(abs_a) else 0
        size_b = os.path.getsize(abs_b) if os.path.exists(abs_b) else 0

        if size_a > max_bytes or size_b > max_bytes:
            try:
                hash_match = _sha256_file(abs_a) == _sha256_file(abs_b)
                results.append(
                    DiffResult(
                        match=m,
                        ratio=1.0 if hash_match else 0.0,
                        additions=0,
                        deletions=0,
                        html_diff="",
                        binary=True,
                        hash_match=hash_match,
                        hash_only_reason="max-file-size-exceeded",
                    )
                )
            except OSError as exc:
                failed = [p for p in (abs_a, abs_b) if not _can_open(p)]
                unreadable.extend(failed or [abs_a, abs_b])
                results.append(
                    DiffResult(
                        match=m,
                        ratio=0.0,
                        additions=0,
                        deletions=0,
                        html_diff="",
                        error=_read_error_text(exc),
                    )
                )
            continue

        # Read both sides. A side that cannot be opened (permission or any
        # other OSError) is a read failure; a side that opens but returns None
        # could not be decoded as text.
        read_errors: list[BaseException] = []
        texts: list[str | None] = []
        for abs_path in (abs_a, abs_b):
            try:
                text = read_file(abs_path, encoding=encoding)
            except PermissionError as exc:
                unreadable.append(abs_path)
                read_errors.append(exc)
                text = None
            else:
                if text is None:
                    try:
                        open(abs_path, "rb").close()
                    except OSError as exc:
                        unreadable.append(abs_path)
                        read_errors.append(exc)
            texts.append(text)
        text_a, text_b = texts

        if read_errors:
            # Never excluded and never labelled as a decode failure.
            results.append(
                DiffResult(
                    match=m,
                    ratio=0.0,
                    additions=0,
                    deletions=0,
                    html_diff="",
                    error=_read_error_text(read_errors[0]),
                )
            )
            continue

        if text_a is None or text_b is None:
            if binary_handling == "exclude":
                excluded.append(
                    {
                        "file_a": m.rel_path_a,
                        "file_b": m.rel_path_b,
                        "reason": "binary or not decodable as text",
                    }
                )
            elif binary_handling == "hash":
                try:
                    hash_match = _sha256_file(abs_a) == _sha256_file(abs_b)
                    results.append(
                        DiffResult(
                            match=m,
                            ratio=1.0 if hash_match else 0.0,
                            additions=0,
                            deletions=0,
                            html_diff="",
                            binary=True,
                            hash_match=hash_match,
                            hash_only_reason="not-decodable",
                        )
                    )
                except OSError as exc:
                    unreadable.extend(p for p in (abs_a, abs_b) if not _can_open(p))
                    results.append(
                        DiffResult(
                            match=m,
                            ratio=0.0,
                            additions=0,
                            deletions=0,
                            html_diff="",
                            error=_read_error_text(exc),
                        )
                    )
            else:
                results.append(
                    DiffResult(
                        match=m,
                        ratio=0.0,
                        additions=0,
                        deletions=0,
                        html_diff="",
                        error="Could not decode one or both files",
                    )
                )
            continue

        if strip_comments:
            text_a = _strip_comments_fn(text_a, ext_a, squash_blanks=squash_blanks)
            text_b = _strip_comments_fn(text_b, ext_b, squash_blanks=squash_blanks)

        line_counts.append(text_a.count("\n") + 1)
        line_counts.append(text_b.count("\n") + 1)
        ratio, additions, deletions = compute_diff(
            text_a, text_b, by_word, autojunk=autojunk, normalize_ws=normalize_ws
        )

        html_diff = ""
        if not metrics_only:
            local_max = max(line_counts[-2:])
            local_width = max(28, len(str(local_max)) * 7 + 10)
            html_diff = generate_html_diff(
                text_a,
                text_b,
                label_a=m.rel_path_a,
                label_b=m.rel_path_b,
                filename_a=m.rel_path_a,
                filename_b=m.rel_path_b,
                context_lines=3 if collapse_identical else -1,
                ln_col_width=local_width,
                autojunk=autojunk,
                by_word=by_word,
                detect_moved=detect_moved,
                normalize_ws=normalize_ws,
            )

            # M4: xhtml2pdf DOM parsing scale limit. 2MB HTML ≈ 100K nodes.
            # html5lib is pure Python; beyond this recursion limit/OOM crashes.
            max_diff_bytes = int(max_diff_html_size_mb * 1024 * 1024)
            original_diff_bytes = len(html_diff.encode("utf-8", errors="replace"))
            truncated = original_diff_bytes > max_diff_bytes
            if truncated:
                html_diff = (
                    '<p class="note">'
                    f"{html_mod.escape(truncation_note_text(original_diff_bytes, max_diff_html_size_mb))}"
                    "</p>"
                )

        results.append(
            DiffResult(
                match=m,
                ratio=ratio,
                additions=additions,
                deletions=deletions,
                html_diff=html_diff,
                html_diff_truncated=truncated if not metrics_only else False,
                html_diff_truncation_reason=(
                    "max-diff-html-size" if not metrics_only and truncated else None
                ),
                html_diff_original_bytes=(
                    original_diff_bytes if not metrics_only and truncated else None
                ),
                # No original diff fragment is retained after replacement.
                html_diff_omitted_bytes=(
                    original_diff_bytes if not metrics_only and truncated else None
                ),
            )
        )

    return results, line_counts, unreadable, excluded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _compute_ln_col_width(line_counts: list[int]) -> int:
    """Compute a unified line-number column width for all diff pages."""
    max_ln = max(line_counts) if line_counts else 1
    digits = len(str(max_ln))
    return max(28, digits * 7 + 10)


# Natural sort: '1. foo' < '2. foo' < '10. foo'
# Splits a string into alternating (text, int) segments so that
# numeric substrings are compared by integer value, not lexicographically.
_RE_NATURAL = re.compile(r"(\d+)")


def _natural_sort_key(s: str) -> list:
    """Natural sort key: compare numeric segments as integers.

    '1. Handler.java' → ['', 1, '. handler.java']
    '10. Bundle.java' → ['', 10, '. bundle.java']
    → 1 < 10, so '1. Handler' sorts before '10. Bundle'.
    """
    parts = _RE_NATURAL.split(s.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def _analysis_status_summary(status: AnalysisStatus) -> list[str]:
    """Completeness details as "Label: value" lines (after the State row).

    Kept for callers that print one line per item; reports use the labelled
    rows from :func:`diffinite.notices.analysis_status_rows` directly.
    """
    return status_rows_as_lines(analysis_status_rows(status)[1:])


def _analysis_metadata_dict(
    metadata: AnalysisMetadata, analysis_status: AnalysisStatus | None = None
) -> dict[str, object]:
    """Serialize the effective analysis configuration without local file paths.

    The JSON report metadata and the manifest's ``analysis_configuration`` are
    both this dict, so they stay identical (including ``environment``).
    """
    return {
        "exec_mode": metadata.exec_mode,
        "k": metadata.k,
        "w": metadata.w,
        "threshold": metadata.threshold,
        "threshold_provenance": metadata.threshold_provenance,
        "autojunk": metadata.autojunk,
        "normalize": metadata.normalize,
        "lang_aware": metadata.lang_aware,
        "strip_comments": metadata.strip_comments,
        "deep_index_truncated": metadata.deep_index_truncated,
        "calibration_profile_id": metadata.calibration_profile_id,
        "calibration_status": metadata.calibration_status,
        "calibration_profile_mismatches": list(metadata.calibration_profile_mismatches),
        "calibration_threshold_matches": metadata.calibration_threshold_matches,
        "calibration_disclosure": (
            _metadata_threshold_disclosure(metadata) if metadata.exec_mode == "deep" else None
        ),
        "filename_threshold": metadata.filename_threshold,
        "by_word": metadata.by_word,
        "squash_blanks": metadata.squash_blanks,
        "normalize_whitespace": metadata.normalize_whitespace,
        "encoding": metadata.encoding,
        "binary_handling": metadata.binary_handling,
        "max_file_size_mb": metadata.max_file_size_mb,
        "max_diff_html_size_mb": metadata.max_diff_html_size_mb,
        "max_index_entries": metadata.max_index_entries,
        "detect_moved": metadata.detect_moved,
        "collapse_identical": metadata.collapse_identical,
        "metrics_only": metadata.metrics_only,
        "uncompared_mode": metadata.uncompared_mode,
        "allow_partial": metadata.allow_partial,
        "ignore_patterns": list(metadata.ignore_patterns),
        "ignore_file_sha256": metadata.ignore_file_sha256,
        "filter_applied": metadata.filter_applied,
        "filter_paths": list(metadata.filter_paths),
        "filter_file_sha256": metadata.filter_file_sha256,
        "sensitive_files": metadata.sensitive_files,
        "sensitive_preset_version": metadata.sensitive_preset_version,
        "sensitive_preset_rules": list(metadata.sensitive_preset_rules),
        "include_patterns": list(metadata.include_patterns),
        "bundle_sources": metadata.bundle_sources,
        "line_comment_unstripped_extensions": list(metadata.line_comment_unstripped_extensions),
        "deep_comment_unstripped_extensions": list(metadata.deep_comment_unstripped_extensions),
        "python_version": metadata.python_version,
        "unicodedata_version": metadata.unicodedata_version,
        "pygments_version": metadata.pygments_version,
        "lang_aware_tiers": {ext: list(tiers) for ext, tiers in metadata.lang_aware_tiers},
        # Same dict as the manifest's top-level "environment" (write_manifest).
        "environment": _environment_dict(metadata, analysis_status),
    }


def _environment_dict(
    metadata: AnalysisMetadata, analysis_status: AnalysisStatus | None = None
) -> dict[str, object]:
    """Software versions the fingerprints depend on (manifest and JSON ``environment``).

    Tokenization uses NFC and Unicode word-character classes (Python's ``unicodedata``)
    and ``--lang-aware`` uses Pygments lexers, so the same input can fingerprint
    differently under other versions. The lang-aware keys are present only when
    the lang-aware channel actually ran.
    """
    env: dict[str, object] = {
        "python_version": metadata.python_version,
        "pygments_version": metadata.pygments_version,
        "unicodedata_version": metadata.unicodedata_version,
    }
    if metadata.exec_mode == "deep" and metadata.normalize and metadata.lang_aware:
        env["lang_aware_tiers"] = {ext: list(tiers) for ext, tiers in metadata.lang_aware_tiers}
        env["lang_aware_fallback_files"] = (
            [dict(item) for item in analysis_status.deep_lang_aware_fallback_files]
            if analysis_status is not None
            else []
        )
    return env


def _metadata_threshold_disclosure(metadata: AnalysisMetadata) -> str:
    """Render one canonical disclosure from the effective metadata profile."""
    assessment = assess_normalize_metadata(metadata) if metadata.normalize else None
    return threshold_disclosure(
        metadata.threshold,
        metadata.threshold_provenance,
        metadata.normalize,
        assessment=assessment,
    )


def _md_table(header: tuple[str, str], rows: list[tuple[str, str]]) -> list[str]:
    """Two-column Markdown table (cells are trusted Markdown)."""
    out = [f"| {header[0]} | {header[1]} |", "|---|---|"]
    out += [f"| {label} | {value} |" for label, value in rows]
    return out


def _limitations_md(meta: AnalysisMetadata | None) -> str:
    """The Scope and Limitations section (Markdown)."""
    lines = ["## Scope and Limitations\n"]
    lines += [f"{i}. {notice}" for i, notice in enumerate(report_notice_texts(meta), 1)]
    lines.append("")
    return "\n".join(lines)


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    """``"1 rule"`` / ``"2 rules"`` with thousands separators."""
    return f"{count_label(n)} {singular if n == 1 else (plural or singular + 's')}"


def _md_cell_text(s: str) -> str:
    """Plain text for a Markdown table cell, shown literally.

    Control characters become visible symbols, and Markdown punctuation and
    ``|`` are backslash-escaped, so a file name cannot forge a cell, a link or
    emphasis.
    """
    s = _visible_controls(s)
    return re.sub(r"([\\`*_\[\]<>|#&~])", r"\\\1", s)


def _build_metadata_banner_md(meta: AnalysisMetadata, status: AnalysisStatus | None = None) -> str:
    """Return the Analysis Configuration, Analysis Status and Scope sections."""
    rows: list[tuple[str, str]] = [
        ("Mode", meta.exec_mode),
        ("K-gram size (K)", str(meta.k)),
        ("Window size (W)", str(meta.w)),
        ("Jaccard threshold", threshold_label(meta.threshold)),
        ("Threshold source", threshold_source_label(meta.threshold_provenance)),
        ("Identifier normalization", "on" if meta.normalize else "off"),
    ]
    if meta.lang_aware:
        rows.append(("Language-aware tokenization", "on"))
    rows += [
        ("Line diff autojunk", "on" if meta.autojunk else "off"),
        (
            "Ignore policy",
            f"{_plural(len(meta.ignore_patterns), 'rule')}; SHA-256 "
            + (_md_code(meta.ignore_file_sha256, table=True) if meta.ignore_file_sha256 else "none"),
        ),
        (
            "Selection filter",
            f"{'applied' if meta.filter_applied else 'none'}; "
            f"{_plural(len(meta.filter_paths), 'path')}; SHA-256 "
            + (_md_code(meta.filter_file_sha256, table=True) if meta.filter_file_sha256 else "none"),
        ),
    ]
    rows += [(label, _md_cell_text(value)) for label, value in policy_config_rows(meta)]
    lines = ["## Analysis Configuration\n", *_md_table(("Setting", "Value"), rows), ""]
    if status is not None:
        status_rows = [
            (label, _md_cell_text(value)) for label, value in analysis_status_rows(status)
        ]
        lines += ["## Analysis Status\n", *_md_table(("Item", "Value"), status_rows), ""]
        excluded_rows = [
            (_md_cell_text(path), _md_cell_text(reason))
            for path, reason in excluded_input_rows(status)
        ]
        if excluded_rows:
            lines += [
                f"## {EXCLUDED_INPUTS_HEADING}\n",
                *_md_table(("Input", "Reason"), excluded_rows),
                "",
            ]
    lines.append(_limitations_md(meta))
    return "\n".join(lines)


def _build_metadata_banner_html(
    meta: AnalysisMetadata, status: AnalysisStatus | None = None
) -> str:
    """Return the configuration, status and scope block for per-pair and index pages."""
    from diffinite.pdf_gen import (
        alert_html,
        config_rows,
        excluded_inputs_html,
        incomplete_notice,
        kv_table_html,
        limitations_html,
    )

    alerts = alert_html(incomplete_notice(meta, status))
    status_html = ""
    if status is not None:
        status_rows = [
            (html_mod.escape(label), html_mod.escape(value))
            for label, value in analysis_status_rows(status)
        ]
        status_html = "<h2>Analysis Status</h2>\n" + kv_table_html(status_rows)
        status_html += excluded_inputs_html(status)
    # Threshold and threshold source in the report-wide wording, whatever the
    # shared row builder prints for them.
    plain = {
        "Jaccard threshold": html_mod.escape(threshold_label(meta.threshold)),
        "Threshold source": html_mod.escape(threshold_source_label(meta.threshold_provenance)),
    }
    cfg_rows = [(label, plain.get(label, value)) for label, value in config_rows(meta)]
    return (
        '<div class="analysis-meta">\n'
        + alerts
        + "<h2>Analysis Configuration</h2>\n"
        + kv_table_html(cfg_rows)
        + status_html
        + limitations_html(meta)
        + "</div>\n"
    )


def _limitations_html_only() -> str:
    """Scope and Limitations for pages built without analysis metadata."""
    from diffinite.pdf_gen import limitations_html

    return limitations_html(None)


def _visible_controls(s: str) -> str:
    """Replace C0 control characters and DEL with their Unicode Control Pictures.

    A file name containing a newline (legal on POSIX) must not start a new
    Markdown block or a new line in a plain-text list, where it could forge a
    heading or table row. U+2400 + code is the Unicode "Control Pictures" block
    (U+2400..U+241F for C0, U+2421 for DEL), so the character stays visible.
    """
    return visible_controls(s)


def _md_code(s: str, *, table: bool = False) -> str:
    """Render *s* as a CommonMark code span that shows it literally.

    Inside a code span CommonMark processes no backslash escapes or entities,
    so the value is not escaped; instead the fence is a backtick run one longer
    than the longest run in the value, padded with a space when the value
    starts or ends with a backtick. Control characters become visible symbols
    (:func:`_visible_controls`). Only in GFM table cells is ``|`` escaped as
    ``\\|``, because the table parser splits cells before parsing the span and
    removes that escape itself.
    """
    s = _visible_controls(s)
    if table:
        s = s.replace("|", "\\|")
    longest = max((len(run) for run in re.findall(r"`+", s)), default=0)
    fence = "`" * (longest + 1)
    # CommonMark strips one space from each side when both ends are spaces, so a
    # value that itself starts and ends with a space needs the pad as well.
    pad = (
        " "
        if s.startswith("`") or s.endswith("`") or (s.startswith(" ") and s.endswith(" ") and s.strip(" "))
        else ""
    )
    return f"{fence}{pad}{s}{pad}{fence}"


def _write_unreadable_log(
    path: str | None,
    unreadable_files: list[str],
    *,
    overwrite: bool = True,
) -> None:
    """Persist unreadable-file evidence without clobbering it unless requested."""
    if not path or not unreadable_files:
        return
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation makes the fail-closed path race-safe: a prior run's
        # diagnostic is never truncated between an existence check and open().
        with out.open("w" if overwrite else "x", encoding="utf-8") as handle:
            handle.write("# Diffinite Unreadable Files Log\n")
            handle.write("# Files below could not be read for analysis or hashing.\n\n")
            for filename in sorted(set(unreadable_files)):
                handle.write(filename + "\n")
    except FileExistsError:
        if overwrite:
            raise
        # The existing log may belong to an earlier committed report set, so it
        # is not clobbered — but this run's diagnostics must not vanish either.
        logger.error(
            "Unreadable-file log %s already exists and was left unchanged; it is "
            "not from this run. Files this run could not read or skipped (%d):",
            out,
            len(set(unreadable_files)),
        )
        for filename in sorted(set(unreadable_files)):
            logger.error("  %s", filename)


def _write_report_checksum_sidecars(report_paths: tuple[str | None, ...]) -> None:
    """Write integrity sidecars, failing the report transaction on any error."""
    for report_path in report_paths:
        if not report_path:
            continue
        path = Path(report_path)
        if not path.is_file():
            continue
        digest = _sha256_file(path)
        Path(f"{path}.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
        # Compatibility only: this is a checksum, not an electronic signature
        # or chain-of-custody attestation.
        Path(f"{path}.sig").write_text(
            "DEPRECATED: plain SHA-256 checksum; not a digital signature "
            "or chain-of-custody proof. Use the .sha256 sidecar.\n"
            f"SHA-256: {digest}\nReport: {path.name}\n",
            encoding="utf-8",
        )
        logger.info("  SHA-256 of %s: %s", path.name, digest)


def _log_report_digests(report_paths: tuple[str | None, ...]) -> None:
    """Log the SHA-256 of reports that get no sidecar (Markdown, JSON)."""
    for report_path in report_paths:
        if not report_path:
            continue
        path = Path(report_path)
        if path.is_file():
            logger.info("  SHA-256 of %s: %s", path.name, _sha256_file(path))


def _remove_stale_output_file(path: str) -> None:
    """Remove an optional output that this run did not need to populate."""
    output = Path(path)
    if not output.exists() and not _path_is_redirect(output):
        return
    if _path_is_redirect(output) or not output.is_file():
        raise SourceIntegrityError(f"Refusing to remove unsafe stale output: {output}")
    output.unlink()


def _csv_safe_cell(value: Any) -> Any:
    """Neutralize spreadsheet formulas while preserving numeric CSV cells."""
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if value[0] in "\t\r\n" or (stripped and stripped[0] in "=+-@"):
        # OWASP CSV Injection guidance recommends an apostrophe prefix so Excel
        # and similar spreadsheet programs treat attacker-controlled text as text.
        return f"'{value}"
    return value


def _verify_published_evidence(
    manifest_path: str,
    report_paths: list[str],
    manifest_digest: str,
    bundle_path: str | None,
    bundle_digest: str | None,
    *,
    split_output_trees: list[str],
    absent_paths: list[str],
) -> None:
    """Recheck the complete output state immediately before transaction commit."""
    manifest_file = Path(manifest_path)
    _reject_redirecting_components(manifest_file, label="manifest verification")
    if not manifest_file.is_file() or _path_is_redirect(manifest_file):
        raise SourceIntegrityError("Integrity manifest disappeared before commit")
    manifest_bytes = manifest_file.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest:
        raise SourceIntegrityError("Integrity manifest changed before output commit")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceIntegrityError("Integrity manifest became unreadable before commit") from exc

    entries = manifest.get("reports")
    if not isinstance(entries, list):
        raise SourceIntegrityError("Integrity manifest is missing its report list")
    expected: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SourceIntegrityError("Integrity manifest contains an invalid report entry")
        logical_path = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(logical_path, str) or not isinstance(digest, str):
            raise SourceIntegrityError("Integrity manifest contains an invalid report hash")
        if logical_path in expected:
            raise SourceIntegrityError(
                f"Integrity manifest contains duplicate report path: {logical_path}"
            )
        expected[logical_path] = digest

    # Same split roots as write_manifest / create_evidence_bundle, so the
    # logical names are computed identically on both sides.
    mapped = _logical_report_paths(report_paths, split_output_trees)
    if {logical for _path, logical in mapped} != set(expected):
        raise SourceIntegrityError(
            "Generated report set changed after the integrity manifest was written"
        )
    for report_path, logical_path in mapped:
        _reject_redirecting_components(report_path, label="report verification")
        if (
            not report_path.is_file()
            or _path_is_redirect(report_path)
            or report_path.stat().st_nlink > 1
        ):
            raise SourceIntegrityError(
                f"Generated report became unsafe before commit: {logical_path}"
            )
        if _sha256_file(report_path) != expected[logical_path]:
            raise SourceIntegrityError(
                f"Generated report changed before output commit: {logical_path}"
            )

    if bundle_path is None:
        if bundle_digest is not None:
            raise SourceIntegrityError("Unexpected evidence bundle digest state")
    else:
        if bundle_digest is None:
            raise SourceIntegrityError("Evidence bundle digest is missing before commit")

        bundle = Path(bundle_path)
        sidecar = Path(f"{bundle_path}.sha256")
        for label, path in (
            ("evidence bundle verification", bundle),
            ("evidence bundle checksum verification", sidecar),
        ):
            _reject_redirecting_components(path, label=label)
            if not path.is_file() or _path_is_redirect(path) or path.stat().st_nlink > 1:
                raise SourceIntegrityError(f"{label} path became unsafe before commit")
        if _sha256_file(bundle) != bundle_digest:
            raise SourceIntegrityError("Evidence bundle changed before output commit")
        expected_sidecar = f"{bundle_digest}  {bundle.name}"
        if sidecar.read_text(encoding="utf-8").splitlines() != [expected_sidecar]:
            raise SourceIntegrityError(
                "Evidence bundle checksum sidecar changed before output commit"
            )

    absolute_reports = {_lexical_absolute(path) for path in report_paths}
    for tree_text in split_output_trees:
        tree = _lexical_absolute(tree_text)
        _validate_live_output_target(_OutputTarget("split-report final verification", tree, True))
        expected_tree_files = {path for path in absolute_reports if path.is_relative_to(tree)}
        actual_tree_files = {_lexical_absolute(path) for path in tree.rglob("*") if path.is_file()}
        if actual_tree_files != expected_tree_files:
            raise SourceIntegrityError(
                f"Split-report tree changed after the integrity manifest was written: {tree}"
            )

    for path_text in absent_paths:
        path = _lexical_absolute(path_text)
        _reject_redirecting_components(path, label="obsolete split-report anchor")
        if path.exists() or _path_is_redirect(path):
            raise SourceIntegrityError(
                f"Obsolete merged report artifact reappeared before commit: {path}"
            )


def _selection_omitted_note(status: AnalysisStatus | None) -> str | None:
    """Disclosure for unmatched files a --filter-json selection left out of the lists.

    A selective report lists only the selected A files, so an empty "Only in B"
    list there means "omitted", not "none exist". None when nothing was omitted.
    """
    if status is None or not (
        status.filter_omitted_unmatched_a or status.filter_omitted_unmatched_b
    ):
        return None
    return (
        "Selective report (--filter-json): unmatched files not listed, "
        f"{count_label(status.filter_omitted_unmatched_a)} in A; "
        f"{count_label(status.filter_omitted_unmatched_b)} in B"
    )


def _write_uncompared_file(
    path: str,
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a_label: str,
    dir_b_label: str,
    omitted_note: str | None = None,
    excluded: list[dict[str, str]] | None = None,
) -> None:
    """Write a privacy-safe list of files excluded from one-to-one comparison."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        handle.write("# Diffinite: Uncompared Files\n")
        # Control characters (a POSIX name may contain a newline) are written as
        # visible symbols so a name cannot forge a section line.
        handle.write(f"# Dir A: {_visible_controls(dir_a_label)}\n")
        handle.write(f"# Dir B: {_visible_controls(dir_b_label)}\n")
        if omitted_note:
            handle.write(f"# {omitted_note}\n")
        handle.write("\n")
        if unmatched_a:
            handle.write(f"## Only in A ({len(unmatched_a)} files)\n")
            for item in unmatched_a:
                handle.write(f"  {_visible_controls(item)}\n")
            handle.write("\n")
        if unmatched_b:
            handle.write(f"## Only in B ({len(unmatched_b)} files)\n")
            for item in unmatched_b:
                handle.write(f"  {_visible_controls(item)}\n")
            handle.write("\n")
        if excluded:
            handle.write(f"## Excluded by policy ({len(excluded)} entries)\n")
            for entry in excluded:
                handle.write(f"  {_visible_controls(exclusion_label(entry))}\n")


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------
def _hash_table_md(hashes_a: list[FileHashEntry], hashes_b: list[FileHashEntry]) -> str:
    """The SHA-256 section (Markdown), the counterpart of ``build_hash_table_html``."""
    lines = ["\n## Evidence Integrity: SHA-256 Hashes\n"]
    for label, hashes in (("Directory A", hashes_a), ("Directory B", hashes_b)):
        if not hashes:
            continue
        lines += [
            f"### {label}\n",
            "| # | File | SHA-256 | Size (bytes) |",
            "|--:|------|---------|--:|",
        ]
        lines += [
            f"| {idx} | {_md_code(h.rel_path, table=True)} | {_md_code(h.sha256, table=True)} "
            f"| {count_label(h.size_bytes)} |"
            for idx, h in enumerate(hashes, 1)
        ]
        lines.append("")
    lines.append(f"{INTEGRITY_NOTICE}\n")
    return "\n".join(lines)


def _generate_markdown_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    strip_comments: bool,
    deep_results: list[DeepMatchResult] | None,
    output_path: str,
    *,
    metadata: AnalysisMetadata | None = None,
    analysis_status: AnalysisStatus | None = None,
    uncompared_mode: str = "inline",
    file_hashes: tuple[list[FileHashEntry], list[FileHashEntry]] | None = None,
) -> None:
    """Generate a Markdown summary report.

    ``file_hashes`` (A, B) is given under ``--hash``: the report then lists the
    SHA-256 digest of every analyzed file, followed by the integrity notice,
    as the PDF and HTML reports do.
    """
    unit = "word" if by_word else "line"
    comment_mode = line_diff_comment_mode(strip_comments, metadata)
    deep_comment_mode = deep_compare_comment_mode(strip_comments, metadata)
    excluded_pairs = analysis_status.diff_excluded_pairs if analysis_status is not None else []

    from diffinite.pdf_gen import REPORT_TITLE, incomplete_notice

    lines: list[str] = []
    lines.append(f"# {REPORT_TITLE}\n")
    alert_text = incomplete_notice(metadata, analysis_status)
    if alert_text:
        lines.append(f"> {alert_text}\n")

    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    particulars: list[tuple[str, str]] = [
        ("Directory A", _md_code(dir_a, table=True)),
        ("Directory B", _md_code(dir_b, table=True)),
        ("Report generated", generated),
        ("Tool", f"Diffinite {__version__}"),
        ("Comparison unit", unit),
    ]
    if deep_comment_mode in ("not-applicable", comment_mode):
        particulars.append(("Comments", comment_mode))
    else:
        particulars.append(("Comments (line diff)", comment_mode))
        particulars.append(("Comments (Deep Compare)", deep_comment_mode))
    matched_value = count_label(len(results))
    if excluded_pairs:
        matched_value += (
            f" (and {_plural(len(excluded_pairs), 'matched pair')} not compared under "
            "--binary-handling exclude, listed below)"
        )
    particulars.append(("Matched pairs", matched_value))
    omitted_note = _selection_omitted_note(analysis_status)
    # Same wording as the PDF/HTML cover.
    unmatched_value = f"{count_label(len(unmatched_a))} in A; {count_label(len(unmatched_b))} in B"
    if omitted_note:
        particulars.append(("Unmatched files (listed)", f"{unmatched_value}. {omitted_note}"))
    else:
        particulars.append(("Unmatched files", unmatched_value))
    lines += ["## Particulars\n", *_md_table(("Item", "Value"), particulars), ""]

    if metadata:
        lines.append(_build_metadata_banner_md(metadata, analysis_status))
    else:
        lines.append(_limitations_md(None))

    # Summary table
    lines.append("## Summary\n")
    lines.append(
        f"| # | File A | File B | Name similarity | {unit.capitalize()} match | Added | Deleted |"
    )
    lines.append("|--:|--------|--------|--:|--:|--:|--:|")
    for idx, r in enumerate(results, 1):
        files = (
            f"| {idx} | {_md_code(r.match.rel_path_a, table=True)} "
            f"| {_md_code(r.match.rel_path_b, table=True)} "
            f"| {name_similarity_label(r.match.similarity)} "
        )
        hash_label = hash_only_label(r)
        if r.error:
            # No difflib value was computed: never print a percentage here.
            lines.append(
                files + f"| Not compared ({_md_code(r.error, table=True)}) | n/a | n/a |"
            )
        elif hash_label is not None:
            lines.append(files + f"| {hash_label} | n/a | n/a |")
        else:
            lines.append(
                files + f"| {line_match_label(r.ratio)} "
                f"| {signed_count(r.additions, '+')} | {signed_count(r.deletions, '-')} |"
            )

    if excluded_pairs:
        lines.append("\n## Matched Pairs Not Compared (--binary-handling exclude)\n")
        for item in excluded_pairs:
            lines.append(
                f"- {_md_code(item.get('file_a', '?'))} and {_md_code(item.get('file_b', '?'))}:"
                f" {_md_cell_text(item_reason_label(item.get('reason')))}"
            )

    # Unmatched
    if uncompared_mode == "inline" and (unmatched_a or unmatched_b):
        lines.append("\n## Unmatched Files\n")
        if unmatched_a:
            lines.append(f"### Only in A ({_md_code(dir_a)})\n")
            for f in unmatched_a:
                lines.append(f"- {_md_code(f)}")
        if unmatched_b:
            lines.append(f"{chr(10) if unmatched_a else ''}### Only in B ({_md_code(dir_b)})\n")
            for f in unmatched_b:
                lines.append(f"- {_md_code(f)}")

    # Deep Compare
    if deep_results:
        lines.append("\n## Deep Compare: Cross-Match Results\n")
        lines.append("| File A | File B | Shared hashes | Jaccard | A in B | B in A |")
        lines.append("|--------|--------|--:|--:|--:|--:|")
        any_inconclusive = False
        for dr in deep_results:
            for b_file, shared, jaccard, inconclusive in dr.matched_files_b:
                # Rounded only for display; 100.00% only when shared == union.
                jaccard_label = overlap_label(jaccard)
                if inconclusive:
                    any_inconclusive = True
                    jaccard_label += " (inconclusive)"
                a_in_b, b_in_a = dr.containment(b_file, shared)
                lines.append(
                    f"| {_md_code(dr.file_a, table=True)} | {_md_code(b_file, table=True)} "
                    f"| {count_label(shared)} | {jaccard_label} "
                    f"| {overlap_label(a_in_b)} | {overlap_label(b_in_a)} |"
                )
        lines.append(f"\n{CONTAINMENT_NOTE}\n")
        if any_inconclusive:
            lines.append(f"{INCONCLUSIVE_NOTICE}\n")

    if file_hashes is not None:
        lines.append(_hash_table_md(*file_hashes))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    logger.info("  Markdown report: %s", out.resolve())


# ---------------------------------------------------------------------------
# JSON report generator (for VSCode Extension consumption)
# ---------------------------------------------------------------------------
def _generate_json_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    strip_comments: bool,
    deep_results: list[DeepMatchResult] | None,
    output_path: str,
    *,
    metadata: AnalysisMetadata | None = None,
    analysis_status: AnalysisStatus | None = None,
    normalize_ws: bool = False,
    uncompared_mode: str = "inline",
) -> None:
    """Generate a JSON report for programmatic consumption.

    Serializes all analysis results including HTML diffs so that
    external tools (e.g. VSCode Extension) can render them without
    re-running the pipeline.
    """
    unit = "word" if by_word else "line"
    comment_mode = line_diff_comment_mode(strip_comments, metadata)

    meta_dict = (
        _analysis_metadata_dict(metadata, analysis_status) if metadata is not None else None
    )

    result_list = []
    for r in results:
        entry = {
            "file_a": r.match.rel_path_a,
            "file_b": r.match.rel_path_b,
            "name_similarity": r.match.similarity,
            "ratio": r.ratio,
            "additions": r.additions,
            "deletions": r.deletions,
            "html_diff": r.html_diff,
            "error": r.error,
            "binary": r.binary,
            "truncation": {
                "truncated": r.html_diff_truncated,
                "reason": r.html_diff_truncation_reason,
                "original_bytes": r.html_diff_original_bytes,
                "omitted_bytes": r.html_diff_omitted_bytes,
            },
        }
        if r.binary:
            entry["hash_match"] = r.hash_match
        # "ratio" is kept for schema compatibility, but for these pairs difflib
        # never ran: the value only encodes SHA-256 identical (1.0) / different
        # (0.0), and for an error pair nothing was compared at all.
        entry["comparison_method"] = (
            "not-compared" if r.error else ("sha256-only" if r.binary else "difflib")
        )
        entry["hash_only_reason"] = (r.hash_only_reason or "not-decodable") if (
            r.binary and not r.error
        ) else None
        entry["comparison_note"] = hash_only_label(r)
        result_list.append(entry)

    status_dict = (
        analysis_status.to_dict() if analysis_status is not None else AnalysisStatus().to_dict()
    )
    # null: Deep Compare did not run; 0: it ran and no pair reached the threshold.
    status_dict["deep"]["reported_pair_count"] = (
        analysis_status.deep_reported_pair_count if analysis_status is not None else None
    )

    deep_list = None
    if deep_results is not None:
        deep_list = []
        for dr in deep_results:
            deep_list.append(
                {
                    "file_a": dr.file_a,
                    # Winnowed positions (duplicates included); NOT the Jaccard
                    # denominator. unique_hashes_a is the set size |A|.
                    "fingerprint_count_a": dr.fingerprint_count_a,
                    "unique_hashes_a": dr.unique_hashes_a,
                    "matches": [
                        {
                            "file_b": b_file,
                            "shared_hashes": shared,
                            "unique_hashes_b": dr.unique_hashes_b.get(b_file, 0),
                            "jaccard": jaccard,
                            "containment_a_in_b": dr.containment(b_file, shared)[0],
                            "containment_b_in_a": dr.containment(b_file, shared)[1],
                            "inconclusive": inconclusive,
                        }
                        for b_file, shared, jaccard, inconclusive in dr.matched_files_b
                    ],
                }
            )

    # Schema v2 adds explicit effective configuration, preprocessing, and
    # completeness accounting while retaining all v1 fields for compatibility.
    report = {
        "schema_version": 2,
        "metadata": meta_dict,
        "dir_a": dir_a,
        "dir_b": dir_b,
        "comparison_unit": unit,
        "comment_mode": comment_mode,
        "preprocessing": {
            "line_diff_comments": comment_mode,
            # --normalize --lang-aware drops lexer comment tokens regardless of
            # --strip-comments, so the deep channel is reported separately.
            "deep_compare_comments": deep_compare_comment_mode(strip_comments, metadata),
            "normalize_whitespace": normalize_ws,
            "fingerprint_normalize": (metadata.normalize if metadata is not None else False),
            "lang_aware": metadata.lang_aware if metadata is not None else False,
            # Extensions whose files kept their comments under --strip-comments
            # (no registered comment syntax), per channel.
            "comments_not_stripped_extensions": {
                "line_diff": (
                    list(metadata.line_comment_unstripped_extensions)
                    if metadata is not None and strip_comments
                    else []
                ),
                "deep_compare": (
                    list(metadata.deep_comment_unstripped_extensions)
                    if metadata is not None and strip_comments
                    else []
                ),
            },
        },
        "analysis_status": status_dict,
        "summary": {
            "matched_pairs": len(results),
            "excluded_matched_pairs": (
                len(analysis_status.diff_excluded_pairs) if analysis_status is not None else 0
            ),
            # Counts of the listed files. In a --filter-json run the files the
            # selection left out are counted separately, never folded into 0.
            "unmatched_a_count": len(unmatched_a),
            "unmatched_b_count": len(unmatched_b),
            "omitted_unmatched_a_count": (
                analysis_status.filter_omitted_unmatched_a if analysis_status is not None else 0
            ),
            "omitted_unmatched_b_count": (
                analysis_status.filter_omitted_unmatched_b if analysis_status is not None else 0
            ),
        },
        # The legal notices that apply to this run, in the wording and order of
        # the human-readable reports (diffinite.notices.applicable_notices).
        # The integrity notice always applies here: every run writes the
        # manifest of SHA-256 digests next to this report, and the JSON must not
        # change with presentation options such as --hash.
        "notices": applicable_notices(
            metadata,
            any_inconclusive=any(
                inconclusive
                for dr in (deep_results or [])
                for _b, _s, _j, inconclusive in dr.matched_files_b
            ),
            deep_rows=any(dr.matched_files_b for dr in (deep_results or [])),
            hashes_reported=True,
        ),
        "results": result_list,
        "deep_results": deep_list,
        "unmatched_a": unmatched_a if uncompared_mode == "inline" else [],
        "unmatched_b": unmatched_b if uncompared_mode == "inline" else [],
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("  JSON report: %s", out.resolve())


# ---------------------------------------------------------------------------
# HTML report generator (standalone, self-contained)
# ---------------------------------------------------------------------------
def _pair_body_html(r: DiffResult, unit: str) -> str:
    """Per-pair section body shared by the merged and the per-pair HTML pages.

    A difflib percentage and +/- counts are printed only when difflib ran:
    error pairs show the error, SHA-256-only pairs show the hash verdict.
    """
    from diffinite.pdf_gen import pair_result_html

    return pair_result_html(r, unit)


def _generate_html_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    strip_comments: bool,
    deep_results: list[DeepMatchResult] | None,
    output_path: str,
    *,
    metadata: AnalysisMetadata | None = None,
    analysis_status: AnalysisStatus | None = None,
    hash_table_html: str | None = None,
    uncompared_mode: str = "inline",
) -> None:
    """Generate a standalone HTML report with all diffs inline."""
    cover_html_body = build_cover_body(
        results,
        unmatched_a,
        unmatched_b,
        dir_a,
        dir_b,
        by_word,
        strip_comments,
        deep_results=deep_results,
        metadata=metadata,
        analysis_status=analysis_status,
        hash_table_html=hash_table_html,
        uncompared_mode=uncompared_mode,
    )

    # Append all inline diffs
    unit = "word" if by_word else "line"
    diff_sections: list[str] = []
    excluded_pairs = analysis_status.diff_excluded_pairs if analysis_status is not None else []
    from diffinite.pdf_gen import _CSS_BODY, _CSS_SCREEN, REPORT_TITLE, pair_heading_html

    if excluded_pairs:
        items = "".join(
            f"<li>{html_mod.escape(item.get('file_a', '?'))} and "
            f"{html_mod.escape(item.get('file_b', '?'))}: "
            f"{html_mod.escape(item_reason_label(item.get('reason')))}</li>"
            for item in excluded_pairs
        )
        diff_sections.append(
            "<h2>Matched pairs not compared (--binary-handling exclude)</h2>\n"
            f"<ul class='unmatched'>{items}</ul>\n"
        )
    for idx, r in enumerate(results, 1):
        heading = pair_heading_html(idx, r.match.rel_path_a, r.match.rel_path_b)
        diff_sections.append(heading + _pair_body_html(r, unit))

    # Write full standalone HTML
    sections = "".join(
        f'<section class="pair">\n{section}</section>\n' for section in diff_sections
    )
    full_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Diffinite: {REPORT_TITLE}</title>
<style>
{_CSS_BODY}
{_CSS_SCREEN}
</style>
</head>
<body>
{cover_html_body}
{sections}
</body>
</html>
"""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(full_html, encoding="utf-8")
    logger.info("  HTML report: %s", out.resolve())


# ---------------------------------------------------------------------------
# Individual HTML reports (--no-merge) + index.html
# ---------------------------------------------------------------------------
def _generate_individual_html(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    strip_comments: bool,
    deep_results: list[DeepMatchResult] | None,
    output_path: str,
    *,
    preserve_tree: bool = True,
    metadata: AnalysisMetadata | None = None,
    analysis_status: AnalysisStatus | None = None,
    hash_table_html: str | None = None,
    uncompared_mode: str = "inline",
) -> None:
    """Generate individual HTML files per diff pair + an index.html."""
    from diffinite.pdf_gen import _CSS_BODY, _CSS_SCREEN, REPORT_TITLE, pair_heading_html

    out_stem = Path(output_path).stem
    out_dir = Path(output_path).parent / f"{out_stem}_files"
    out_dir.mkdir(parents=True, exist_ok=True)

    unit = "word" if by_word else "line"
    index_entries: list[dict] = []
    status_banner = (
        _build_metadata_banner_html(metadata, analysis_status)
        if metadata is not None
        else _limitations_html_only()
    )

    for idx, r in enumerate(results, 1):
        # Determine output filename
        if preserve_tree:
            rel = PurePosixPath(r.match.rel_path_a)
            # Keep the complete source filename and place entries below a
            # reserved namespace. Replacing the original suffix made `same.py`
            # and `same.js` collide, while root-level `index` overwrote the
            # generated evidence index.
            dest = out_dir / "entries" / str(rel).replace("/", os.sep)
            dest = Path(f"{dest}.html")
        else:
            safe_name = Path(r.match.rel_path_a).name.replace(" ", "_")
            dest = out_dir / f"{idx:03d}_{safe_name}.html"

        dest.parent.mkdir(parents=True, exist_ok=True)

        # Build single-file HTML content
        body = pair_heading_html(idx, r.match.rel_path_a, r.match.rel_path_b) + _pair_body_html(
            r, unit
        )

        full_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html_mod.escape(r.match.rel_path_a)}: Diffinite {REPORT_TITLE}</title>
<style>
{_CSS_BODY}
{_CSS_SCREEN}
</style>
</head>
<body>
<p class="doc-tool">Diffinite {REPORT_TITLE}</p>
{status_banner}
{body}
</body>
</html>
"""
        dest.write_text(full_html, encoding="utf-8")

        # Track for index.html
        rel_link = dest.relative_to(out_dir).as_posix()
        index_entries.append(
            {
                "idx": idx,
                "file_a": r.match.rel_path_a,
                "file_b": r.match.rel_path_b,
                "name_similarity": r.match.similarity,  # fuzzy filename similarity, 0 to 100
                "ratio": r.ratio,  # line (or word) match, 0.0 to 1.0
                "binary": r.binary,
                "hash_match": r.hash_match,
                "additions": r.additions,
                "deletions": r.deletions,
                "link": rel_link,
                "error": r.error,
                "hash_label": hash_only_label(r),
            }
        )

    # Build index.html
    _build_index_html(
        out_dir,
        index_entries,
        dir_a,
        dir_b,
        unmatched_a,
        unmatched_b,
        metadata=metadata,
        analysis_status=analysis_status,
        uncompared_mode=uncompared_mode,
        unit=unit,
    )
    logger.info(
        "  Individual HTML reports: %d, with index.html, in %s",
        len(index_entries),
        out_dir.resolve(),
    )


def _build_index_html(
    out_dir: Path,
    entries: list[dict],
    dir_a: str,
    dir_b: str,
    unmatched_a: list[str],
    unmatched_b: list[str],
    *,
    metadata: AnalysisMetadata | None = None,
    analysis_status: AnalysisStatus | None = None,
    uncompared_mode: str = "inline",
    unit: str = "line",
) -> None:
    """Generate an index.html with hyperlinks to all individual reports."""
    rows = []
    for e in entries:
        name_sim = name_similarity_label(e.get("name_similarity", 0.0))
        # The "<Unit> match" column mirrors the cover/CSV: percentage for text pairs,
        # SHA-256 status for binary pairs (difflib ratio is meaningless there).
        if e["error"]:
            content_match = "<td><em>Not compared (error)</em></td>"
        elif e.get("hash_label"):
            content_match = f"<td>{html_mod.escape(e['hash_label'])}</td>"
        else:
            content_match = f'<td class="num">{line_match_label(e["ratio"])}</td>'
        hash_only = bool(e["error"] or e.get("hash_label"))
        added = "n/a" if hash_only else signed_count(e["additions"], "+")
        deleted = "n/a" if hash_only else signed_count(e["deletions"], "-")
        rows.append(
            f"<tr>"
            f'<td class="num">{e["idx"]}</td>'
            f'<td><a href="{html_mod.escape(e["link"])}">'
            f"{html_mod.escape(e['file_a'])}</a></td>"
            f"<td>{html_mod.escape(e['file_b'])}</td>"
            f'<td class="num">{name_sim}</td>'
            f"{content_match}"
            f'<td class="num">{added}</td>'
            f'<td class="num">{deleted}</td>'
            f"</tr>\n"
        )

    unmatched_section = ""
    omitted_note = _selection_omitted_note(analysis_status)
    if uncompared_mode == "inline" and (unmatched_a or unmatched_b or omitted_note):
        ua_items = "".join(f"<li>{html_mod.escape(f)}</li>" for f in unmatched_a)
        ub_items = "".join(f"<li>{html_mod.escape(f)}</li>" for f in unmatched_b)
        omitted_html = f'<p class="note">{html_mod.escape(omitted_note)}</p>' if omitted_note else ""
        unmatched_section = f"""
<h2>Unmatched Files</h2>
{omitted_html}
<h3>Only in A ({len(unmatched_a)})</h3><ul class="unmatched">{ua_items}</ul>
<h3>Only in B ({len(unmatched_b)})</h3><ul class="unmatched">{ub_items}</ul>
"""

    from diffinite.pdf_gen import _CSS_BODY, _CSS_SCREEN, REPORT_TITLE, kv_table_html

    index_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Evidence Index: Diffinite {REPORT_TITLE}</title>
<style>
{_CSS_BODY}
{_CSS_SCREEN}
</style>
</head>
<body>
<p class="doc-tool">Diffinite {REPORT_TITLE}</p>
<h1>Evidence Index</h1>
{kv_table_html([
    ("Directory A", html_mod.escape(dir_a)),
    ("Directory B", html_mod.escape(dir_b)),
    ("Compared pairs", count_label(len(entries))),
])}
{_build_metadata_banner_html(metadata, analysis_status) if metadata is not None else _limitations_html_only()}
<h2>Compared Pairs</h2>
<p class="note">Each File A entry links to that pair's report.</p>
<table class="summary">
<thead>
<tr>
<th class="num" style="width: 4%;">#</th><th style="width: 33%;">File A</th><th style="width: 33%;">File B</th>
<th class="num" style="width: 7%;">Name similarity</th><th class="num" style="width: 11%;">{unit.capitalize()} match</th>
<th class="num" style="width: 6%;">Added</th><th class="num" style="width: 6%;">Deleted</th>
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>
{unmatched_section}
</body>
</html>
"""
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_pipeline(
    dir_a: str,
    dir_b: str,
    by_word: bool = False,
    strip_comments: bool = False,
    squash_blanks: bool = False,
    threshold: float = FUZZY_THRESHOLD,
    *,
    no_merge: bool = False,
    show_page_number: bool = False,
    show_file_number: bool = False,
    show_bates_number: bool = False,
    show_filename: bool = False,
    # Display options
    collapse_identical: bool = False,
    # Execution mode & deep compare options
    exec_mode: str = "deep",
    workers: int = 4,
    kgram_size: int = DEFAULT_K,
    window_size: int = DEFAULT_W,
    min_jaccard: float | None = None,
    threshold_provenance: str | None = None,
    normalize: bool = False,
    lang_aware: bool = False,
    metadata: AnalysisMetadata | None = None,
    # Multi-format output
    report_pdf: str | None = None,
    report_html: str | None = None,
    report_md: str | None = None,
    report_json: str | None = None,
    # Forensic options
    autojunk: bool = True,
    max_index_entries: int = 10_000_000,
    # Evidence integrity
    embed_hash: bool = False,
    bundle_path: str | None = None,
    allow_partial: bool = False,
    # Encoding
    encoding: str | None = None,
    # Sorting
    sort_by: str | None = None,
    sort_order: str = "asc",
    # Moved block detection
    detect_moved: bool = False,
    # Uncompared files
    uncompared_mode: str = "inline",
    # Bates prefix/suffix
    bates_prefix: str = "",
    bates_suffix: str = "",
    bates_start: int = 1,
    # Binary handling
    binary_handling: str = "hash",
    # Ignore list
    ignore_file: str | None = None,
    # Collection policy
    sensitive_files: str = "exclude",
    include_patterns: Sequence[str] | None = None,
    bundle_sources: str = "full",
    # Metrics-only output and JSON file filter
    metrics_only: bool = False,
    filter_json: str | None = None,
    # Stability & Forensics
    unreadable_log: str | None = None,
    max_file_size_mb: float = 10.0,
    max_diff_html_size_mb: float = 2.0,
    dir_alias_a: str | None = None,
    dir_alias_b: str | None = None,
    # Individual output tree structure
    preserve_tree: bool = True,
    # Whitespace normalization
    normalize_ws: bool = False,
    # PDF font
    pdf_font: str | None = None,
    pdf_lang: str | None = None,
) -> None:
    """Execute the full diff-to-report pipeline.
    # ... docstrings truncated ...
    """
    if exec_mode not in {"simple", "deep"}:
        raise ValueError("exec_mode must be 'simple' or 'deep'")
    if sensitive_files not in SENSITIVE_MODES:
        raise ValueError(f"sensitive_files must be one of {', '.join(SENSITIVE_MODES)}")
    if bundle_sources not in {"full", "none"}:
        raise ValueError("bundle_sources must be 'full' or 'none'")
    include_rules = tuple(p.strip() for p in (include_patterns or ()) if p.strip())
    for name, value in (
        ("kgram_size", kgram_size),
        ("window_size", window_size),
        ("workers", workers),
        ("max_index_entries", max_index_entries),
        ("bates_start", bates_start),
    ):
        if value < 1:
            raise ValueError(f"{name} must be >= 1")
    if not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("threshold must be finite and between 0 and 100")
    if min_jaccard is not None and (not math.isfinite(min_jaccard) or not 0 <= min_jaccard <= 1):
        raise ValueError("min_jaccard must be finite and between 0 and 1")
    for name, limit_value in (
        ("max_file_size_mb", max_file_size_mb),
        ("max_diff_html_size_mb", max_diff_html_size_mb),
    ):
        if not math.isfinite(limit_value) or limit_value <= 0:
            raise ValueError(f"{name} must be finite and greater than 0")

    # Determine effective output paths
    if report_pdf is None and report_html is None and report_md is None and report_json is None:
        report_pdf = "report.pdf"

    # --metrics-only emits ONLY the JSON metrics format (Markdown/HTML/PDF are
    # skipped). Without this, a --metrics-only run with no --report-json default
    # produced the PDF default which is then gated off → a silent no-op.
    if metrics_only and not report_json:
        anchor = report_pdf or report_html or report_md or "report.pdf"
        report_json = str(Path(anchor).with_suffix(".json"))
        logger.warning(
            "--metrics-only generates only the JSON metrics report: %s "
            "(Markdown, HTML and PDF reports are not produced in metrics-only mode).",
            report_json,
        )

    # The manifest stays next to the first requested report anchor. Resolve and
    # validate the complete output graph before even walking the source trees:
    # otherwise a report path inside an input can overwrite evidence or become
    # part of the very file set being compared.
    report_anchor = next(
        (path for path in (report_pdf, report_html, report_md, report_json) if path),
        None,
    )
    manifest_dir = str(Path(report_anchor).parent) if report_anchor else "."
    manifest_path = os.path.join(manifest_dir, "manifest.sha256.json")
    output_targets = _validate_output_boundaries(
        dir_a,
        dir_b,
        report_pdf=report_pdf,
        report_html=report_html,
        report_md=report_md,
        report_json=report_json,
        manifest_path=manifest_path,
        bundle_path=bundle_path,
        unreadable_log=unreadable_log,
        ignore_file=ignore_file,
        filter_json=filter_json,
        pdf_font=pdf_font,
        no_merge=no_merge,
        metrics_only=metrics_only,
        show_bates_number=show_bates_number,
        uncompared_mode=uncompared_mode,
    )

    # Determine effective aliases
    dir_a_disp = _display_label(dir_alias_a, dir_a)
    dir_b_disp = _display_label(dir_alias_b, dir_b)
    _reject_unencodable_names("directory label", [dir_a_disp, dir_b_disp])

    # Normalize/lang-aware affect only the deep fingerprint channel. Reporting
    # them as applied in simple mode would make the effective configuration false.
    normalize = bool(normalize and exec_mode == "deep")
    lang_aware = bool(lang_aware and normalize)
    if exec_mode != "deep":
        # Deep-only threshold inputs are not effective configuration in simple mode.
        min_jaccard = None
        threshold_provenance = None

    # Resolve library calls through the same Python source of truth as the CLI.
    if min_jaccard is None:
        effective_threshold, effective_provenance = resolve_threshold_deep(
            None,
            normalize,
        )
        min_jaccard = effective_threshold / 100.0
    else:
        # Record the threshold the caller actually set, not min_jaccard * 100
        # (e.g. 0.57 * 100 == 56.99999999999999). The CLI passes the 0-100 value
        # in metadata.threshold; use it whenever it is the value min_jaccard came
        # from. Otherwise round away the float round-trip error only if the
        # rounded value still maps back to exactly the same min_jaccard.
        if metadata is not None and metadata.threshold / 100.0 == min_jaccard:
            effective_threshold = metadata.threshold
        else:
            # 10 decimal places: far below any meaningful threshold step, far
            # above double-precision noise (~1e-14 at this magnitude).
            rounded = round(min_jaccard * 100.0, 10)
            effective_threshold = (
                rounded if rounded / 100.0 == min_jaccard else min_jaccard * 100.0
            )
        effective_provenance = "user"
        default_threshold, default_provenance = resolve_threshold_deep(None, normalize)
        if threshold_provenance == default_provenance and effective_threshold == default_threshold:
            effective_provenance = default_provenance

    calibration_assessment = (
        assess_normalize_calibration(
            threshold=effective_threshold,
            k=kgram_size,
            w=window_size,
            strip_comments=strip_comments,
            lang_aware=lang_aware,
        )
        if normalize
        else None
    )
    effective_squash_blanks = bool(strip_comments and squash_blanks)
    effective_encoding = encoding if encoding and encoding.lower() not in {"", "auto"} else "auto"

    # Metadata is output, not an alternative configuration input. Derive every
    # execution field from the values actually used by this run so a stale
    # caller-provided dataclass cannot make the report non-reproducible.
    if metadata is None:
        metadata = AnalysisMetadata(
            exec_mode=exec_mode,
            k=kgram_size,
            w=window_size,
            # Record on the 0-100 scale, matching the CLI (--threshold-deep) so
            # the same setting reads identically regardless of entry point.
            threshold=effective_threshold,
            autojunk=autojunk,
            threshold_provenance=effective_provenance,
            normalize=normalize,
            lang_aware=lang_aware,
        )
    metadata = dataclasses.replace(
        metadata,
        exec_mode=exec_mode,
        k=kgram_size,
        w=window_size,
        threshold=effective_threshold,
        autojunk=autojunk,
        deep_index_truncated=False,
        threshold_provenance=effective_provenance,
        normalize=normalize,
        lang_aware=lang_aware,
        strip_comments=strip_comments,
        calibration_profile_id=(
            calibration_assessment.profile_id if calibration_assessment else None
        ),
        calibration_status=(
            calibration_assessment.status if calibration_assessment else "not-applicable"
        ),
        calibration_profile_mismatches=(
            calibration_assessment.profile_mismatches if calibration_assessment else ()
        ),
        calibration_threshold_matches=(
            calibration_assessment.threshold_matches if calibration_assessment else None
        ),
        filename_threshold=threshold,
        by_word=by_word,
        squash_blanks=effective_squash_blanks,
        normalize_whitespace=normalize_ws,
        encoding=effective_encoding,
        binary_handling=binary_handling,
        max_file_size_mb=max_file_size_mb,
        max_diff_html_size_mb=max_diff_html_size_mb,
        max_index_entries=max_index_entries,
        detect_moved=detect_moved,
        collapse_identical=collapse_identical,
        metrics_only=metrics_only,
        uncompared_mode=uncompared_mode,
        allow_partial=allow_partial,
        # Tokenization (NFC, \w classes) and lang-aware lexing depend on these.
        python_version=platform.python_version(),
        unicodedata_version=unicodedata.unidata_version,
        pygments_version=pygments_version(),
    )

    analysis_status = AnalysisStatus(allow_partial=allow_partial)

    # Parse policy inputs once and embed their effective contents/hash. The VS
    # Code extension may auto-apply ~/.diffignore, so silently relying on a
    # machine-local file would otherwise make the evidence set irreproducible.
    ignore_patterns: list[str] = []
    ignore_file_sha256: str | None = None
    if ignore_file:
        try:
            ignore_bytes = Path(ignore_file).read_bytes()
            # utf-8-sig drops one leading BOM (Windows editors, PowerShell 5.1
            # Out-File), which str.strip() keeps; the SHA-256 below still covers
            # the raw bytes.
            ignore_text = ignore_bytes.decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"Cannot read ignore policy file: {exc}") from exc
        ignore_file_sha256 = hashlib.sha256(ignore_bytes).hexdigest()
        for line in ignore_text.splitlines():
            pat = line.strip()
            if pat and not pat.startswith("#"):
                ignore_patterns.append(pat)
        logger.info("Loaded %d ignore patterns from %s", len(ignore_patterns), ignore_file)

    target_files: set[str] | None = None
    filter_file_sha256: str | None = None
    if filter_json:
        try:
            filter_bytes = Path(filter_json).read_bytes()
            filter_data = json.loads(filter_bytes.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot read filter policy JSON: {exc}") from exc
        if not isinstance(filter_data, list) or not all(
            isinstance(item, str) for item in filter_data
        ):
            raise RuntimeError("Filter policy JSON must be an array of relative path strings")
        target_files = set()
        for item in filter_data:
            try:
                parts = _safe_relative_parts(item, label="filter selection")
            except SourceIntegrityError as exc:
                raise RuntimeError(f"Unsafe filter policy relative path: {item!r}") from exc
            target_files.add(PurePosixPath(*parts).as_posix())
        _reject_unencodable_names("filter selection path", target_files)
        filter_file_sha256 = hashlib.sha256(filter_bytes).hexdigest()

    collection_policy = CollectionPolicy(
        ignore_patterns=tuple(ignore_patterns),
        include_patterns=include_rules,
        sensitive_files=sensitive_files,
    )
    metadata = dataclasses.replace(
        metadata,
        sensitive_files=sensitive_files,
        sensitive_preset_version=(
            SENSITIVE_PRESET_VERSION if sensitive_files != "include" else None
        ),
        sensitive_preset_rules=(
            tuple(sensitive_preset_rules()) if sensitive_files != "include" else ()
        ),
        include_patterns=include_rules,
        bundle_sources=bundle_sources if bundle_path else "not-requested",
        ignore_patterns=tuple(ignore_patterns),
        ignore_file_sha256=ignore_file_sha256,
        filter_applied=target_files is not None,
        filter_paths=tuple(sorted(target_files or set())),
        filter_file_sha256=filter_file_sha256,
    )

    # Step 1: collect and match
    logger.info("Step 1: Collecting files")
    unreadable_errors: list[str] = []
    collection_errors_a: list[str] = []
    collection_errors_b: list[str] = []

    excluded_a: list[dict[str, str]] = []
    excluded_b: list[dict[str, str]] = []
    files_a = collect_files(
        dir_a,
        unreadable_list=collection_errors_a,
        policy=collection_policy,
        excluded_list=excluded_a,
    )
    files_b = collect_files(
        dir_b,
        unreadable_list=collection_errors_b,
        policy=collection_policy,
        excluded_list=excluded_b,
    )
    analysis_status.policy_excluded = [
        {"side": side, **item, "path": _disclosable_name(item["path"])}
        for side, items in (("A", excluded_a), ("B", excluded_b))
        for item in items
    ]
    analysis_status.exclusion_listing = uncompared_mode
    if analysis_status.policy_excluded:
        logger.info("  Excluded by policy: %d in A, %d in B", len(excluded_a), len(excluded_b))
    sensitive_found = [
        item for item in analysis_status.policy_excluded if item["source"] == "sensitive-preset"
    ]
    if sensitive_found and sensitive_files == "error":
        for item in sensitive_found:
            logger.error(
                "  Sensitive file %s:%s (rule %s)",
                item["side"],
                visible_controls(item["path"]),
                item["rule"],
            )
        raise RuntimeError(
            f"Sensitive files found ({len(sensitive_found)}); nothing was written. "
            "The files are listed above. Use --sensitive-files exclude to leave "
            "them out or --sensitive-files include to compare them."
        )
    collected_files_a = list(files_a)
    collected_files_b = list(files_b)
    logger.info("  Files collected: %d in A, %d in B", len(files_a), len(files_b))
    # Fail before hashing/analysis rather than crash in a report writer after it.
    _reject_unencodable_names("source A path", [*files_a, *collection_errors_a])
    _reject_unencodable_names("source B path", [*files_b, *collection_errors_b])

    collection_failures = [
        *(_collection_failure("A", dir_a, item) for item in collection_errors_a),
        *(_collection_failure("B", dir_b, item) for item in collection_errors_b),
    ]
    # Preserve deterministic ordering while collapsing duplicate diagnostics.
    collection_failures = [
        {"side": key[0], "path": key[1], "reason": key[2]}
        for key in sorted(
            {(item["side"], item["path"], item["reason"]) for item in collection_failures}
        )
    ]
    if collection_failures:
        analysis_status.collection_failed_files.extend(collection_failures)
        analysis_status.mark_incomplete("collection-file-skipped")
        unreadable_errors.extend(_format_collection_failures(collection_failures))
        if not allow_partial:
            _write_unreadable_log(
                unreadable_log,
                unreadable_errors,
                overwrite=False,
            )
            raise RuntimeError(
                f"Input collection was incomplete: {len(collection_failures)} "
                "file or directory entry was unreadable or skipped; refusing a "
                "complete report. Use --allow-partial to emit an explicitly "
                "incomplete report."
            )

    if target_files is not None:
        missing_filter_paths = sorted(target_files - set(files_a))
        if missing_filter_paths:
            excluded_here = {
                item["path"]: item for item in analysis_status.policy_excluded if item["side"] == "A"
            }
            policy_hits = [p for p in missing_filter_paths if p in excluded_here]
            if policy_hits:
                raise RuntimeError(
                    "Filter policy names paths that the collection policy excluded from "
                    "source A: "
                    + "; ".join(
                        f"{p} ({exclusion_reason(excluded_here[p])})" for p in policy_hits
                    )
                    + ". Change --ignore-file, --include or --sensitive-files to compare them."
                )
            raise RuntimeError(
                "Filter policy names paths missing from source A: "
                + ", ".join(missing_filter_paths)
            )

    # Step 2: compute file hashes (always)
    logger.info("Step 2: Computing SHA-256 digests of the input files")
    hashes_a = compute_file_hashes(dir_a, files_a)
    hashes_b = compute_file_hashes(dir_b, files_b)
    logger.info("  Files hashed: %d in A, %d in B", len(hashes_a), len(hashes_b))
    hashed_a = {entry.rel_path for entry in hashes_a}
    hashed_b = {entry.rel_path for entry in hashes_b}
    hash_failures = [
        {"side": "A", "path": rel, "reason": "hashing failed"}
        for rel in files_a
        if rel not in hashed_a
    ]
    hash_failures.extend(
        {"side": "B", "path": rel, "reason": "hashing failed"}
        for rel in files_b
        if rel not in hashed_b
    )
    if hash_failures:
        analysis_status.collection_failed_files.extend(hash_failures)
        analysis_status.mark_incomplete("collection-file-unhashed")
        unreadable_errors.extend(_format_collection_failures(hash_failures))
        if not allow_partial:
            _write_unreadable_log(
                unreadable_log,
                unreadable_errors,
                overwrite=False,
            )
            raise RuntimeError(
                f"Input hashing failed for {_plural(len(hash_failures), 'file')}; refusing "
                "a partial report. Use --allow-partial to emit an explicitly "
                "incomplete report."
            )
        # Only verified bytes may enter matching, analysis, or the manifest.
        files_a = [rel for rel in files_a if rel in hashed_a]
        files_b = [rel for rel in files_b if rel in hashed_b]

    matches, unmatched_a, unmatched_b = match_files(
        files_a,
        files_b,
        threshold=threshold,
    )
    logger.info(
        "  Matched pairs: %d; unmatched files: %d in A, %d in B",
        len(matches),
        len(unmatched_a),
        len(unmatched_b),
    )

    # Analysis, manifest, and bundle all consume this private snapshot, verified by
    # SHA-256 at creation, before analysis and before commit (it is not immutable).
    # The original roots are re-hashed after analysis so mid-run source changes
    # cannot silently produce a successful evidence artifact.
    snapshot_tmp = tempfile.TemporaryDirectory(prefix="diffinite_snapshot_")
    snapshot_base = Path(snapshot_tmp.name)
    # Until _OutputTransaction owns this directory, remove the plaintext source
    # copy here: on failure it must not wait for garbage collection.
    try:
        analysis_dir_a = create_immutable_snapshot(
            dir_a,
            files_a,
            hashes_a,
            str(snapshot_base / "source_a"),
        )
        analysis_dir_b = create_immutable_snapshot(
            dir_b,
            files_b,
            hashes_b,
            str(snapshot_base / "source_b"),
        )
        verify_snapshot_matches_manifest(analysis_dir_a, hashes_a, side="A")
        verify_snapshot_matches_manifest(analysis_dir_b, hashes_b, side="B")

        # Build hash table HTML if --hash requested
        hash_table_html: str | None = None
        if embed_hash:
            hash_table_html = build_hash_table_html(hashes_a, hashes_b)

        logger.info("Step 3: Comparing matched file pairs")
        # --- Restrict the analysis to the files named by --filter-json ---
        if target_files is not None:
            logger.info("  Selection filter: %s", filter_json)

            # Keep only matches where file A is in the target list
            matches = [m for m in matches if m.rel_path_a in target_files]
            # A selective report lists only the selected A files; the omitted
            # unmatched counts are disclosed in the analysis status, never
            # reported as 0.
            selected_unmatched_a = [fa for fa in unmatched_a if fa in target_files]
            analysis_status.filter_omitted_unmatched_a = len(unmatched_a) - len(
                selected_unmatched_a
            )
            analysis_status.filter_omitted_unmatched_b = len(unmatched_b)
            unmatched_a = selected_unmatched_a
            unmatched_b = []  # Omit from selective report (count disclosed above)
            logger.info("  Pairs selected by the filter: %d", len(matches))

        analysis_status.diff_requested_pair_count = len(matches)

        unit = "word" if by_word else "line"

        # Comment-rule extensions each channel will apply (--strip-comments):
        # a side with no rules borrows its matched partner's, in both channels.
        comment_pairs = [(m.rel_path_a, m.rel_path_b) for m in matches]
        if strip_comments:
            line_comment_exts = [
                ext
                for m in matches
                for ext in comment_extensions_for_pair(
                    Path(m.rel_path_a).suffix.lower(), Path(m.rel_path_b).suffix.lower()
                )
            ]
            metadata = dataclasses.replace(
                metadata,
                line_comment_unstripped_extensions=tuple(
                    extensions_without_comment_rules(line_comment_exts)
                ),
            )

        # Step 3: read, preprocess, diff, collect line counts (parallel)
        results: list[DiffResult] = []
        all_line_counts: list[int] = []
        excluded_pairs: list[dict[str, str]] = []

        num_workers = min(workers, len(matches)) if workers > 1 else 1
        if sys.platform == "win32":
            # CPython concurrent.futures.process._MAX_WINDOWS_WORKERS = 63 - 2:
            # ProcessPoolExecutor raises ValueError above this on Windows.
            num_workers = min(num_workers, 61)
        if num_workers <= 1:
            req, lines, errs, excl = _process_match_chunk(
                1,
                matches,
                analysis_dir_a,
                analysis_dir_b,
                encoding,
                binary_handling,
                strip_comments,
                squash_blanks,
                by_word,
                autojunk,
                metrics_only,
                collapse_identical,
                detect_moved,
                max_file_size_mb,
                normalize_ws=normalize_ws,
                max_diff_html_size_mb=max_diff_html_size_mb,
            )
            results.extend(req)
            all_line_counts.extend(lines)
            unreadable_errors.extend(errs)
            excluded_pairs.extend(excl)
        else:
            logger.info("  Worker processes: %d", num_workers)
            import concurrent.futures

            chunk_size = max(1, len(matches) // num_workers)
            chunks = [matches[i : i + chunk_size] for i in range(0, len(matches), chunk_size)]

            with concurrent.futures.ProcessPoolExecutor(
                max_workers=num_workers, initializer=_exit_when_parent_dies
            ) as executor:
                futures = []
                chunk_file_counts = []  # track how many files each worker was assigned
                for i, chunk in enumerate(chunks):
                    chunk_file_counts.append(len(chunk))
                    futures.append(
                        executor.submit(
                            _process_match_chunk,
                            i + 1,
                            chunk,
                            analysis_dir_a,
                            analysis_dir_b,
                            encoding,
                            binary_handling,
                            strip_comments,
                            squash_blanks,
                            by_word,
                            autojunk,
                            metrics_only,
                            collapse_identical,
                            detect_moved,
                            max_file_size_mb,
                            normalize_ws,
                            max_diff_html_size_mb,
                        )
                    )

                crashed_workers = 0
                lost_file_count = 0
                for idx, future in enumerate(futures):
                    try:
                        req, lines, errs, excl = future.result()
                        results.extend(req)
                        all_line_counts.extend(lines)
                        unreadable_errors.extend(errs)
                        excluded_pairs.extend(excl)
                    except Exception as exc:
                        crashed_workers += 1
                        lost = chunk_file_counts[idx]
                        lost_file_count += lost
                        logger.error(
                            "Worker %d stopped; %d file pairs are missing from the report: %s",
                            idx + 1,
                            lost,
                            exc,
                        )
                        for match in chunks[idx]:
                            analysis_status.diff_failed_pairs.append(
                                {
                                    "file_a": match.rel_path_a,
                                    "file_b": match.rel_path_b,
                                    "reason": f"worker-failure: {exc}",
                                }
                            )

                if lost_file_count > 0:
                    analysis_status.mark_incomplete("diff-worker-failure")
                    logger.warning(
                        "Incomplete analysis: %d worker processes stopped; %d of %d file "
                        "pairs are missing from the report.",
                        crashed_workers,
                        lost_file_count,
                        len(matches),
                    )
                if crashed_workers and not allow_partial:
                    raise RuntimeError(
                        f"Worker processes stopped: {crashed_workers}; file pairs missing: "
                        f"{lost_file_count}. Refusing a partial report. "
                        "Use --allow-partial to emit an explicitly incomplete report."
                    )

        total_files = len(results)
        # A pair with an error result (unreadable file, or a decode failure under
        # --binary-handling error) was never compared: it is a failed pair, not
        # a successful one, and the run is marked incomplete.
        for result in results:
            if result.error:
                analysis_status.diff_failed_pairs.append(
                    {
                        "file_a": result.match.rel_path_a,
                        "file_b": result.match.rel_path_b,
                        "reason": f"pair-error: {result.error}",
                    }
                )
                analysis_status.mark_incomplete("diff-pair-error")
        # Pairs left uncompared by --binary-handling exclude are disclosed
        # separately: requested = successful + failed + excluded.
        analysis_status.diff_excluded_pairs.extend(
            sorted(excluded_pairs, key=lambda item: (item["file_a"], item["file_b"]))
        )
        analysis_status.diff_successful_pair_count = (
            analysis_status.diff_requested_pair_count
            - len(analysis_status.diff_failed_pairs)
            - len(analysis_status.diff_excluded_pairs)
        )
        analysis_status.diff_truncated_count = sum(
            1 for result in results if result.html_diff_truncated
        )
        if analysis_status.diff_truncated_count:
            analysis_status.mark_incomplete("diff-payload-truncated")

        if not metrics_only:
            # Diagnostic only: each HTML diff page sizes its own line-number column
            # in the worker, so there is no single applied width to thread here.
            logger.debug("  Max line-number column width: %dpx", _compute_ln_col_width(all_line_counts))

        # ── Sort results ──────────────────────────────────────────────
        if sort_by:
            reverse = sort_order == "desc"
            if sort_by == "filename":
                results.sort(
                    key=lambda r: _natural_sort_key(PurePosixPath(r.match.rel_path_a).name),
                    reverse=reverse,
                )
            elif sort_by == "path":
                results.sort(key=lambda r: _natural_sort_key(r.match.rel_path_a), reverse=reverse)
            elif sort_by == "similarity":
                results.sort(key=lambda r: r.match.similarity, reverse=reverse)
            elif sort_by == "ratio":
                # Only difflib ratios are ranked. SHA-256-only and error pairs
                # have no difflib ratio; they follow, in their existing order.
                ranked = [r for r in results if not r.error and not r.binary]
                unranked = [r for r in results if r.error or r.binary]
                ranked.sort(key=lambda r: r.ratio, reverse=reverse)
                results[:] = ranked + unranked
            logger.info("  Sorted by %s (%s)", sort_by, sort_order)

        # Deep Compare (only in deep mode)
        deep_results = None
        if exec_mode == "deep":
            logger.info("Step 4: Running Deep Compare (every A file against every B file)")
            deep_status: dict = {}
            deep_files_a = (
                files_a if target_files is None else [path for path in files_a if path in target_files]
            )
            if deep_files_a or target_files is None:
                deep_results = run_deep_compare(
                    analysis_dir_a,
                    analysis_dir_b,
                    deep_files_a,
                    files_b,
                    k=kgram_size,
                    w=window_size,
                    workers=workers,
                    min_jaccard=min_jaccard,
                    normalize=normalize,
                    lang_aware=lang_aware,
                    max_index_entries=max_index_entries,
                    max_file_size_mb=max_file_size_mb,
                    strip_comments=strip_comments,
                    encoding=encoding,
                    allow_partial=allow_partial,
                    status=deep_status,
                    comment_pairs=comment_pairs,
                )
            else:
                deep_results = []
                deep_status.update(
                    {
                        "requested_file_count": 0,
                        "successful_file_count": 0,
                        "failed_files": [],
                        "index_truncated": False,
                    }
                )
            analysis_status.deep_requested_file_count = deep_status.get(
                "requested_file_count", len(deep_files_a) + len(files_b)
            )
            analysis_status.deep_successful_file_count = deep_status.get(
                "successful_file_count", analysis_status.deep_requested_file_count
            )
            analysis_status.deep_failed_files.extend(deep_status.get("failed_files", []))
            analysis_status.deep_skipped_binary_files.extend(
                deep_status.get("skipped_binary_files", [])
            )
            analysis_status.deep_unfingerprinted_files.extend(
                deep_status.get("unfingerprinted_files", [])
            )
            analysis_status.deep_lang_aware_fallback_files.extend(
                deep_status.get("lang_aware_fallback_files", [])
            )
            metadata = dataclasses.replace(
                metadata,
                deep_comment_unstripped_extensions=tuple(
                    deep_status.get("comment_unstripped_extensions", [])
                ),
                lang_aware_tiers=tuple(
                    (ext, tuple(tiers))
                    for ext, tiers in sorted(deep_status.get("lang_aware_tiers", {}).items())
                ),
            )
            if metadata.normalize:
                # The assessment depends on which extensions kept their comments,
                # known only now; recompute so the stored status matches the
                # disclosure (which re-assesses from this same metadata).
                reassessed = assess_normalize_metadata(metadata)
                if (
                    "strip_comments" in reassessed.profile_mismatches
                    and "strip_comments" not in metadata.calibration_profile_mismatches
                ):
                    # The CLI could not know these extensions before collection.
                    console_warning = threshold_console_warning(
                        reassessed,
                        metadata.threshold,
                        metadata.threshold_provenance,
                        comment_unstripped_extensions=metadata.deep_comment_unstripped_extensions,
                    )
                    if console_warning:
                        logger.warning("%s", console_warning)
                metadata = dataclasses.replace(
                    metadata,
                    calibration_profile_id=reassessed.profile_id,
                    calibration_status=reassessed.status,
                    calibration_profile_mismatches=reassessed.profile_mismatches,
                    calibration_threshold_matches=reassessed.threshold_matches,
                )
            # Stated in every report, so "ran, nothing reached the threshold"
            # (0) reads differently from "not run" (None, simple mode).
            analysis_status.deep_reported_pair_count = sum(
                len(dr.matched_files_b) for dr in deep_results
            )
            if analysis_status.deep_failed_files:
                analysis_status.mark_incomplete("deep-file-or-worker-failure")
            # Surface index truncation so a capped run is not read as complete.
            if deep_status.get("index_truncated") and metadata is not None:
                metadata = dataclasses.replace(metadata, deep_index_truncated=True)
                analysis_status.deep_index_truncated = True
                analysis_status.mark_incomplete("deep-index-truncated")
        elif exec_mode == "simple":
            logger.info("Step 4: Deep Compare not run (simple mode)")
    except BaseException:
        snapshot_tmp.cleanup()
        raise

    # ── Output generation ─────────────────────────────────────────────
    output_transaction = _OutputTransaction(
        output_targets,
        cleanup=snapshot_tmp.cleanup,
    )

    split_output_trees: list[str] = []
    obsolete_no_merge_paths: list[str] = []
    if no_merge and not metrics_only:
        for output_anchor, is_pdf in ((report_html, False), (report_pdf, True)):
            if not output_anchor:
                continue
            path = Path(output_anchor)
            split_output_trees.append(str(path.parent / f"{path.stem}_files"))
            obsolete_no_merge_paths.extend((str(path), f"{path}.sha256", f"{path}.sig"))
            if is_pdf:
                obsolete_no_merge_paths.append(str(path.with_suffix(".csv")))

        split_output_trees = list(dict.fromkeys(split_output_trees))
        obsolete_no_merge_paths = list(dict.fromkeys(obsolete_no_merge_paths))
        for stale_path in obsolete_no_merge_paths:
            output_transaction.run(_remove_stale_output_file, stale_path)
        for tree_path in split_output_trees:
            output_transaction.run(
                _prepare_split_output_tree,
                Path(tree_path),
                Path(manifest_path),
            )

    logger.info("Step 5: Writing reports")
    # JSON report
    if report_json:
        output_transaction.run(
            _generate_json_report,
            results,
            unmatched_a,
            unmatched_b,
            dir_a_disp,
            dir_b_disp,
            by_word,
            strip_comments,
            deep_results,
            report_json,
            metadata=metadata,
            analysis_status=analysis_status,
            normalize_ws=normalize_ws,
            uncompared_mode=uncompared_mode,
        )

    # Markdown report
    if report_md and not metrics_only:
        output_transaction.run(
            _generate_markdown_report,
            results,
            unmatched_a,
            unmatched_b,
            dir_a_disp,
            dir_b_disp,
            by_word,
            strip_comments,
            deep_results,
            report_md,
            metadata=metadata,
            analysis_status=analysis_status,
            uncompared_mode=uncompared_mode,
            file_hashes=(hashes_a, hashes_b) if embed_hash else None,
        )

    # HTML report
    if report_html and not metrics_only:
        if no_merge:
            logger.info("  Individual HTML reports")
            output_transaction.run(
                _generate_individual_html,
                results,
                unmatched_a,
                unmatched_b,
                dir_a_disp,
                dir_b_disp,
                by_word,
                strip_comments,
                deep_results,
                report_html,
                preserve_tree=preserve_tree,
                metadata=metadata,
                analysis_status=analysis_status,
                hash_table_html=hash_table_html,
                uncompared_mode=uncompared_mode,
            )
        else:
            output_transaction.run(
                _generate_html_report,
                results,
                unmatched_a,
                unmatched_b,
                dir_a_disp,
                dir_b_disp,
                by_word,
                strip_comments,
                deep_results,
                report_html,
                metadata=metadata,
                analysis_status=analysis_status,
                hash_table_html=hash_table_html,
                uncompared_mode=uncompared_mode,
            )

    # PDF report
    if report_pdf and not metrics_only:
        logger.info("  Writing the PDF report")
        output_transaction.run(
            _generate_pdf_report,
            results,
            unmatched_a,
            unmatched_b,
            dir_a_disp,
            dir_b_disp,
            by_word,
            strip_comments,
            deep_results,
            report_pdf,
            no_merge=no_merge,
            preserve_tree=preserve_tree,
            show_page_number=show_page_number,
            show_file_number=show_file_number,
            show_bates_number=show_bates_number,
            show_filename=show_filename,
            unit=unit,
            total_files=total_files,
            metadata=metadata,
            analysis_status=analysis_status,
            hash_table_html=hash_table_html,
            bates_prefix=bates_prefix,
            bates_suffix=bates_suffix,
            bates_start=bates_start,
            include_uncompared=uncompared_mode == "inline",
            uncompared_mode=uncompared_mode,
            pdf_font=pdf_font,
            pdf_lang=pdf_lang,
        )

    logger.info("  Reports written")

    # ── Report Integrity Checksums (SHA-256) ────────────────────────
    checksum_targets = () if metrics_only or no_merge else (report_pdf, report_html)
    output_transaction.run(_write_report_checksum_sidecars, checksum_targets)
    # The Markdown and JSON reports get no sidecar (the manifest lists them),
    # but their digests are printed like those of the PDF and HTML.
    digest_only: tuple[str | None, ...] = (
        (report_json,) if metrics_only else (report_json, report_md)
    )
    if report_pdf and not metrics_only and not no_merge:
        # The merged PDF's exhibit index is a report file too.
        digest_only += (str(Path(report_pdf).with_suffix(".csv")),)
    output_transaction.run(_log_report_digests, digest_only)

    # ── Write uncompared files to separate file ───────────────────
    separate_uncompared_path: str | None = None
    if uncompared_mode == "separate":
        # Derive filename from first available report path
        first_report = next(
            (p for p in [report_pdf, report_html, report_md, report_json] if p),
            "report",
        )
        sep_path = str(Path(first_report).with_name(Path(first_report).stem + "_uncompared.txt"))
        separate_uncompared_path = sep_path
        omitted_note = _selection_omitted_note(analysis_status)
        if unmatched_a or unmatched_b or omitted_note or analysis_status.policy_excluded:
            output_transaction.run(
                _write_uncompared_file,
                sep_path,
                unmatched_a,
                unmatched_b,
                dir_a_disp,
                dir_b_disp,
                omitted_note,
                analysis_status.policy_excluded,
            )
            logger.info("  Uncompared files list: %s", sep_path)
        else:
            output_transaction.run(_remove_stale_output_file, sep_path)
            separate_uncompared_path = None

    # ── 4) Write Unreadable Log (Forensics) ─────────────────────────
    current_unreadable_log: str | None = None
    if unreadable_log:
        if unreadable_errors:
            logger.warning(
                "Files that could not be read: %d",
                len(unreadable_errors),
            )
            output_transaction.run(
                _write_unreadable_log,
                unreadable_log,
                unreadable_errors,
            )
            current_unreadable_log = unreadable_log
        else:
            output_transaction.run(_remove_stale_output_file, unreadable_log)

    # ── Evidence integrity (always) ───────────────────────────────────
    all_report_paths = output_transaction.run(
        _collect_report_artifacts,
        report_pdf,
        report_html,
        report_md,
        report_json,
        results=results,
        preserve_tree=preserve_tree,
        no_merge=no_merge,
        metrics_only=metrics_only,
        separate_uncompared_path=separate_uncompared_path,
        current_unreadable_log=current_unreadable_log,
    )

    manifest_status = output_transaction.run(analysis_status.to_dict)
    manifest_configuration = output_transaction.run(
        _analysis_metadata_dict, metadata, analysis_status
    )
    manifest_environment = output_transaction.run(_environment_dict, metadata, analysis_status)
    output_transaction.run(
        write_manifest,
        dir_a,
        dir_b,
        hashes_a,
        hashes_b,
        all_report_paths,
        manifest_path,
        root_label_a=dir_a_disp,
        root_label_b=dir_b_disp,
        analysis_status=manifest_status,
        analysis_configuration=manifest_configuration,
        split_roots=split_output_trees,
        environment=manifest_environment,
    )
    manifest_digest = output_transaction.run(_sha256_file, manifest_path)

    # Evidence bundle (--bundle) — driven by the exact hashed file set so the
    # ZIP contents always match the integrity manifest.
    bundle_digest: str | None = None
    if bundle_path:
        logger.info("Step 6: Creating the evidence bundle")
        bundle_digest = output_transaction.run(
            create_evidence_bundle,
            analysis_dir_a,
            analysis_dir_b,
            [h.rel_path for h in hashes_a],
            [h.rel_path for h in hashes_b],
            manifest_path,
            all_report_paths,
            bundle_path,
            split_roots=split_output_trees,
            include_sources=bundle_sources == "full",
        )

    # Verify as late as possible, while the output transaction can still restore
    # the complete prior artifact set.  This catches added/removed entries as well
    # as byte changes that occur during analysis or report/bundle generation.
    source_changes = output_transaction.run(
        _verify_source_state,
        "A",
        dir_a,
        collected_files_a,
        hashes_a,
        collection_failures,
        collection_policy,
        analysis_status.policy_excluded,
    )
    source_changes.extend(
        output_transaction.run(
            _verify_source_state,
            "B",
            dir_b,
            collected_files_b,
            hashes_b,
            collection_failures,
            collection_policy,
            analysis_status.policy_excluded,
        )
    )
    if source_changes:
        try:
            raise SourceIntegrityError(
                "Source changed during analysis; no successful report/bundle was produced: "
                + ", ".join(source_changes)
            )
        except SourceIntegrityError:
            output_transaction.rollback()
            raise

    output_transaction.run(
        verify_snapshot_matches_manifest,
        analysis_dir_a,
        hashes_a,
        side="A",
    )
    output_transaction.run(
        verify_snapshot_matches_manifest,
        analysis_dir_b,
        hashes_b,
        side="B",
    )
    output_transaction.run(
        _verify_published_evidence,
        manifest_path,
        all_report_paths,
        manifest_digest,
        bundle_path,
        bundle_digest,
        split_output_trees=split_output_trees,
        absent_paths=obsolete_no_merge_paths,
    )

    output_transaction.commit()
    logger.info("Done")


# ---------------------------------------------------------------------------
# PDF report (extracted from old pipeline)
# ---------------------------------------------------------------------------
def _generate_pdf_report(
    results: list[DiffResult],
    unmatched_a: list[str],
    unmatched_b: list[str],
    dir_a: str,
    dir_b: str,
    by_word: bool,
    strip_comments: bool,
    deep_results: list[DeepMatchResult] | None,
    output_pdf: str,
    *,
    no_merge: bool,
    preserve_tree: bool = True,
    show_page_number: bool,
    show_file_number: bool,
    show_bates_number: bool,
    show_filename: bool,
    unit: str,
    total_files: int,
    metadata: AnalysisMetadata | None = None,
    analysis_status: AnalysisStatus | None = None,
    hash_table_html: str | None = None,
    bates_prefix: str = "",
    bates_suffix: str = "",
    bates_start: int = 1,
    include_uncompared: bool = True,
    uncompared_mode: str = "inline",
    pdf_font: str | None = None,
    pdf_lang: str | None = None,
) -> None:
    """Generate PDF report with divide-and-conquer merging."""
    final_out_dir: Path | None = None
    if no_merge:
        out_stem = Path(output_pdf).stem
        final_out_dir = Path(output_pdf).parent / f"{out_stem}_files"
        final_out_dir.parent.mkdir(parents=True, exist_ok=True)
        logger.info("  No-merge mode: individual PDFs in %s", final_out_dir.resolve())

    with tempfile.TemporaryDirectory(prefix="diffinite_") as tmpdir:
        if no_merge:
            out_dir = Path(tmpdir) / "individual"
            out_dir.mkdir(parents=True, exist_ok=True)

        # (1) Cover page
        cover_body = build_cover_body(
            results,
            unmatched_a,
            unmatched_b,
            dir_a,
            dir_b,
            by_word,
            strip_comments,
            deep_results=deep_results,
            metadata=metadata,
            analysis_status=analysis_status,
            hash_table_html=hash_table_html,
            include_uncompared=uncompared_mode == "inline",
            uncompared_mode=uncompared_mode,
            conventions=pdf_conventions(
                show_page_number=show_page_number,
                show_file_number=show_file_number,
                show_filename=show_filename,
                show_bates_number=show_bates_number,
                bates_prefix=bates_prefix,
                bates_suffix=bates_suffix,
                bates_start=bates_start,
            ),
        )
        cover_annotation, cover_footer, cover_header = _build_annotation_html(
            show_page_number=show_page_number
        )
        cover_html = _html_wrap(
            "Diffinite: Cover and Summary",
            cover_body,
            annotation_html=cover_annotation,
            has_footer=cover_footer,
            has_header=cover_header,
            pdf_font=pdf_font,
            pdf_lang=pdf_lang,
        )
        if no_merge:
            cover_dest = str(out_dir / "000_cover.pdf")  # type: ignore[possibly-undefined]
        else:
            cover_dest = os.path.join(tmpdir, "00_cover.pdf")
        cover_ok = html_to_pdf(cover_html, cover_dest)
        if cover_ok:
            logger.info("  Cover page done")

        # ── Pre-flight: warn about large diffs that may slow PDF ────
        # 500 KB of HTML ≈ 500+ source lines in side-by-side diff table.
        # xhtml2pdf layout becomes noticeably slow above this threshold.
        _LARGE_DIFF_BYTES = 500_000
        large_files = [
            (i, r)
            for i, r in enumerate(results, 1)
            if not r.error and not r.binary and len(r.html_diff) > _LARGE_DIFF_BYTES
        ]
        if large_files:
            logger.warning(
                "%d files have large diffs; PDF rendering may be slow or stop responding:",
                len(large_files),
            )
            for i, r in large_files:
                logger.warning(
                    "  %d. %s (%s of HTML)",
                    i,
                    r.match.rel_path_a,
                    size_label(len(r.html_diff)),
                )
            logger.warning(
                "  Options: --collapse-identical (shorter diffs), --no-merge "
                "(one PDF per pair) or --report-html (faster export)."
            )

        # (2) Per-file diff pages
        diff_pdf_pairs: list[tuple[str, DiffResult]] = []
        for idx, r in enumerate(results, 1):
            # Per-file warning for large diffs
            if not r.error and not r.binary and len(r.html_diff) > _LARGE_DIFF_BYTES:
                logger.warning(
                    "  Rendering PDF %d of %d (%s, %s of HTML); this may take a while",
                    idx,
                    len(results),
                    r.match.rel_path_a,
                    size_label(len(r.html_diff)),
                )

            diff_html = build_diff_page_html(
                r,
                idx,
                unit,
                show_page_number=show_page_number,
                show_file_number=show_file_number,
                total_files=total_files,
                show_filename=show_filename,
                pdf_font=pdf_font,
                pdf_lang=pdf_lang,
            )
            safe_name = Path(r.match.rel_path_a).name.replace(" ", "_")
            if no_merge:
                if preserve_tree:
                    rel = PurePosixPath(r.match.rel_path_a)
                    entry = out_dir / "entries" / str(rel).replace("/", os.sep)  # type: ignore[possibly-undefined]
                    diff_dest = f"{entry}.pdf"
                    Path(diff_dest).parent.mkdir(parents=True, exist_ok=True)
                else:
                    diff_dest = str(out_dir / f"{idx:03d}_{safe_name}.pdf")  # type: ignore[possibly-undefined]
            else:
                diff_dest = os.path.join(tmpdir, f"{idx:03d}_diff.pdf")
            if html_to_pdf(diff_html, diff_dest):
                diff_pdf_pairs.append((diff_dest, r))
                logger.info("  Diff page %d (%s) done", idx, r.match.rel_path_a)
            else:
                logger.warning("  Diff page %d failed", idx)

        failed_parts = (0 if cover_ok else 1) + (len(results) - len(diff_pdf_pairs))
        if failed_parts:
            raise RuntimeError(
                f"PDF rendering failed for {_plural(failed_parts, 'report part')}; "
                "no successful PDF report or manifest was produced"
            )

        # (3) Merge with bookmarks or individual PDFs
        if no_merge:
            if show_bates_number:
                _apply_bates_to_individual(
                    [cover_dest] + [p for p, _ in diff_pdf_pairs],
                    start=bates_start,
                    prefix=bates_prefix,
                    suffix=bates_suffix,
                )
            assert final_out_dir is not None
            shutil.copytree(out_dir, final_out_dir, dirs_exist_ok=True)
            logger.info("  No-merge mode: %d PDFs saved", 1 + len(diff_pdf_pairs))
        else:
            exhibit_data = merge_with_bookmarks(
                cover_dest,
                diff_pdf_pairs,
                output_pdf,
            )
            if show_bates_number:
                logger.info("  Stamping Bates numbers")
                # Stage the temp on the SAME volume as output_pdf. tmpdir is on
                # the system drive, so os.replace(output_pdf, tmpdir/...) is a
                # cross-volume move that raises WinError 17 on Windows when the
                # user's -o path is on another drive.
                bates_tmp = str(
                    Path(output_pdf).with_name(Path(output_pdf).stem + ".bates_tmp.pdf")
                )
                os.replace(output_pdf, bates_tmp)
                try:
                    add_bates_numbers(
                        bates_tmp,
                        output_pdf,
                        start=bates_start,
                        prefix=bates_prefix,
                        suffix=bates_suffix,
                    )
                finally:
                    Path(bates_tmp).unlink(missing_ok=True)

            # Write CSV Exhibit Index
            try:
                csv_path = str(Path(output_pdf).with_suffix(".csv"))
                import csv
                from pypdf import PdfReader as _PR

                total_pages = len(_PR(output_pdf).pages)
                digits = max(4, len(str(bates_start + total_pages - 1)))

                with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    col_header = "Bates range" if show_bates_number else "Page range"
                    # "Name similarity" = fuzzy filename similarity; "Line/Word match" =
                    # difflib ratio over the comparison unit (word under --by-word). Keeping
                    # them in separate, explicitly-labelled columns prevents reading a 100%
                    # filename match as identical file content. Values carry the % sign.
                    writer.writerow(
                        [
                            "Index",
                            "File A",
                            "File B",
                            "Name similarity",
                            f"{'Word' if by_word else 'Line'} match",
                            col_header,
                        ]
                    )

                    # merge_with_bookmarks rows do not carry the error / hash
                    # reason, so look the result up by its pair.
                    result_by_pair = {
                        (r.match.rel_path_a, r.match.rel_path_b): r for _p, r in diff_pdf_pairs
                    }
                    for row_idx, row in enumerate(exhibit_data, 1):
                        start_page = row["start_page"]
                        end_page = row["end_page"]
                        if show_bates_number:
                            bs_num = bates_start + start_page - 1
                            be_num = bates_start + end_page - 1
                            bs = f"{bates_prefix}{str(bs_num).zfill(digits)}{bates_suffix}"
                            be = f"{bates_prefix}{str(be_num).zfill(digits)}{bates_suffix}"
                            range_str = bs if bs == be else f"{bs} to {be}"
                        else:
                            range_str = (
                                str(start_page)
                                if start_page == end_page
                                else f"{start_page} to {end_page}"
                            )

                        # Content match: a percentage only when difflib ran. An
                        # error pair was never compared; a SHA-256-only pair has
                        # just the hash verdict.
                        pair_result = result_by_pair.get((row["file_a"], row["file_b"]))
                        error = row.get("error") or (pair_result.error if pair_result else None)
                        hash_label = hash_only_label(pair_result) if pair_result else None
                        if error:
                            content_str = _csv_safe_cell(f"Not compared ({error})")
                        elif hash_label is not None:
                            content_str = hash_label
                        elif row.get("binary"):
                            content_str = "Not compared by difflib; SHA-256 " + (
                                "identical" if row.get("hash_match") else "different"
                            )
                        else:
                            content_str = line_match_label(row.get("ratio", 0.0))

                        writer.writerow(
                            [
                                row_idx,
                                _csv_safe_cell(row["file_a"]),
                                _csv_safe_cell(row["file_b"]),
                                name_similarity_label(row["sim"]),
                                content_str,
                                _csv_safe_cell(range_str),
                            ]
                        )
                logger.info("  Exhibit index CSV: %s", csv_path)
            except Exception as e:
                raise RuntimeError(f"Failed to generate the PDF Exhibit Index CSV: {e}") from e


def _apply_bates_to_individual(
    pdf_paths: list[str],
    *,
    start: int = 1,
    prefix: str = "",
    suffix: str = "",
) -> None:
    """Stamp sequential Bates numbers across individual PDFs."""
    from pypdf import PdfReader as _PR

    page_counts = []
    for p in pdf_paths:
        try:
            page_counts.append(len(_PR(p).pages))
        except Exception as exc:
            raise RuntimeError(
                f"Cannot read rendered PDF before Bates stamping: {Path(p).name}"
            ) from exc

    total = sum(page_counts)
    digits = max(4, len(str(start + total - 1)))
    offset = start
    for p, pc in zip(pdf_paths, page_counts):
        if pc == 0:
            continue
        stamp_bates_inplace(p, offset, digits, prefix=prefix, suffix=suffix)
        offset += pc
