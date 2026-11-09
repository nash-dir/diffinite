"""Diffinite 유사도 메트릭 및 증거 무결성.

Winnowing 핑거프린트 기반 Jaccard 유사도를 계산하고,
분석 대상 파일의 SHA-256 해시 기록, 매니페스트 생성, 증거 번들링을 수행한다.

이 모듈은 "얼마나 비슷한가"만 계산한다.
"어떤 유형의 복제인가"는 판단하지 않는다 (감정인의 몫).

증거 무결성:
    - ``compute_file_hashes()``: 디렉토리 내 파일의 SHA-256 해시 계산
    - ``write_manifest()``: ``manifest.sha256.json`` 생성  (항상 실행)
    - ``create_evidence_bundle()``: 증거 번들 zip + zip 해시 생성

의존:
    - 표준 라이브러리: hashlib, json, zipfile, datetime
    - ``models.FileHashEntry``: 해시 결과 데이터클래스

호출관계:
    ``pipeline.run_pipeline()`` → ``compute_file_hashes()``
    ``pipeline.run_pipeline()`` → ``write_manifest()``
    ``pipeline.run_pipeline()`` → ``create_evidence_bundle()``  (``--bundle`` 시)
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import shutil
import stat
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

from diffinite.models import FileHashEntry
from diffinite import __version__

logger = logging.getLogger(__name__)

# SHA-256 버퍼 크기 (64KB). 대형 파일에서도 메모리 효율적.
_HASH_BUF_SIZE = 65536


class SourceIntegrityError(RuntimeError):
    """Raised when source bytes no longer match the analysis snapshot."""


def _validate_archive_path(path: str, *, label: str) -> None:
    """Reject paths that could escape or be reinterpreted during ZIP extraction."""
    logical = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or logical.is_absolute()
        or logical.as_posix() != path
        or any(part in {".", ".."} for part in logical.parts)
        or (logical.parts and ":" in logical.parts[0])
    ):
        raise SourceIntegrityError(f"Unsafe {label} archive path: {path!r}")


def _path_is_redirect(path: Path) -> bool:
    """Return whether *path* is a symlink or a Windows junction."""
    if path.is_symlink():
        return True
    # Path.is_junction() exists only from Python 3.12. The reparse tag gives the
    # same answer on every supported version, and matching the mount-point tag
    # exactly keeps other reparse points (e.g. OneDrive placeholders) allowed.
    try:
        reparse_tag = getattr(os.lstat(path), "st_reparse_tag", 0)
    except OSError:
        return False
    return reparse_tag != 0 and reparse_tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", None)


def _lexical_absolute(path: str | Path) -> Path:
    """Return an absolute path without dereferencing any path component."""
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _reject_redirecting_components(path: Path, *, label: str) -> None:
    """Reject existing symlink/junction components in an output path."""
    absolute = _lexical_absolute(path)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if _path_is_redirect(current):
            raise SourceIntegrityError(f"Unsafe {label} path uses a symlink or junction: {current}")


def _reject_descendant_redirects(root: Path, path: Path, *, label: str) -> None:
    """Reject redirects below an already-resolved trusted root."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise SourceIntegrityError(f"Unsafe {label} path escapes its root: {path}") from exc
    current = root
    for part in relative.parts:
        current /= part
        if _path_is_redirect(current):
            raise SourceIntegrityError(f"Unsafe {label} path uses a symlink or junction: {current}")


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def _safe_relative_parts(rel_path: str, *, label: str) -> tuple[str, ...]:
    _validate_archive_path(rel_path, label=label)
    return PurePosixPath(rel_path).parts


def _resolve_contained_file(root: Path, rel_path: str, *, label: str) -> Path:
    """Resolve one safe relative regular file without crossing a redirect."""
    parts = _safe_relative_parts(rel_path, label=label)
    candidate = root.joinpath(*parts)
    _reject_descendant_redirects(root, candidate, label=label)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise SourceIntegrityError(f"Unsafe {label} path escapes its root: {rel_path}")
    return resolved


def _logical_report_paths(report_paths: list[str]) -> list[tuple[Path, str]]:
    """Map report files to stable, privacy-safe manifest/archive names."""
    used: set[str] = {"manifest.sha256.json"}
    mapped: list[tuple[Path, str]] = []
    for report_path in report_paths:
        path = Path(report_path)
        split_root = next(
            (parent for parent in path.parents if parent.name.endswith("_files")),
            None,
        )
        if split_root is not None:
            logical = f"{split_root.name}/{path.relative_to(split_root).as_posix()}"
        else:
            logical = path.name
        top_level = PurePosixPath(logical).parts[0]
        if top_level in {"source_a", "source_b", "reports"}:
            logical = f"reports/{logical}"

        candidate = logical
        suffix_index = 1
        while candidate in used:
            logical_path = Path(logical)
            candidate = (
                logical_path.parent / f"{logical_path.stem}_{suffix_index}{logical_path.suffix}"
            ).as_posix()
            suffix_index += 1
        used.add(candidate)
        mapped.append((path, candidate))
    return mapped


def jaccard_similarity(fp_a: set[int], fp_b: set[int]) -> float:
    """Jaccard similarity of two Winnowing fingerprint sets: |A∩B| / |A∪B|.

    Reported as "N% of the two files' code fingerprints match."
    Returns 0.0 when both sets are empty.
    """
    if not fp_a and not fp_b:
        return 0.0
    intersection = len(fp_a & fp_b)
    union = len(fp_a | fp_b)
    return intersection / union if union else 0.0


# ---------------------------------------------------------------------------
# SHA-256 해시 계산
# ---------------------------------------------------------------------------
def _sha256_file(filepath: str | Path) -> str:
    """단일 파일의 SHA-256 hex digest를 반환한다.

    64KB 버퍼로 분할 읽기하여 대형 파일에서도 메모리를 일정하게 유지.
    """
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(_HASH_BUF_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def compute_file_hashes(
    root_dir: str,
    file_list: list[str],
) -> list[FileHashEntry]:
    """디렉토리 내 파일 목록의 SHA-256 해시를 일괄 계산한다.

    Args:
        root_dir: 기준 디렉토리 절대경로.
        file_list: ``root_dir`` 기준 POSIX 상대경로 목록
                   (``collector.collect_files()`` 출력).

    Returns:
        ``FileHashEntry`` 리스트 (상대경로 기준 정렬).
        읽기 실패 파일은 건너뛰고 경고 로그를 남긴다.
    """
    root = Path(root_dir).resolve()
    entries: list[FileHashEntry] = []

    for rel_path in sorted(file_list):
        try:
            abs_path = _resolve_contained_file(
                root,
                rel_path,
                label="source file",
            )
            stat = abs_path.stat()
            sha = _sha256_file(abs_path)
            mtime = datetime.datetime.fromtimestamp(
                stat.st_mtime,
                tz=datetime.timezone.utc,
            ).isoformat()
            entries.append(
                FileHashEntry(
                    rel_path=rel_path,
                    sha256=sha,
                    size_bytes=stat.st_size,
                    modified_at=mtime,
                )
            )
        except SourceIntegrityError:
            raise
        except (OSError, IOError) as e:
            logger.warning("Hash computation failed for %s: %s", rel_path, e)

    return entries


def create_immutable_snapshot(
    root_dir: str,
    file_list: list[str],
    expected_hashes: list[FileHashEntry],
    snapshot_dir: str,
) -> str:
    """Copy the collected file set and verify every copied byte against its hash.

    The verified copy is the only source subsequently used for diffing,
    fingerprinting, and evidence bundling. A change between initial hashing and
    snapshot creation therefore fails closed instead of mixing byte versions.

    Despite the historical function name, the snapshot is **not immutable**: it is
    a private temp-directory copy the process owner can write to. Its integrity
    comes from SHA-256 verification at creation, again before analysis and again
    before output is committed (``verify_snapshot_matches_manifest``).
    """
    try:
        root = Path(root_dir).resolve(strict=True)
    except OSError as exc:
        raise SourceIntegrityError(f"Cannot resolve snapshot source root: {exc}") from exc
    if not root.is_dir():
        raise SourceIntegrityError(f"Snapshot source root is not a directory: {root}")

    destination_lexical = _lexical_absolute(snapshot_dir)
    _reject_redirecting_components(destination_lexical, label="snapshot output")
    destination = destination_lexical.resolve(strict=False)
    if _paths_overlap(root, destination):
        raise SourceIntegrityError(f"Snapshot output overlaps its source root: {destination}")
    if destination.exists() and not destination.is_dir():
        raise SourceIntegrityError(f"Snapshot output exists but is not a directory: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    expected = {entry.rel_path: entry for entry in expected_hashes}

    missing_hashes = sorted(set(file_list) - set(expected))
    if missing_hashes:
        raise SourceIntegrityError(
            "Integrity snapshot cannot be created because hashing failed for: "
            + ", ".join(missing_hashes)
        )

    for rel_path in sorted(file_list):
        try:
            source = _resolve_contained_file(
                root,
                rel_path,
                label="snapshot source",
            )
        except OSError as exc:
            raise SourceIntegrityError(
                f"Integrity snapshot source is unavailable: {rel_path}"
            ) from exc
        parts = _safe_relative_parts(rel_path, label="snapshot destination")
        target = destination.joinpath(*parts)
        _reject_descendant_redirects(destination, target, label="snapshot destination")
        resolved_parent = target.parent.resolve(strict=False)
        if not resolved_parent.is_relative_to(destination):
            raise SourceIntegrityError(f"Snapshot destination escapes its root: {rel_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, target)
            copied_digest = _sha256_file(target)
        except OSError as exc:
            raise SourceIntegrityError(
                f"Integrity snapshot failed while copying {rel_path}: {exc}"
            ) from exc
        if copied_digest != expected[rel_path].sha256:
            raise SourceIntegrityError(
                f"Source changed after hashing and before snapshot: {rel_path}"
            )

    return str(destination)


def verify_snapshot_matches_manifest(
    snapshot_dir: str,
    expected_hashes: list[FileHashEntry],
    *,
    side: str,
) -> None:
    """Fail unless a private analysis snapshot still matches its source manifest.

    The snapshot is writable by the process owner on supported platforms, so the
    initial copy verification alone cannot establish which bytes workers later
    consumed.  Verify both the complete regular-file set and every SHA-256 before
    analysis and again before publishing a successful evidence set.
    """
    lexical_root = _lexical_absolute(snapshot_dir)
    _reject_redirecting_components(lexical_root, label=f"snapshot {side}")
    try:
        root = lexical_root.resolve(strict=True)
    except OSError as exc:
        raise SourceIntegrityError(f"Analysis snapshot {side} is unavailable: {exc}") from exc
    if not root.is_dir() or _path_is_redirect(root):
        raise SourceIntegrityError(f"Analysis snapshot {side} is not a safe directory")

    expected: dict[str, FileHashEntry] = {}
    for entry in expected_hashes:
        _safe_relative_parts(entry.rel_path, label=f"snapshot {side} manifest entry")
        if entry.rel_path in expected:
            raise SourceIntegrityError(
                f"Analysis snapshot {side} manifest contains a duplicate path: {entry.rel_path}"
            )
        expected[entry.rel_path] = entry

    actual: dict[str, Path] = {}

    def _walk_error(error: OSError) -> None:
        raise SourceIntegrityError(f"Cannot enumerate analysis snapshot {side}: {error}") from error

    for dirpath, dirnames, filenames in os.walk(
        root,
        topdown=True,
        onerror=_walk_error,
        followlinks=False,
    ):
        parent = Path(dirpath)
        for name in dirnames:
            directory = parent / name
            if _path_is_redirect(directory):
                raise SourceIntegrityError(
                    f"Analysis snapshot {side} contains a redirecting directory"
                )
        for name in filenames:
            path = parent / name
            relative = path.relative_to(root).as_posix()
            try:
                stat_result = path.stat()
            except OSError as exc:
                raise SourceIntegrityError(
                    f"Cannot inspect analysis snapshot {side} file: {relative}"
                ) from exc
            if _path_is_redirect(path) or not path.is_file() or stat_result.st_nlink > 1:
                raise SourceIntegrityError(
                    f"Analysis snapshot {side} contains an unsafe file: {relative}"
                )
            actual[relative] = path

    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    if missing or unexpected:
        raise SourceIntegrityError(
            f"Analysis snapshot {side} file set changed: missing={missing}, unexpected={unexpected}"
        )

    changed: list[str] = []
    for relative, entry in expected.items():
        path = actual[relative]
        try:
            if path.stat().st_size != entry.size_bytes or _sha256_file(path) != entry.sha256:
                changed.append(relative)
        except OSError as exc:
            raise SourceIntegrityError(
                f"Cannot verify analysis snapshot {side} file: {relative}"
            ) from exc
    if changed:
        raise SourceIntegrityError(
            f"Analysis snapshot {side} bytes changed: {', '.join(sorted(changed))}"
        )


def verify_sources_unchanged(
    root_dir: str,
    expected_hashes: list[FileHashEntry],
) -> list[str]:
    """Return relative paths whose current bytes differ from initial hashes."""
    root = Path(root_dir).resolve()
    changed: list[str] = []
    for entry in expected_hashes:
        try:
            source = _resolve_contained_file(
                root,
                entry.rel_path,
                label="source verification",
            )
            current = _sha256_file(source)
        except (OSError, SourceIntegrityError):
            changed.append(entry.rel_path)
            continue
        if current != entry.sha256:
            changed.append(entry.rel_path)
    return changed


# ---------------------------------------------------------------------------
# 매니페스트 생성 (항상 실행)
# ---------------------------------------------------------------------------
def write_manifest(
    dir_a: str,
    dir_b: str,
    hashes_a: list[FileHashEntry],
    hashes_b: list[FileHashEntry],
    report_paths: list[str],
    output_path: str,
    root_label_a: Optional[str] = None,
    root_label_b: Optional[str] = None,
    analysis_status: Optional[dict] = None,
    analysis_configuration: Optional[dict] = None,
) -> str:
    """``manifest.sha256.json``을 생성한다.

    모든 분석 실행에서 무조건 생성되며, 분석 대상 파일과
    생성된 리포트의 SHA-256 해시를 기록한다.

    Args:
        report_paths: 이번 실행에서 생성된 리포트 파일 경로 목록. 누락·빈 파일·
            심볼릭 링크/정션이 있으면 불완전한 매니페스트를 쓰지 않고 실패한다.
        output_path: 매니페스트 JSON 저장 경로.
        root_label_a / root_label_b: 매니페스트에 기록할 소스 루트 표시명.
            지정하지 않으면 **베이스네임**을 사용한다 — 해석된 절대경로를 그대로
            기록하면 OS 사용자명·내부 디렉토리 구조·클라이언트 식별자 등이
            (보통 의도치 않게) 디스커버리 산출물로 노출되기 때문이다.
            사람이 읽는 리포트가 쓰는 alias(``dir_alias_*``)와 일치시킨다.
        analysis_configuration: 실제 적용된 분석·수집 정책. 로컬 설정 파일의
            절대경로 대신 유효 규칙과 원본 SHA-256을 기록한다.

    Returns:
        생성된 매니페스트 파일의 절대경로.
    """
    out = _lexical_absolute(output_path)
    _reject_redirecting_components(out, label="manifest output")
    resolved_out = out.resolve(strict=False)
    if out.exists() and not out.is_file():
        raise SourceIntegrityError(f"Manifest output is not a regular file: {out}")
    source_roots = (
        _lexical_absolute(dir_a).resolve(strict=False),
        _lexical_absolute(dir_b).resolve(strict=False),
    )
    if any(_paths_overlap(resolved_out, root) for root in source_roots):
        raise SourceIntegrityError(f"Manifest output overlaps a source root: {resolved_out}")

    # 리포트 파일 해시
    report_entries = []
    for p, logical_path in _logical_report_paths(report_paths):
        lexical_report = _lexical_absolute(p)
        _reject_redirecting_components(lexical_report, label="manifest report input")
        if lexical_report == out or lexical_report.resolve(strict=False) == resolved_out:
            raise SourceIntegrityError(
                f"Manifest output collides with a report artifact: {logical_path}"
            )
        try:
            resolved_report = lexical_report.resolve(strict=True)
            st = resolved_report.stat()
        except OSError as exc:
            raise SourceIntegrityError(
                f"Cannot read generated report artifact: {logical_path}"
            ) from exc
        if not resolved_report.is_file() or st.st_size <= 0:
            raise SourceIntegrityError(
                f"Generated report artifact is missing, empty, or not regular: {logical_path}"
            )
        report_entries.append(
            {
                "path": logical_path,
                "sha256": _sha256_file(resolved_report),
                "size_bytes": st.st_size,
            }
        )

    manifest = {
        "tool": "diffinite",
        "version": __version__,
        "created_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "integrity_note": (
            "Integrity is checked by comparing the per-file sha256 values below "
            "with an independently kept copy; this manifest is not signed. "
            "created_at is informational only: re-running on identical inputs "
            "yields identical per-file hashes but a different created_at, so a "
            "difference in the manifest-as-a-whole hash alone does not show that "
            "any input or report changed."
        ),
        "source_a": {
            "root": root_label_a if root_label_a is not None else Path(dir_a).name,
            "file_count": len(hashes_a),
            "files": [
                {
                    "path": h.rel_path,
                    "sha256": h.sha256,
                    "size_bytes": h.size_bytes,
                    "modified_at": h.modified_at,
                }
                for h in hashes_a
            ],
        },
        "source_b": {
            "root": root_label_b if root_label_b is not None else Path(dir_b).name,
            "file_count": len(hashes_b),
            "files": [
                {
                    "path": h.rel_path,
                    "sha256": h.sha256,
                    "size_bytes": h.size_bytes,
                    "modified_at": h.modified_at,
                }
                for h in hashes_b
            ],
        },
        "reports": report_entries,
        "analysis_status": analysis_status or {"state": "unknown"},
        "analysis_configuration": analysis_configuration or {"state": "unknown"},
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{out.name}.", suffix=".tmp", dir=str(out.parent)
    )
    staged = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as staged_file:
            staged_file.write(manifest_text)
            staged_file.flush()
            os.fsync(staged_file.fileno())
        os.replace(staged, out)
    except Exception:
        staged.unlink(missing_ok=True)
        raise
    logger.info("Manifest → %s", out.resolve())
    return str(out.resolve())


# ---------------------------------------------------------------------------
# 증거 번들 생성 (--bundle 시)
# ---------------------------------------------------------------------------
def _stage_hash_sidecar(
    hash_file: Path,
    zip_hash: str,
    archive_name: str,
) -> Path:
    """Durably stage a checksum sidecar beside its final destination."""
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{hash_file.name}.",
        suffix=".tmp",
        dir=str(hash_file.parent),
    )
    staged = Path(staged_name)
    descriptor_open = True
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as staged_file:
            descriptor_open = False
            staged_file.write(f"{zip_hash}  {archive_name}\n")
            staged_file.flush()
            os.fsync(staged_file.fileno())
    except Exception:
        if descriptor_open:
            os.close(descriptor)
        staged.unlink(missing_ok=True)
        raise
    return staged


def _reserve_backup_path(target: Path) -> Path:
    """Reserve a same-directory path for rollback across atomic replacements."""
    descriptor, backup_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".backup",
        dir=str(target.parent),
    )
    os.close(descriptor)
    return Path(backup_name)


def _publish_bundle_pair(
    staged_zip: Path,
    staged_hash: Path,
    output_zip: Path,
    output_hash: Path,
) -> None:
    """Publish ZIP and checksum together, restoring prior outputs on failure.

    Each individual rename is atomic. Moving existing outputs aside before the
    new ZIP is exposed ensures the canonical paths never intentionally contain
    a new ZIP and an old checksum at the same time.
    """
    backups: dict[Path, Path] = {}
    published: set[Path] = set()
    try:
        for target in (output_zip, output_hash):
            if not target.exists():
                continue
            backup = _reserve_backup_path(target)
            backups[target] = backup
            try:
                os.replace(target, backup)
            except Exception:
                backup.unlink(missing_ok=True)
                backups.pop(target, None)
                raise

        os.replace(staged_zip, output_zip)
        published.add(output_zip)
        os.replace(staged_hash, output_hash)
        published.add(output_hash)
    except Exception as publish_error:
        rollback_errors: list[str] = []

        # Remove any newly published files before putting the old pair back.
        for target in (output_hash, output_zip):
            if target not in published:
                continue
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                rollback_errors.append(f"cannot remove new {target.name}: {exc}")

        # Restore ZIP first. Only restore the old sidecar when the ZIP returned
        # to its prior state, so a rollback problem cannot create an old/new mix.
        zip_restored = output_zip not in backups and not output_zip.exists()
        zip_backup = backups.get(output_zip)
        if zip_backup is not None and zip_backup.exists():
            try:
                os.replace(zip_backup, output_zip)
                zip_restored = True
            except OSError as exc:
                rollback_errors.append(f"cannot restore {output_zip.name}: {exc}")

        hash_backup = backups.get(output_hash)
        if hash_backup is not None and hash_backup.exists() and zip_restored:
            try:
                os.replace(hash_backup, output_hash)
            except OSError as exc:
                rollback_errors.append(f"cannot restore {output_hash.name}: {exc}")

        if rollback_errors:
            details = "; ".join(rollback_errors)
            retained = sorted(str(backup) for backup in backups.values() if backup.exists())
            recovery_note = (
                " Recovery backups retained at: " + ", ".join(retained) if retained else ""
            )
            raise SourceIntegrityError(
                f"Bundle publication failed and rollback was incomplete: {details}.{recovery_note}"
            ) from publish_error
        raise
    else:
        for backup in backups.values():
            try:
                backup.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Could not remove old bundle backup %s: %s", backup, exc)
    finally:
        staged_zip.unlink(missing_ok=True)
        staged_hash.unlink(missing_ok=True)


# ZIP's DOS date field covers 1980-01-01 .. 2107-12-31 (PKWARE APPNOTE 4.4.6:
# 7-bit year offset from 1980, 2-second resolution); clamp outside that range.
_ZIP_MIN_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_ZIP_MAX_DATE_TIME = (2107, 12, 31, 23, 59, 58)


def _zip_date_time(timestamp: float) -> tuple[int, int, int, int, int, int]:
    """Local date_time tuple for a ZIP entry, clamped to the DOS-representable range."""
    try:
        value = tuple(time.localtime(timestamp)[:6])
    except (OverflowError, OSError, ValueError):
        # Out of the platform's localtime range: clamp toward the nearer end
        # (a NaN fails "> 0" and gets the minimum).
        return _ZIP_MAX_DATE_TIME if timestamp > 0 else _ZIP_MIN_DATE_TIME
    return min(max(value, _ZIP_MIN_DATE_TIME), _ZIP_MAX_DATE_TIME)  # type: ignore[return-value]


def create_evidence_bundle(
    dir_a: str,
    dir_b: str,
    files_a: list[str],
    files_b: list[str],
    manifest_path: str,
    report_paths: list[str],
    output_zip: str,
) -> str:
    """증거 번들 zip을 생성한다.

    번들 구조::

        evidence_bundle.zip
        ├── manifest.sha256.json
        ├── report.pdf (등 생성된 리포트)
        ├── source_a/
        │   └── (해시된 dir_a 파일)
        └── source_b/
            └── (해시된 dir_b 파일)

    zip 생성 후 zip 파일 자체의 SHA-256을 ``{output_zip}.sha256``로 기록.

    무결성 핵심:
        번들에 담는 소스 파일 집합은 **매니페스트가 해시한 집합과 정확히 동일**하다.
        ``files_a``/``files_b`` 는 ``collector.collect_files()`` 가 돌려준
        (심볼릭 링크·ignore 제외가 적용된) 상대경로 목록이어야 한다.
        독립적인 ``rglob`` walk를 쓰지 않으므로, 매니페스트에 없는(해시되지 않은)
        파일·심볼릭 링크 대상(트리 밖 내용)·제외 대상이 번들에 섞일 수 없다.

    Args:
        files_a / files_b: 매니페스트가 해시한 것과 동일한 상대경로 목록.
        output_zip: 생성할 zip 파일 경로.

    Returns:
        생성된 zip 파일의 SHA-256 hex digest.
    """

    def _bundle_source_root(path: str, files: list[str], *, label: str) -> Path:
        lexical = _lexical_absolute(path)
        _reject_redirecting_components(lexical, label=label)
        if not lexical.exists():
            if files:
                raise SourceIntegrityError(f"Missing {label}: {lexical}")
            # Preserve the historical empty-side API: an absent root is acceptable
            # only when its declared and manifested file set is empty.
            return lexical.resolve(strict=False)
        try:
            resolved = lexical.resolve(strict=True)
        except OSError as exc:
            raise SourceIntegrityError(f"Cannot resolve {label}: {exc}") from exc
        if not resolved.is_dir():
            raise SourceIntegrityError(f"{label} is not a directory: {resolved}")
        return resolved

    root_a = _bundle_source_root(dir_a, files_a, label="bundle source A root")
    root_b = _bundle_source_root(dir_b, files_b, label="bundle source B root")

    out = _lexical_absolute(output_zip)
    hash_file = Path(f"{out}.sha256")
    for label, candidate in (
        ("evidence bundle output", out),
        ("evidence bundle checksum output", hash_file),
    ):
        _reject_redirecting_components(candidate, label=label)
        resolved_candidate = candidate.resolve(strict=False)
        if any(_paths_overlap(resolved_candidate, root) for root in (root_a, root_b)):
            raise SourceIntegrityError(
                f"Evidence bundle output overlaps a source root: {resolved_candidate}"
            )
        if candidate.exists() and not candidate.is_file():
            raise SourceIntegrityError(f"Evidence bundle output is not a regular file: {candidate}")

    manifest_lexical = _lexical_absolute(manifest_path)
    _reject_redirecting_components(manifest_lexical, label="integrity manifest input")
    try:
        manifest_file = manifest_lexical.resolve(strict=True)
    except OSError as exc:
        raise SourceIntegrityError(f"Cannot resolve integrity manifest: {exc}") from exc
    if not manifest_file.is_file():
        raise SourceIntegrityError(f"Integrity manifest is not a regular file: {manifest_file}")
    try:
        manifest_bytes = manifest_file.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceIntegrityError(f"Cannot read integrity manifest: {exc}") from exc

    def _expected_hashes(side_key: str) -> dict[str, str]:
        side = manifest.get(side_key)
        if not isinstance(side, dict) or not isinstance(side.get("files"), list):
            raise SourceIntegrityError(f"Integrity manifest is missing {side_key}.files")
        expected: dict[str, str] = {}
        for entry in side["files"]:
            if not isinstance(entry, dict):
                raise SourceIntegrityError(f"Invalid {side_key} manifest entry")
            rel_path = entry.get("path")
            digest = entry.get("sha256")
            if not isinstance(rel_path, str) or not isinstance(digest, str):
                raise SourceIntegrityError(f"Invalid {side_key} path/hash entry")
            _validate_archive_path(rel_path, label=side_key)
            if rel_path in expected:
                raise SourceIntegrityError(f"Duplicate {side_key} manifest path: {rel_path}")
            expected[rel_path] = digest
        return expected

    expected_a = _expected_hashes("source_a")
    expected_b = _expected_hashes("source_b")

    def _recorded_mtimes(side_key: str) -> dict[str, float]:
        # Bundle entries carry the ORIGINAL file's mtime as recorded in the
        # manifest; the snapshot copy being bundled has a fresh mtime.
        recorded: dict[str, float] = {}
        for entry in manifest[side_key]["files"]:
            value = entry.get("modified_at")
            if isinstance(value, str):
                try:
                    recorded[entry["path"]] = datetime.datetime.fromisoformat(value).timestamp()
                except (ValueError, OverflowError, OSError):
                    continue
        return recorded

    mtimes_a = _recorded_mtimes("source_a")
    mtimes_b = _recorded_mtimes("source_b")
    if set(files_a) != set(expected_a) or len(files_a) != len(expected_a):
        raise SourceIntegrityError("source_a file list does not match the manifest")
    if set(files_b) != set(expected_b) or len(files_b) != len(expected_b):
        raise SourceIntegrityError("source_b file list does not match the manifest")

    report_entries = manifest.get("reports")
    if not isinstance(report_entries, list):
        raise SourceIntegrityError("Integrity manifest is missing reports")
    expected_reports: dict[str, str] = {}
    for entry in report_entries:
        if not isinstance(entry, dict):
            raise SourceIntegrityError("Invalid report manifest entry")
        logical_path = entry.get("path")
        digest = entry.get("sha256")
        if not isinstance(logical_path, str) or not isinstance(digest, str):
            raise SourceIntegrityError("Invalid report path/hash entry")
        _validate_archive_path(logical_path, label="report")
        if logical_path in expected_reports:
            raise SourceIntegrityError(f"Duplicate report manifest path: {logical_path}")
        expected_reports[logical_path] = digest
    mapped_reports = _logical_report_paths(report_paths)
    if {logical for _path, logical in mapped_reports} != set(expected_reports):
        raise SourceIntegrityError("Report file list does not match the manifest")

    verified_reports: list[tuple[Path, str]] = []
    for report_path, logical_path in mapped_reports:
        lexical_report = _lexical_absolute(report_path)
        _reject_redirecting_components(lexical_report, label="report input")
        try:
            resolved_report = lexical_report.resolve(strict=True)
        except OSError as exc:
            raise SourceIntegrityError(f"Cannot resolve bundled report: {logical_path}") from exc
        if not resolved_report.is_file():
            raise SourceIntegrityError(f"Bundled report is not a regular file: {logical_path}")
        verified_reports.append((resolved_report, logical_path))
    mapped_reports = verified_reports

    output_candidates = {out.resolve(), hash_file.resolve()}
    evidence_inputs = {manifest_file.resolve()}
    evidence_inputs.update(path.resolve() for path, _logical in mapped_reports)
    evidence_inputs.update((root_a / rel_path).resolve() for rel_path in files_a)
    evidence_inputs.update((root_b / rel_path).resolve() for rel_path in files_b)
    collisions = output_candidates & evidence_inputs
    if collisions:
        raise SourceIntegrityError(
            "Evidence bundle output collides with and would overwrite an input: "
            + ", ".join(sorted(str(path) for path in collisions))
        )

    out.parent.mkdir(parents=True, exist_ok=True)

    def _resolved_source(root: Path, rel_path: str) -> Path:
        try:
            return _resolve_contained_file(root, rel_path, label="bundled source")
        except OSError as exc:
            raise SourceIntegrityError(f"Missing bundled source: {rel_path}") from exc

    def _write_verified(
        archive: zipfile.ZipFile,
        source: Path,
        archive_name: str,
        expected_digest: str,
        mtime: float | None = None,
    ) -> None:
        digest = hashlib.sha256()
        try:
            if mtime is None:
                mtime = source.stat().st_mtime
            info = zipfile.ZipInfo(archive_name, date_time=_zip_date_time(mtime))
            info.compress_type = archive.compression
            with source.open("rb") as input_file, archive.open(info, "w") as output_file:
                while chunk := input_file.read(_HASH_BUF_SIZE):
                    digest.update(chunk)
                    output_file.write(chunk)
        except OSError as exc:
            raise SourceIntegrityError(f"Cannot bundle {archive_name}: {exc}") from exc
        if digest.hexdigest() != expected_digest:
            raise SourceIntegrityError(
                f"Bundled bytes changed or do not match manifest hash: {archive_name}"
            )

    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{out.name}.", suffix=".tmp", dir=str(out.parent)
    )
    os.close(descriptor)
    staged = Path(staged_name)
    staged_hash: Path | None = None
    try:
        with zipfile.ZipFile(str(staged), "w", zipfile.ZIP_DEFLATED) as archive:
            for rel_path in files_a:
                _write_verified(
                    archive,
                    _resolved_source(root_a, rel_path),
                    f"source_a/{rel_path}",
                    expected_a[rel_path],
                    mtimes_a.get(rel_path),
                )
            for rel_path in files_b:
                _write_verified(
                    archive,
                    _resolved_source(root_b, rel_path),
                    f"source_b/{rel_path}",
                    expected_b[rel_path],
                    mtimes_b.get(rel_path),
                )
            archive.writestr("manifest.sha256.json", manifest_bytes)
            for report_path, logical_path in mapped_reports:
                _write_verified(
                    archive,
                    report_path,
                    logical_path,
                    expected_reports[logical_path],
                )
        # Hash and sidecar staging happen before either canonical output moves.
        # A checksum or write failure therefore leaves the previous pair intact.
        zip_hash = _sha256_file(staged)
        staged_hash = _stage_hash_sidecar(hash_file, zip_hash, out.name)
        _publish_bundle_pair(staged, staged_hash, out, hash_file)
    except Exception:
        staged.unlink(missing_ok=True)
        if staged_hash is not None:
            staged_hash.unlink(missing_ok=True)
        raise

    logger.info("Evidence bundle → %s (%d bytes)", out.resolve(), out.stat().st_size)
    logger.info("Bundle SHA-256: %s", zip_hash)
    logger.info("Hash file → %s", hash_file.resolve())

    return zip_hash
