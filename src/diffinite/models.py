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
    """Rabin 롤링 해시 값 (mod 2^61-1). 충돌 확률 ≈ 1/2^61."""

    position: int
    """K-gram이 시작하는 토큰 인덱스 (0-based)."""


# ──────────────────────────────────────────────────────────────────────
# N:M Deep Compare 결과
# ──────────────────────────────────────────────────────────────────────
@dataclass
class DeepMatchResult:
    """A-파일 하나에 대한 N:M 크로스매칭 결과.

    ``deep_compare._run_multi_channel()``이 생성한다. 하나의 A-파일이
    여러 B-파일과 매칭될 수 있으므로 ``matched_files_b``는 리스트.

    ``channel_scores``, ``classification``, ``afc_results``는 multi-channel
    모드에서만 채워진다. single-channel 모드에서는 모두 빈 dict.

    보고서 렌더러(``pdf_gen``, ``pipeline``)는 ``channel_scores``의 존재 여부로
    multi/single 모드를 판별한다.
    """

    file_a: str
    """디렉토리 A 기준 상대경로."""

    matched_files_b: list[tuple[str, int, float]] = field(default_factory=list)
    """매칭된 B-파일 목록. 각 원소: ``(rel_path_b, shared_hash_count, jaccard)``.
    Jaccard 내림차순 정렬."""

    fingerprint_count_a: int = 0
    """A-파일의 총 핑거프린트 수. multi-channel 시 모든 채널 합산값."""

    channel_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    """B-파일별 6채널 스코어. Key=rel_path_b, Value={"raw_winnowing": 0.85, ...}.
    ``evidence.compute_channel_scores()`` 출력을 직접 저장."""

    classification: dict[str, str] = field(default_factory=dict)
    """B-파일별 분류 레이블. Key=rel_path_b, Value="DIRECT_COPY" 등.
    ``evidence.classify_similarity_pattern()`` 출력."""

    afc_results: dict[str, dict] = field(default_factory=dict)
    """B-파일별 AFC 분석 결과. Key=rel_path_b, Value={"classification": ..., "filtration_report": [...]}.
    optional — AFC 실패 시 해당 키 없음."""


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

    profile: str
    """``"industrial"`` 또는 ``"academic"``. 프로파일별 K/W/T 프리셋 결정."""

    k: int
    """K-gram 크기. 커질수록 정밀도 ↑ / 재현율 ↓."""

    w: int
    """Winnowing 윈도우 크기. 밀도 보장: ≥(W+K-1) 토큰 공유 시 반드시 탐지."""

    threshold: float
    """최소 Jaccard 유사도 임계값. 이 미만의 매칭은 결과에서 제외."""

    tokenizer: str = "token"
    """``"token"`` / ``"ast"`` / ``"pdg"``. AST/PDG는 tree-sitter 필요."""

    grid_search: bool = False
    """True이면 K×W 감도 분석(grid search)이 수행됨."""
