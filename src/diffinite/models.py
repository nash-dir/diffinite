"""Diffinite 전역 데이터 모델.

패키지 전역에서 사용하는 데이터클래스를 중앙 정의한다.
순환 의존을 방지하기 위해 이 모듈은 **어떤 diffinite 하위 모듈도 import하지 않는다**.

설계 원칙:
    - 불변 VO(Value Object)는 ``frozen=True``로 선언하여 해싱·비교 안전성을 보장한다.
    - 가변 결과 객체는 ``field(default_factory=...)`` 패턴으로 mutable default 방지.
    - 법정 제출물에 포함되는 수치(ratio, similarity)는 float으로 통일하되,
      인터페이스 경계에서 반올림 책임은 호출쪽에 둔다.

의존:
    - 표준 라이브러리만 사용 (dataclasses, typing).
    - 외부·내부 패키지 import 금지 — 다른 모든 모듈이 이 모듈을 import한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# 언어별 주석 사양
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CommentSpec:
    """특정 언어의 주석 마커 사양.

    ``parser.py``의 2-pass 주석 제거 상태 머신이 이 값을 참조한다.
    ``languages/`` 레지스트리에서 확장자별로 ``LangSpec.comment``에 설정됨.

    주의:
        ``block_start``/``block_end``는 반드시 쌍으로 설정해야 한다.
        한쪽만 None이면 ``_strip_2pass`` 상태 머신이 블록 종료를 감지하지 못한다.
    """

    line_markers: tuple[str, ...] = ()
    """단일행 주석 시작 마커들. 예: ``("//",)``, ``("#",)``"""

    block_start: Optional[str] = None
    """블록 주석 시작. 예: ``"/*"``. None이면 블록 주석 없음."""

    block_end: Optional[str] = None
    """블록 주석 종료. 예: ``"*/"``. ``block_start``와 반드시 쌍."""

    string_delims: tuple[str, ...] = ('"', "'")
    """문자열 리터럴을 여는 따옴표들. 빈 튜플이면 따옴표를 **데이터**로 취급한다
    (HTML/XML/SVG/CSS — 따옴표는 속성·값일 뿐이며, 그 때문에 주석 마커가
    문자열 안에 갇혀 제거되지 않는 오류를 막는다). 트리플 쿼트(\"\"\", ''')는
    동일 따옴표가 포함돼 있으면 자동 인식된다."""

    template_delims: tuple[str, ...] = ("`",)
    """템플릿/원시 문자열 리터럴 구분자(JS 템플릿 리터럴, Go 원시 문자열).
    빈 튜플이면 백틱을 일반 문자로 취급한다."""

    has_regex_literals: bool = False
    """JS 계열 정규식 리터럴(``/regex/``) 인식 여부. True면 식이 올 수 있는 위치의
    ``/``를 정규식 시작으로 보아, 정규식 내부의 ``/*``·``//`` 를 주석으로 오인해
    실제 코드를 삭제하는 오류를 막는다."""

    block_markers_line_anchored: bool = False
    """블록 주석 마커가 행의 컬럼 0에서만 유효한지 여부(Ruby ``=begin``/``=end``).
    True면 들여쓰기되거나 식 중간에 나타난 마커는 주석으로 보지 않는다."""


# ──────────────────────────────────────────────────────────────────────
# 1:1 파일 매칭 결과
# ──────────────────────────────────────────────────────────────────────
@dataclass
class FileMatch:
    """두 디렉토리 간 1:1 매칭된 파일 쌍.

    ``collector.match_files()``가 생성한다.
    ``similarity``는 ``rapidfuzz.fuzz.ratio()`` 결과(0–100)이며,
    exact match 시 100.0이 설정된다.
    """

    rel_path_a: str
    """디렉토리 A 기준 상대경로 (POSIX 스타일)"""

    rel_path_b: str
    """디렉토리 B 기준 상대경로"""

    similarity: float
    """파일명 유사도 (0–100). exact match = 100.0"""


# ──────────────────────────────────────────────────────────────────────
# Diff 결과
# ──────────────────────────────────────────────────────────────────────
@dataclass
class DiffResult:
    """단일 파일 쌍의 diff 분석 결과.

    ``differ.compute_diff()`` + ``differ.generate_html_diff()`` 출력을 통합한다.
    ``pipeline.py``에서 2-pass로 구성: 1차에서 ratio/additions/deletions 계산,
    전체 파일의 최대 라인수로 ``ln_col_width`` 결정 후 2차에서 ``html_diff`` 최종 생성.

    ``error``가 설정된 경우 다른 필드(ratio 등)는 의미 없는 기본값이다.
    보고서 렌더러는 ``error is not None``을 먼저 확인해야 한다.
    """

    match: FileMatch
    ratio: float
    """내용 유사도 (0.0–1.0). ``difflib.SequenceMatcher.ratio()`` 결과."""

    additions: int
    """B에 추가된 라인(또는 단어) 수"""

    deletions: int
    """A에서 삭제된 라인(또는 단어) 수"""

    html_diff: str
    """Side-by-side HTML diff 테이블. Pygments 구문 강조 포함."""

    error: Optional[str] = None
    """None이 아니면 디코딩/읽기 실패 등의 에러 메시지. 이 경우 위 필드는 0/빈값."""

    binary: bool = False
    """True if file pair was detected as binary (non-decodable)."""

    hash_match: Optional[bool] = None
    """SHA-256 match status for binary files. None for text files."""

    html_diff_truncated: bool = False
    """True when the inline diff payload was omitted because it exceeded the limit."""

    html_diff_truncation_reason: Optional[str] = None
    """Machine-readable reason for omitting the inline diff payload."""

    html_diff_original_bytes: Optional[int] = None
    """UTF-8 byte size of the generated diff before it was omitted."""

    html_diff_omitted_bytes: Optional[int] = None
    """Number of original diff bytes omitted from serialized/display output."""


# ──────────────────────────────────────────────────────────────────────
# Winnowing 핑거프린트 엔트리
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FingerprintEntry:
    """Winnowing 알고리즘이 선택한 단일 핑거프린트.

    ``fingerprint.winnow()``가 윈도우 내 최소 해시를 선택할 때 생성한다.
    ``frozen=True``로 set/dict의 원소로 안전하게 사용 가능.

    ``position``은 토큰 레벨 오프셋이다 (바이트/문자 오프셋 아님).
    원본 소스 위치를 역추적하려면 토큰 배열과의 인덱스 매핑이 필요하다.
    """

    hash_value: int
    """Karp-Rabin 롤링 해시 값 (mod 2^61-1). 비적대적 입력에서 충돌은 무시할 수준."""

    position: int
    """K-gram이 시작하는 토큰 인덱스 (0-based)."""


# ──────────────────────────────────────────────────────────────────────
# N:M Deep Compare 결과
# ──────────────────────────────────────────────────────────────────────
@dataclass
class DeepMatchResult:
    """A-파일 하나에 대한 N:M 크로스매칭 결과.

    ``deep_compare.run_deep_compare()``가 생성한다. 하나의 A-파일이
    여러 B-파일과 매칭될 수 있으므로 ``matched_files_b``는 리스트.
    """

    file_a: str
    """디렉토리 A 기준 상대경로."""

    matched_files_b: list[tuple[str, int, float, bool]] = field(default_factory=list)
    """매칭된 B-파일 목록. 각 원소:
    ``(rel_path_b, shared_hash_count, jaccard, inconclusive)``.
    ``inconclusive`` 는 normalize 모드에서 두 파일 중 작은 쪽 토큰 수가 보정 floor
    (calibration.INCONCLUSIVE_TOKEN_FLOOR) 미만이라 확정 판정을 보류해야 함을 뜻한다.
    Jaccard 내림차순 정렬."""

    fingerprint_count_a: int = 0
    """A-파일에서 winnowing이 선택한 위치 수 (중복 해시 포함).
    Jaccard/containment의 분모가 아니다 — 분모는 ``unique_hashes_a``."""

    unique_hashes_a: int = 0
    """A-파일의 고유 핑거프린트 해시 수 (|A|). Jaccard·containment가 쓰는 집합 크기."""

    unique_hashes_b: dict[str, int] = field(default_factory=dict)
    """매칭된 각 B-파일의 고유 핑거프린트 해시 수 (|B|)."""

    def containment(self, b_file: str, shared: int) -> tuple[float, float]:
        """방향성 포함도 ``(|A∩B|/|A|, |A∩B|/|B|)`` — 원본 기준 / 비교본 기준 비율.

        Jaccard는 합집합 대비 비율이라 큰 파일에 작은 파일이 통째로 들어가도
        낮게 나온다. 포함도는 "A의 지문 중 몇 %가 B에도 있는가"를 그대로 말한다.
        (JPlag·Dolos의 방향별 유사도, 국내 감정의 원본/비교본 기준 비율과 유사한 개념이나,
        분모는 토큰·라인이 아니라 고유 winnowing 지문 해시 수다.)
        """
        size_b = self.unique_hashes_b.get(b_file, 0)
        a_in_b = round(shared / self.unique_hashes_a, 4) if self.unique_hashes_a else 0.0
        b_in_a = round(shared / size_b, 4) if size_b else 0.0
        return a_in_b, b_in_a


# ──────────────────────────────────────────────────────────────────────
# 분석 메타데이터 (보고서 재현가능성 보장)
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class AnalysisMetadata:
    """보고서에 기록되는 실행 파라미터.

    모든 보고서(PDF/HTML/MD)의 헤더에 이 정보가 포함되어,
    **동일 파라미터로 분석을 재현**할 수 있도록 보장한다.
    법정 제출물의 감정서 신뢰성 확보에 필수.

    ``frozen=True``로 생성 후 변경 불가 — 보고서 무결성 보장.
    """

    exec_mode: str
    """``"simple"`` 또는 ``"deep"``. deep은 N:M Winnowing 포함."""

    k: int
    """K-gram 크기. 커질수록 정밀도 ↑ / 재현율 ↓."""

    w: int
    """Winnowing 윈도우 크기. 밀도 보장: >=(W+K-1) 토큰 공유 시 반드시 탐지."""

    threshold: float
    """최소 Jaccard 유사도 임계값을 **0–100 백분율 스케일**로 기록한다
    (CLI ``--threshold-deep`` 와 동일 스케일). 예: 5.0 = 5%. 이 값은 보고서
    표시·재현용 기록이며, 실제 필터링은 0–1 내부 값으로 별도 수행된다.
    두 생성 경로(CLI/라이브러리)가 같은 스케일을 쓰도록 통일됨."""

    autojunk: bool = True
    """``difflib.SequenceMatcher``의 autojunk 옵션.
    False(``--no-autojunk``)로 설정하면 모든 토큰을 동등 취급하여
    포렌식 정밀 분석에 적합하지만 대형 파일에서 성능이 저하된다."""

    deep_index_truncated: bool = False
    """Deep 모드의 역 인덱스가 ``--max-index-entries`` 상한에서 잘렸는지 여부.
    True이면 일부 크로스매치가 누락되어 유사도가 **과소보고**될 수 있으므로,
    보고서에 경고를 표기해 '완전한 결과'로 오인되지 않게 한다."""

    # NOTE: fields below are appended AFTER the historical fields above so that
    # positional construction `AnalysisMetadata("deep", 5, 4, 5.0, autojunk, ...)`
    # keeps its original meaning. Do not insert new fields mid-struct.
    threshold_provenance: str = "legacy-uncalibrated"
    """``threshold`` 값의 출처: ``"user"`` (명시 지정),
    ``"legacy-uncalibrated"`` (raw 호환 기본값), ``"normalize-default"``
    (normalize 채널 보정 기본값, calibration.py). 보고서가 임계값의 출처를
    명시해 감정 재현성·방어력을 높인다."""

    normalize: bool = False
    """``--normalize`` 식별자·리터럴 정규화 사용 여부. True이면 식별자가 평탄화되어
    위양성률 특성이 달라지므로(calibration.py), 보고서가 채널·임계값·측정 오류율을
    공시할 수 있도록 기록한다."""

    lang_aware: bool = False
    """언어 인식 정규화(``--lang-aware``) 사용 여부. True이면 deep 모드 핑거프린트가
    언어별 키워드 인식(Pygments lexer / 레지스트리)으로 생성되어, 기본(언어 무관)
    정규화와 **핑거프린트가 호환되지 않는다** — 보고서에 채널을 명시해 둔다."""

    ignore_patterns: tuple[str, ...] = ()
    """실제로 적용된 제외 규칙. 설정 파일의 절대경로 대신 유효 규칙 자체를
    기록해 개인정보를 노출하지 않으면서 수집 대상을 재현한다."""

    ignore_file_sha256: str | None = None
    """읽은 제외 파일 원본 바이트의 SHA-256. 주석·개행까지 같은 정책 파일인지
    외부 원본과 대조할 수 있으며, 파일 경로는 기록하지 않는다."""

    filter_applied: bool = False
    """2단계 선택 필터가 적용되었는지 여부. 빈 필터와 미적용을 구분한다."""

    filter_paths: tuple[str, ...] = ()
    """실제로 선택된 A측 상대경로의 정렬된 목록."""

    filter_file_sha256: str | None = None
    """선택 JSON 원본 바이트의 SHA-256. 임시 파일의 절대경로는 기록하지 않는다."""

    strip_comments: bool | None = None
    """Deep fingerprint 입력에 실제 적용된 주석 제거 여부. ``None``은 구형
    호출자가 이 의미론적 설정을 기록하지 않아 알 수 없음을 뜻한다."""

    calibration_profile_id: str | None = None
    """normalize 오류율 수치를 산출한 버전 고정 검증 프로필 식별자."""

    calibration_status: str = "not-assessed"
    """검증 수치 적용 상태: ``applicable``, ``unvalidated-profile``,
    ``off-calibration-threshold``, ``not-applicable`` 또는 ``not-assessed``."""

    calibration_profile_mismatches: tuple[str, ...] = ()
    """검증 프로필과 다른 실제 설정 필드명. 빈 튜플은 차이가 없거나
    아직 평가되지 않았다는 뜻이므로 ``calibration_status``와 함께 해석한다."""

    calibration_threshold_matches: bool | None = None
    """실제 threshold가 검증 프로필의 측정 지점과 같은지 여부."""

    filename_threshold: float | None = None
    """A/B의 1:1 파일명 매칭에 적용된 최소 유사도(0–100). Deep Jaccard
    ``threshold``와 의미가 다르므로 별도 기록한다."""

    by_word: bool | None = None
    """라인 단위 대신 단어 단위 difflib 비교를 실제 적용했는지 여부."""

    squash_blanks: bool | None = None
    """주석 제거 뒤 연속 빈 줄을 축약했는지 여부. 주석 제거가 꺼져 있으면
    실제 효과가 없으므로 실행 경로는 False를 기록한다."""

    normalize_whitespace: bool | None = None
    """라인/단어 diff에서 공백을 정규화했는지 여부."""

    encoding: str = "unknown"
    """실제 디코딩 정책. 자동 감지는 ``"auto"``, 명시 인코딩은 그 이름을 기록한다."""

    binary_handling: str = "unknown"
    """디코딩 불가능 파일 정책: ``exclude``, ``hash`` 또는 ``error``."""

    max_file_size_mb: float | None = None
    """텍스트 분석 대신 해시 경로를 선택하거나 deep 분석을 건너뛰는 파일 크기 상한."""

    max_diff_html_size_mb: float | None = None
    """inline diff payload를 완전히 대체하는 UTF-8 HTML 크기 상한."""

    max_index_entries: int | None = None
    """Deep Compare 역색인의 최대 항목 수. 상한 도달 시 결과가 과소보고될 수 있다."""

    detect_moved: bool | None = None
    """렌더링 diff에서 이동 블록 탐지를 실제 요청했는지 여부."""

    collapse_identical: bool | None = None
    """동일 문맥을 축약해 제한된 주변 줄만 렌더링했는지 여부."""

    metrics_only: bool | None = None
    """점수만 계산하고 inline diff payload를 만들지 않은 실행인지 여부."""

    uncompared_mode: str = "unknown"
    """미비교 파일 목록의 보고 정책: ``inline``, ``separate`` 또는 ``none``."""

    allow_partial: bool | None = None
    """일부 입력/worker 실패를 명시적 불완전 보고서로 허용한 정책인지 여부."""


@dataclass
class AnalysisStatus:
    """Completeness accounting shared by JSON and human-readable reports."""

    allow_partial: bool = False
    reasons: list[str] = field(default_factory=list)
    diff_requested_pair_count: int = 0
    diff_successful_pair_count: int = 0
    diff_failed_pairs: list[dict[str, str]] = field(default_factory=list)
    deep_requested_file_count: int = 0
    deep_successful_file_count: int = 0
    deep_failed_files: list[dict[str, str]] = field(default_factory=list)
    deep_skipped_binary_files: list[dict[str, str]] = field(default_factory=list)
    deep_index_truncated: bool = False
    diff_truncated_count: int = 0
    # Appended to preserve positional compatibility with the historical fields.
    collection_failed_files: list[dict[str, str]] = field(default_factory=list)

    @property
    def state(self) -> str:
        return "incomplete" if self.reasons else "complete"

    def mark_incomplete(self, reason: str) -> None:
        if reason not in self.reasons:
            self.reasons.append(reason)

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "reasons": list(self.reasons),
            "allow_partial": self.allow_partial,
            "collection": {
                "failed_file_count": len(self.collection_failed_files),
                "failed_files": list(self.collection_failed_files),
            },
            "diff": {
                "requested_pair_count": self.diff_requested_pair_count,
                "successful_pair_count": self.diff_successful_pair_count,
                "failed_pair_count": len(self.diff_failed_pairs),
                "failed_pairs": list(self.diff_failed_pairs),
            },
            "deep": {
                "requested_file_count": self.deep_requested_file_count,
                "successful_file_count": self.deep_successful_file_count,
                "failed_file_count": len(self.deep_failed_files),
                "failed_files": list(self.deep_failed_files),
                "skipped_binary_file_count": len(self.deep_skipped_binary_files),
                "skipped_binary_files": list(self.deep_skipped_binary_files),
            },
            "truncation": {
                "deep_index_truncated": self.deep_index_truncated,
                "diff_truncated_count": self.diff_truncated_count,
            },
        }


# ──────────────────────────────────────────────────────────────────────
# 파일 해시 엔트리 (증거 무결성)
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FileHashEntry:
    """분석 대상 파일 하나의 SHA-256 해시 기록.

    ``evidence.compute_file_hashes()``가 생성한다.
    ``manifest.sha256.json``과 ``--hash`` 리포트 테이블에 사용.

    ``frozen=True``로 생성 후 변경 불가 — 무결성 기록의 불변성 보장.
    """

    rel_path: str
    """디렉토리 기준 상대경로 (POSIX 스타일)."""

    sha256: str
    """SHA-256 hex digest (64자)."""

    size_bytes: int
    """파일 크기 (바이트)."""

    modified_at: str
    """파일 최종 수정 시각 (ISO 8601)."""


# ──────────────────────────────────────────────────────────────────────
# Moved Block 탐지 결과
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MovedBlock:
    """이동된 코드 블록 하나를 나타내는 VO.

    ``differ.detect_moved_blocks()``가 생성한다.
    delete 영역(A-side)의 줄들이 insert 영역(B-side)으로 이동한 것을 의미한다.

    ``a_lines``/``b_lines`` 는 **실제로 매칭된 줄 인덱스의 1:1 쌍**이다
    (``a_lines[i]`` ↔ ``b_lines[i]``, 동일 길이). 연속 범위(start..end)가 아니라
    실제 매칭 줄만 담으므로, 블록 사이의 매칭되지 않은 줄(gap)이 '이동'으로
    잘못 표시되거나 A/B 길이가 어긋나는 일이 없다.

    ``frozen=True``로 불변 — 결과 집합의 안정성 보장.
    """

    a_lines: tuple[int, ...]
    """A-side 매칭 줄 인덱스 (0-based, 오름차순)."""

    b_lines: tuple[int, ...]
    """B-side 매칭 줄 인덱스 (``a_lines`` 와 1:1 대응, 동일 길이)."""

    move_id: int = 0
    """고유 이동 ID. 같은 move_id를 가진 del/ins 줄은 시각적으로 페어링된다."""
