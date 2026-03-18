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
import zipfile
from pathlib import Path

from diffinite.models import FileHashEntry
from diffinite import __version__

logger = logging.getLogger(__name__)

# SHA-256 버퍼 크기 (64KB). 대형 파일에서도 메모리 효율적.
_HASH_BUF_SIZE = 65536


def jaccard_similarity(fp_a: set[int], fp_b: set[int]) -> float:
    """Winnowing 핑거프린트 Jaccard 유사도. |A∩B| / |A∪B|.

    "두 파일의 코드 지문 중 N%가 일치합니다" 형태로 보고서에 표시.
    양쪽 모두 빈 집합이면 0.0 반환.
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
        abs_path = root / rel_path
        try:
            stat = abs_path.stat()
            sha = _sha256_file(abs_path)
            mtime = datetime.datetime.fromtimestamp(
                stat.st_mtime,
                tz=datetime.timezone.utc,
            ).isoformat()
            entries.append(FileHashEntry(
                rel_path=rel_path,
                sha256=sha,
                size_bytes=stat.st_size,
                modified_at=mtime,
            ))
        except (OSError, IOError) as e:
            logger.warning("Hash computation failed for %s: %s", rel_path, e)

    return entries


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
) -> str:
    """``manifest.sha256.json``을 생성한다.

    모든 분석 실행에서 무조건 생성되며, 분석 대상 파일과
    생성된 리포트의 SHA-256 해시를 기록한다.

    Args:
        report_paths: 생성된 리포트 파일 경로 목록 (존재하는 파일만 해시).
        output_path: 매니페스트 JSON 저장 경로.

    Returns:
        생성된 매니페스트 파일의 절대경로.
    """
    # 리포트 파일 해시
    report_entries = []
    for rp in report_paths:
        p = Path(rp)
        if p.exists() and p.stat().st_size > 0:
            report_entries.append({
                "path": p.name,
                "sha256": _sha256_file(p),
                "size_bytes": p.stat().st_size,
            })

    manifest = {
        "tool": "diffinite",
        "version": __version__,
        "created_at": datetime.datetime.now(
            tz=datetime.timezone.utc
        ).isoformat(),
        "source_a": {
            "root": str(Path(dir_a).resolve()),
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
            "root": str(Path(dir_b).resolve()),
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
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("Manifest → %s", out.resolve())
    return str(out.resolve())


# ---------------------------------------------------------------------------
# 증거 번들 생성 (--bundle 시)
# ---------------------------------------------------------------------------
def create_evidence_bundle(
    dir_a: str,
    dir_b: str,
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
        │   └── (dir_a 전체 파일)
        └── source_b/
            └── (dir_b 전체 파일)

    zip 생성 후 zip 파일 자체의 SHA-256을 ``{output_zip}.sha256``로 기록.

    Args:
        output_zip: 생성할 zip 파일 경로.

    Returns:
        생성된 zip 파일의 SHA-256 hex digest.
    """
    out = Path(output_zip)
    out.parent.mkdir(parents=True, exist_ok=True)

    root_a = Path(dir_a).resolve()
    root_b = Path(dir_b).resolve()

    with zipfile.ZipFile(str(out), "w", zipfile.ZIP_DEFLATED) as zf:
        # Source A
        for item in root_a.rglob("*"):
            if item.is_file():
                arcname = f"source_a/{item.relative_to(root_a).as_posix()}"
                zf.write(str(item), arcname)

        # Source B
        for item in root_b.rglob("*"):
            if item.is_file():
                arcname = f"source_b/{item.relative_to(root_b).as_posix()}"
                zf.write(str(item), arcname)

        # Manifest
        if Path(manifest_path).exists():
            zf.write(manifest_path, "manifest.sha256.json")

        # Reports
        for rp in report_paths:
            p = Path(rp)
            if p.exists() and p.stat().st_size > 0:
                zf.write(str(p), p.name)

    # Compute zip hash
    zip_hash = _sha256_file(out)

    # Write sidecar hash file
    hash_file = Path(f"{output_zip}.sha256")
    hash_file.write_text(
        f"{zip_hash}  {out.name}\n",
        encoding="utf-8",
    )

    logger.info("Evidence bundle → %s (%d bytes)", out.resolve(), out.stat().st_size)
    logger.info("Bundle SHA-256: %s", zip_hash)
    logger.info("Hash file → %s", hash_file.resolve())

    return zip_hash
