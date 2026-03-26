"""파일 수집 및 퍼지 1:1 매칭.

두 디렉토리의 파일 목록을 수집하고, ``rapidfuzz``로 파일명 유사도 기반
1:1 매칭을 수행한다.  디렉토리 간 파일명이 다르더라도 매칭되도록
2-phase 전략 사용: exact match → fuzzy match.

알고리즘 복잡도:
    - Phase 1 (exact):  O(N) — set lookup
    - Phase 2 (fuzzy):  O(R²) — R = 미매칭 파일 수 (실무에서 R ≪ N)
    - 전체: O(N + R²). 대부분의 파일이 exact match되므로 실질 선형.

의존:
    - ``rapidfuzz``:  C++ 기반 고성능 퍼지 문자열 매칭
    - ``models.FileMatch``:  결과 데이터클래스

호출관계:
    ``pipeline.run_pipeline()`` → ``collect_files()`` → ``match_files()``
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

from rapidfuzz import fuzz

from diffinite.models import FileMatch

# ──────────────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────────────
FUZZY_THRESHOLD: float = 60
"""퍼지 매칭 최소 유사도 (0–100). CLI ``--threshold``로 오버라이드 가능.
60 미만은 파일명 유사도가 너무 낮아 오매칭 위험이 높다."""


import fnmatch
import os

# ──────────────────────────────────────────────────────────────────────
# 파일 수집 & 무시 패턴 처리
# ──────────────────────────────────────────────────────────────────────
def should_ignore(name: str, patterns: list[str]) -> bool:
    """Check if a file or directory name matches any ignore pattern."""
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
    return False

def collect_files(directory: str, ignore_patterns: list[str] | None = None) -> list[str]:
    """지정 디렉토리 하위의 모든 파일을 재귀 수집한다.

    방문 중 `ignore_patterns`에 매칭되는 디렉토리는 하위 탐색을
    완전 생략(Pruning)하여 압도적인 성능 향상을 이룬다.

    Returns:
        정렬된 POSIX 스타일 상대경로 목록.
    """
    if ignore_patterns is None:
        ignore_patterns = []
        
    root = Path(directory).resolve()
    paths: list[str] = []
    
    for dirpath, dirnames, filenames in os.walk(root):
        # 1. Prune ignored directories (modify in-place for os.walk)
        dirnames[:] = [d for d in dirnames if not should_ignore(d, ignore_patterns)]
        
        # 2. Collect non-ignored files
        current_dir = Path(dirpath)
        for f in filenames:
            if not should_ignore(f, ignore_patterns):
                abs_file = current_dir / f
                if abs_file.is_file():
                    paths.append(abs_file.relative_to(root).as_posix())
                    
    paths.sort()
    return paths


# ──────────────────────────────────────────────────────────────────────
# 2-Phase 퍼지 매칭
# ──────────────────────────────────────────────────────────────────────
def match_files(
    files_a: list[str],
    files_b: list[str],
    threshold: float = FUZZY_THRESHOLD,
) -> Tuple[list[FileMatch], list[str], list[str]]:
    """두 파일 목록을 exact + fuzzy 전략으로 1:1 매칭한다.

    Phase 1 (exact):
        동일 상대경로 파일을 O(N) set lookup으로 즉시 매칭.
        대부분의 실무 케이스에서 90%+ 파일이 여기서 처리된다.

    Phase 2 (fuzzy):
        Phase 1에서 매칭되지 않은 나머지 파일에 대해
        rapidfuzz.fuzz.ratio() (Levenshtein 기반)로 유사도 계산.
        score 내림차순 greedy 전략으로 중복 없이 1:1 할당.

    Args:
        threshold: 이 값 미만의 fuzzy 매칭은 버린다.
                   60 미만은 실무에서 거의 의미 없는 매칭이 된다.

    Returns:
        ``(matched_pairs, unmatched_a, unmatched_b)``
        unmatched 파일은 deep_compare에서 N:M 크로스매칭 대상이 된다.
    """
    matches: list[FileMatch] = []

    # ── Phase 1: Exact match ────────────────────────────────────────
    # set lookup O(1) × N = O(N). 경로가 정확히 같으면 무조건 매칭.
    set_b = set(files_b)
    exact_matched_a: set[int] = set()
    exact_matched_b: set[str] = set()

    for i, fa in enumerate(files_a):
        if fa in set_b:
            matches.append(FileMatch(fa, fa, 100.0))
            exact_matched_a.add(i)
            exact_matched_b.add(fa)

    remaining_a = [(i, fa) for i, fa in enumerate(files_a) if i not in exact_matched_a]
    remaining_b = [(j, fb) for j, fb in enumerate(files_b) if fb not in exact_matched_b]

    # ── Phase 2: Fuzzy match on remainder ───────────────────────────
    # O(R²) brute-force. R은 미매칭 파일 수 — 실무에서 대부분 한 자릿수.
    # 더 큰 R이 예상되면 rapidfuzz.process.extractBests() 기반
    # 헝가리안 할당으로 교체 검토 필요.
    if remaining_a and remaining_b:
        candidates: list[Tuple[float, int, int]] = []
        for ri, (i, fa) in enumerate(remaining_a):
            for rj, (j, fb) in enumerate(remaining_b):
                score = fuzz.ratio(fa, fb)
                if score >= threshold:
                    candidates.append((score, ri, rj))

        # score 내림차순 정렬 → greedy best-first 할당
        candidates.sort(key=lambda x: x[0], reverse=True)

        used_ri: set[int] = set()
        used_rj: set[int] = set()
        for score, ri, rj in candidates:
            if ri in used_ri or rj in used_rj:
                continue  # 이미 매칭된 파일은 스킵 (1:1 보장)
            _, fa = remaining_a[ri]
            _, fb = remaining_b[rj]
            matches.append(FileMatch(fa, fb, score))
            used_ri.add(ri)
            used_rj.add(rj)

        unmatched_a = [fa for ri, (_, fa) in enumerate(remaining_a) if ri not in used_ri]
        unmatched_b = [fb for rj, (_, fb) in enumerate(remaining_b) if rj not in used_rj]
    else:
        unmatched_a = [fa for _, fa in remaining_a]
        unmatched_b = [fb for _, fb in remaining_b]

    return matches, unmatched_a, unmatched_b
