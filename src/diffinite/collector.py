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

from pathlib import Path, PurePosixPath
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Tuple

from rapidfuzz import fuzz

from diffinite.models import FileMatch

# ──────────────────────────────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────────────────────────────
FUZZY_THRESHOLD: float = 60
"""퍼지 매칭 최소 유사도 (0–100). CLI ``--threshold``로 오버라이드 가능.
60 미만은 파일명 유사도가 너무 낮아 오매칭 위험이 높다."""


import errno
import fnmatch
import os
import stat

_REPARSE_TAG_NAME_SURROGATE = 0x20000000
"""Windows SDK winnt.h ``IsReparseTagNameSurrogate``: bit 29 of a reparse tag
marks a reparse point that names another file (symlink, junction, ...)."""

_WIN32_NAME_REASON = "name ends with a dot or space; Windows paths cannot address it"


def _is_win32_unaddressable(name: str) -> bool:
    """Return whether Win32 path normalization would alter ``name``.

    Windows strips trailing dots and spaces from each path component, so
    ``open("dir/a.py.")`` silently opens ``dir/a.py`` (or fails).  Such an
    entry can be listed but not read as itself by the rest of the pipeline,
    so it is disclosed as skipped instead of being collected or dropped.
    """
    return os.name == "nt" and name.endswith((".", " "))


def _archive_unsafe_name_reason(name: str) -> str | None:
    """Reason a name component would be refused by the evidence layer, or None.

    ``evidence._validate_archive_path`` rejects any path containing a
    backslash or a component starting with a drive designator (``C:x``),
    because Windows path joining would land it outside the extraction root.
    Such names are legal on POSIX; collecting one would abort the run while
    hashing, so it is disclosed as skipped here instead (same rule as
    ``evidence._is_drive_designator``).
    """
    if "\\" in name:
        return "name contains a backslash; not representable in the evidence archive"
    if len(name) >= 2 and name[1] == ":" and name[0].isascii() and name[0].isalpha():
        return (
            "name starts with a drive designator (X:); not representable in the "
            "evidence archive"
        )
    return None


def _is_link_like_directory(path: Path) -> bool:
    """Return whether a directory entry can redirect traversal elsewhere.

    ``Path.is_symlink()`` covers POSIX links and Windows symbolic links.  On
    Windows, directory junctions and other reparse points also redirect reads
    but are not reported as symbolic links on every supported Python version.
    Treat every directory reparse point as an excluded, disclosed input rather
    than allowing an evidence walk to escape or duplicate its declared root.
    """
    if path.is_symlink():
        return True
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", None)
    return bool(reparse_flag is not None and attributes & reparse_flag)

# ──────────────────────────────────────────────────────────────────────
# 파일 수집 & 무시 패턴 처리
# ──────────────────────────────────────────────────────────────────────
def _match_segments(pat_segs: list[str], path_segs: list[str]) -> bool:
    """Match path components against pattern components (``**`` aware).

    Each non-``**`` component is matched with :func:`fnmatch.fnmatchcase`
    against exactly one path component, so ``*``/``?``/``[...]`` never cross
    a ``/``.  A ``**`` component matches zero or more whole components, except
    a trailing ``**`` which matches one or more (``abc/**`` = everything
    *inside* ``abc``), as in gitignore.

    Consecutive ``**`` components are merged (``**/**`` matches exactly what
    ``**`` matches) and every (pattern index, path index) state is evaluated
    at most once, so the cost is bounded by ``len(pat) * len(path)`` matches
    even for degenerate patterns such as ``**/**/**/**/y``.
    """
    pat: list[str] = []
    for seg in pat_segs:
        if seg == "**" and pat and pat[-1] == "**":
            continue
        pat.append(seg)
    n_pat, n_path = len(pat), len(path_segs)
    memo: dict[tuple[int, int], bool] = {}

    def match(i: int, j: int) -> bool:
        key = (i, j)
        cached = memo.get(key)
        if cached is not None:
            return cached
        if i == n_pat:
            result = j == n_path
        elif pat[i] == "**":
            if i == n_pat - 1:
                result = n_path - j >= 1
            else:
                result = any(match(i + 1, k) for k in range(j, n_path + 1))
        else:
            result = (
                j < n_path
                and fnmatch.fnmatchcase(path_segs[j], pat[i])
                and match(i + 1, j + 1)
            )
        memo[key] = result
        return result

    return match(0, 0)


def matching_pattern(
    rel_path: str, patterns: Sequence[str], is_dir: bool = False
) -> str | None:
    """Check whether a POSIX relative path is excluded by any ignore pattern.

    gitignore 의 패턴 문법 중 아래 부분집합을 그대로 따른다:

    - 매칭은 **모든 OS에서 대소문자를 구분**한다 (``fnmatchcase``). 같은
      정책 파일(같은 SHA-256)이 OS마다 다른 증거 집합을 고르지 않게 한다.
    - 끝의 ``/`` 는 "디렉토리에만 매칭"을 뜻하며 앵커링 판단에서 제외된다
      (``node_modules/`` 는 모든 깊이의 ``node_modules`` 디렉토리에 매칭).
    - 끝의 ``/`` 를 뗀 뒤 ``/`` 가 남지 않는 패턴(``node_modules``, ``*.log``)은
      모든 깊이의 경로 **컴포넌트 이름**에 매칭된다.
    - ``/`` 가 남는 패턴(``/build``, ``src/*.py``, ``**/*.gen.cs``)은 루트 기준
      상대경로에 앵커링된다. 앞의 ``/`` 는 앵커 표시일 뿐이다.
    - ``*``, ``?``, ``[...]`` 는 ``/`` 를 넘지 않는다 (``src/*.py`` 는
      ``src/a/b.py`` 에 매칭되지 않음). 앞의 ``**/`` 는 0개 이상의 디렉토리
      (루트 포함), 중간의 ``/**/`` 는 0개 이상의 디렉토리, 끝의 ``/**`` 는
      그 디렉토리 안의 모든 것에 매칭된다.
    - 어떤 상위 디렉토리가 매칭되면 그 아래 모든 경로도 제외된다.

    지원하지 않는 gitignore 기능: ``!`` 부정(re-include)과 ``\\`` 이스케이프.
    ``!foo`` 는 이름이 문자 그대로 ``!foo`` 인 항목에만 매칭된다.
    gitignore 와 달리 패턴 **앞의 공백도 제거**된다(앞뒤 공백 모두 strip):
    ``"  foo"`` 는 ``foo`` 와 같고, 공백으로 시작하는 이름은 매칭할 수 없다.

    Args:
        rel_path: 루트 기준 POSIX 상대경로.
        patterns: 무시 패턴 목록.
        is_dir: ``rel_path`` 자체가 디렉토리이면 True (디렉토리 전용 패턴용).
            상위 컴포넌트는 항상 디렉토리로 취급한다.
    """
    parts = [part for part in rel_path.split("/") if part]
    if not parts:
        return None
    for pat in patterns:
        p = pat.strip()
        dir_only = p.endswith("/")
        p = p.rstrip("/")
        if not p:
            continue
        anchored = "/" in p
        segs = [seg for seg in p.split("/") if seg]
        if not segs:
            continue
        for k in range(1, len(parts) + 1):
            candidate_is_dir = k < len(parts) or is_dir
            if dir_only and not candidate_is_dir:
                continue
            if anchored:
                if _match_segments(segs, parts[:k]):
                    return pat
            elif fnmatch.fnmatchcase(parts[k - 1], segs[0]):
                return pat
    return None


def should_ignore(rel_path: str, patterns: Sequence[str], is_dir: bool = False) -> bool:
    """Whether any pattern in ``patterns`` excludes ``rel_path`` (see :func:`matching_pattern`)."""
    return matching_pattern(rel_path, patterns, is_dir) is not None


# ──────────────────────────────────────────────────────────────────────
# Sensitive-file preset
# ──────────────────────────────────────────────────────────────────────
SENSITIVE_PRESET_VERSION = "1"
"""Bump whenever the lists below change, so a manifest names the exact list used."""

SENSITIVE_FILE_PATTERNS: tuple[str, ...] = (
    # Environment files holding configuration secrets (dotenv convention).
    ".env",
    ".env.*",
    "*.env",
    # Private keys and key stores.
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    # OpenSSH default private key file names (ssh-keygen(1), FILES). Exact
    # names only: a prefix glob would also match source files such as
    # id_rsa_util.py.
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ecdsa_sk",
    "id_ed25519",
    "id_ed25519_sk",
    # Credential files of common tools.
    ".npmrc",
    ".pypirc",
    ".netrc",
    "_netrc",
    ".git-credentials",
    ".htpasswd",
    "credentials",
    "credentials.json",
    "*.tfvars",
    "*.tfstate",
    "*.tfstate.backup",
)
"""File-name patterns of the sensitive-file preset, matched case-insensitively."""

SENSITIVE_KEPT_SUFFIXES: tuple[str, ...] = (".example", ".sample", ".template", ".dist", ".pub")
"""A name ending in one of these is a template or a public key, not a secret."""

SENSITIVE_DIRECTORIES: tuple[str, ...] = (".ssh", ".aws", ".azure", ".gnupg", ".kube")
"""Every file under a directory with one of these names (credential stores)."""

SENSITIVE_PATH_PATTERNS: tuple[str, ...] = (".config/gcloud/**", ".docker/config.json")
"""Path patterns, matched at any depth, for credential files of cloud CLIs."""


def sensitive_preset_rules() -> list[str]:
    """The preset as a flat list of rules, for the manifest and the reports."""
    return [
        *SENSITIVE_FILE_PATTERNS,
        *(f"{name}/**" for name in SENSITIVE_DIRECTORIES),
        *SENSITIVE_PATH_PATTERNS,
        *(f"except *{suffix}" for suffix in SENSITIVE_KEPT_SUFFIXES),
    ]


def sensitive_rule(rel_path: str) -> str | None:
    """The preset rule that marks file ``rel_path`` as sensitive, or None.

    Matching ignores case on every OS: ``.ENV`` and ``ID_RSA`` hold the same
    secrets as ``.env`` and ``id_rsa``.
    """
    parts = [part.lower() for part in rel_path.split("/") if part]
    if not parts:
        return None
    name = parts[-1]
    for directory in parts[:-1]:
        if directory in SENSITIVE_DIRECTORIES:
            return f"{directory}/**"
    for i in range(len(parts)):
        for pattern in SENSITIVE_PATH_PATTERNS:
            if _match_segments(pattern.split("/"), parts[i:]):
                return pattern
    if name.endswith(SENSITIVE_KEPT_SUFFIXES):
        return None
    for pattern in SENSITIVE_FILE_PATTERNS:
        if fnmatch.fnmatchcase(name, pattern):
            return pattern
    return None


SENSITIVE_MODES = ("exclude", "include", "error")
EXCLUSION_SOURCES = ("ignore-file", "include-filter", "sensitive-preset")


@dataclass(frozen=True)
class CollectionPolicy:
    """What :func:`collect_files` leaves out, in the order the rules apply.

    1. ``ignore_patterns`` (the ignore file) excludes files and prunes
       directories.
    2. ``include_patterns``, when not empty, excludes every file that no
       pattern matches (same pattern syntax as the ignore file).
    3. ``sensitive_files`` ``"exclude"`` or ``"error"`` excludes files named by
       the sensitive-file preset; ``"include"`` collects them.  Under
       ``"error"`` the pipeline refuses the run when any were found.

    Every exclusion is recorded with the rule that caused it.
    """

    ignore_patterns: tuple[str, ...] = ()
    include_patterns: tuple[str, ...] = ()
    sensitive_files: str = "include"

    def __post_init__(self) -> None:
        if self.sensitive_files not in SENSITIVE_MODES:
            raise ValueError(f"sensitive_files must be one of {SENSITIVE_MODES}")


def exclusion_for(
    rel_path: str, policy: CollectionPolicy, is_dir: bool = False
) -> tuple[str, str] | None:
    """``(source, rule)`` when ``policy`` excludes ``rel_path``, else None."""
    rule = matching_pattern(rel_path, policy.ignore_patterns, is_dir)
    if rule is not None:
        return "ignore-file", rule
    if is_dir:
        return None
    if policy.include_patterns and matching_pattern(rel_path, policy.include_patterns) is None:
        return "include-filter", "no --include pattern matches"
    if policy.sensitive_files != "include":
        rule = sensitive_rule(rel_path)
        if rule is not None:
            return "sensitive-preset", rule
    return None

def collect_files(
    directory: str,
    ignore_patterns: Sequence[str] | None = None,
    unreadable_list: list[str] | None = None,
    *,
    policy: CollectionPolicy | None = None,
    excluded_list: list[dict[str, str]] | None = None,
) -> list[str]:
    """지정 디렉토리 하위의 모든 파일을 재귀 수집한다.

    방문 중 `ignore_patterns`에 매칭되는 디렉토리는 하위 탐색을
    완전 생략(Pruning)하여 압도적인 성능 향상을 이룬다.

    무시 패턴에 걸리지 않았는데 수집하지 못한 항목(심볼릭 링크/리파스 포인트,
    stat 실패, 일반 파일이 아닌 항목, Windows에서 끝이 ``.``/공백인 이름,
    증거 아카이브가 거부하는 이름 — 백슬래시 포함 또는 ``X:`` 로 시작)은
    모두 ``unreadable_list`` 에 ``"<rel> (skipped: <reason>)"`` 형태로 기록한다.

    ``policy`` 를 주면 ``ignore_patterns`` 대신 그 정책 전체(ignore, include,
    민감 파일 프리셋)를 적용한다. 정책이 제외한 항목은 ``excluded_list`` 에
    ``{"path", "kind": "file"|"directory", "source", "rule"}`` 로 기록한다.
    제외된 디렉토리는 하위를 열거하지 않고 디렉토리 하나로 기록한다.

    Returns:
        정렬된 POSIX 스타일 상대경로 목록.
    """
    if policy is None:
        policy = CollectionPolicy(ignore_patterns=tuple(ignore_patterns or ()))
        
    root = Path(directory).resolve()
    paths: list[str] = []
    
    def on_err(err: OSError):
        if unreadable_list is not None and hasattr(err, 'filename') and err.filename:
            unreadable_list.append(str(err.filename))

    def _disclose(rel: str, reason: str) -> None:
        if unreadable_list is not None:
            unreadable_list.append(f"{rel} (skipped: {reason})")

    def _excluded(rel: str, kind: str, is_dir: bool) -> bool:
        found = exclusion_for(rel, policy, is_dir=is_dir)
        if found is None:
            return False
        if excluded_list is not None:
            excluded_list.append({"path": rel, "kind": kind, "source": found[0], "rule": found[1]})
        return True

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_err):
        current_dir = Path(dirpath)
        rel_dir = current_dir.relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        # 1. Prune ignored directories (modify in-place for os.walk).
        #    Test the relative dir path so path-anchored patterns also prune.
        #    The ignore policy is applied first: an entry the policy excludes is
        #    not evidence, so it must not be reported as a collection failure.
        kept_dirs = []
        for d in dirnames:
            rel_d = f"{rel_dir}/{d}" if rel_dir else d
            if _excluded(rel_d, "directory", is_dir=True):
                continue
            if _is_win32_unaddressable(d):
                _disclose(rel_d, _WIN32_NAME_REASON)
                continue
            unsafe = _archive_unsafe_name_reason(d)
            if unsafe is not None:
                _disclose(rel_d, unsafe)
                continue
            abs_dir = current_dir / d
            if _is_link_like_directory(abs_dir):
                _disclose(rel_d, "linked or reparse-point directory")
                continue
            kept_dirs.append(d)
        dirnames[:] = kept_dirs

        # 2. Collect non-ignored files.  Every listed entry that is not
        #    collected is disclosed, so the pipeline can refuse the run or mark
        #    the report incomplete instead of silently claiming full coverage.
        for f in filenames:
            rel_f = f"{rel_dir}/{f}" if rel_dir else f
            if _excluded(rel_f, "file", is_dir=False):
                continue
            if _is_win32_unaddressable(f):
                _disclose(rel_f, _WIN32_NAME_REASON)
                continue
            unsafe = _archive_unsafe_name_reason(f)
            if unsafe is not None:
                _disclose(rel_f, unsafe)
                continue
            try:
                st = os.lstat(os.path.join(dirpath, f))
            except OSError as exc:
                # errno name, not strerror: strerror is OS-locale dependent and
                # the disclosure text must be reproducible across machines.
                code = errno.errorcode.get(exc.errno or -1, str(exc.errno))
                _disclose(rel_f, f"stat failed: {code}")
                continue
            if stat.S_ISLNK(st.st_mode) or (
                getattr(st, "st_reparse_tag", 0) & _REPARSE_TAG_NAME_SURROGATE
            ):
                _disclose(rel_f, "symbolic link")
            elif stat.S_ISREG(st.st_mode):
                paths.append(rel_f)
            else:
                _disclose(rel_f, "not a regular file")

    paths.sort()
    if excluded_list is not None:
        excluded_list.sort(key=lambda item: item["path"])
    return paths


# ──────────────────────────────────────────────────────────────────────
# 2-Phase 퍼지 매칭
# ──────────────────────────────────────────────────────────────────────
def _common_trailing_parts(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """Count identical directory names shared from the innermost level up."""
    count = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x != y:
            break
        count += 1
    return count


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
        파일명 점수가 같으면 (1) 안쪽부터 이름이 같은 상위 디렉토리 수,
        (2) 상위 디렉토리 경로의 ``fuzz.ratio``, (3) 입력 순서로 결정한다.
        보고되는 유사도는 항상 파일명(basename) 점수다.

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
        # M1: O(R²) 안전장치 — R이 커지면 fuzz.ratio() 호출이 폭발적으로 증가
        r_size = len(remaining_a) * len(remaining_b)
        if r_size > 250_000:  # 500×500 = 250K comparisons ≈ 수십 초
            import logging
            logging.getLogger(__name__).warning(
                "Fuzzy matching: %d by %d unmatched files, %d comparisons; this may take "
                "a while. Consider using --threshold to reduce false matches.",
                len(remaining_a), len(remaining_b), r_size,
            )
        # Score on the basename, not the full relative path: 'Name Sim.' means
        # filename similarity. Full-path scoring falsely matched files sharing a
        # long directory prefix and missed same-named files in differently-named
        # subtrees (old/src/util.py vs new/lib/util.py) — the renamed/moved case.
        names_a = [PurePosixPath(fa).name for _, fa in remaining_a]
        names_b = [PurePosixPath(fb).name for _, fb in remaining_b]
        dirs_a = [PurePosixPath(fa).parent.parts for _, fa in remaining_a]
        dirs_b = [PurePosixPath(fb).parent.parts for _, fb in remaining_b]
        candidates: list[Tuple[float, int, float, int, int]] = []
        for ri, (i, fa) in enumerate(remaining_a):
            for rj, (j, fb) in enumerate(remaining_b):
                score = fuzz.ratio(names_a[ri], names_b[rj])
                if score >= threshold:
                    # Tie-breaks only (the reported similarity stays the
                    # basename score): prefer the counterpart whose nearest
                    # parent directories have the same names, then the more
                    # similar parent path, then input order (deterministic).
                    shared_dirs = _common_trailing_parts(dirs_a[ri], dirs_b[rj])
                    dir_score = fuzz.ratio("/".join(dirs_a[ri]), "/".join(dirs_b[rj]))
                    candidates.append((score, shared_dirs, dir_score, ri, rj))

        # score 내림차순 정렬 → greedy best-first 할당.  동점(같은 파일명이
        # 여러 개)이면 디렉토리 근접도로 결정한다 — 정렬 순서에 맡기지 않는다.
        candidates.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3], x[4]))

        used_ri: set[int] = set()
        used_rj: set[int] = set()
        for score, _shared, _dir_score, ri, rj in candidates:
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
