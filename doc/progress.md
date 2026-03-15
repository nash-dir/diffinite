# Diffinite 프로젝트 진척 기록

> **문서 갱신일**: 2026-03-15  
> **버전**: 0.3.0  
> **브랜치**: `dev` (main 미반영)

---

## 프로젝트 요약

Diffinite는 **IP 소송, 코드 감사, 소프트웨어 표절 포렌식**을 위한 소스코드 비교 도구이다.
두 디렉토리의 소스코드를 비교하여 다중 증거 채널 분석 결과를 PDF/HTML/Markdown 보고서로 생성한다.

---

## 주요 마일스톤

### Phase 1 — 기반 구축 (2026-03-13)
| 항목 | 상태 | 비고 |
|------|:----:|------|
| Winnowing 핑거프린트 엔진 (`fingerprint.py`) | ✅ | K-gram, Rolling Hash, Winnow |
| 2-Pass 주석 제거 파서 (`parser.py`) | ✅ | 4-state → 5-state 상태 머신 |
| Diff 엔진 (`differ.py`) | ✅ | `difflib` + `Pygments` 구문 강조 |
| 파일 수집/매칭 (`collector.py`) | ✅ | 2-phase exact + fuzzy |
| PDF/HTML/MD 보고서 (`pdf_gen.py`, `pipeline.py`) | ✅ | Divide-and-conquer, Bates 번호 |
| CLI (`cli.py`) | ✅ | 3-Tier 파라미터, simple/deep 모드 |
| 모듈 테스트 커버리지 감사 | ✅ | 250+ 테스트 |

### Phase 2 — Deep Compare & 다중 증거 (2026-03-14)
| 항목 | 상태 | 비고 |
|------|:----:|------|
| N:M 크로스매칭 엔진 (`deep_compare.py`) | ✅ | 역 인덱스 + 병렬 추출 |
| AST/PDG 정규화 (`ast_normalizer.py`) | ✅ | tree-sitter 기반 |
| 6채널 증거 분석 (`evidence.py`) | ✅ | ROC AUC 비례 가중치 |
| 2단계 분류 체계 (Strict + Relaxed) | ✅ | Recall +22.5% |
| AFC 파이프라인 (Altai 3단계) | ✅ | Abstraction-Filtration-Comparison |
| 법리 델타 분석 (IDEX) | ✅ | 5패턴 분류 |
| 언어 레지스트리 리팩토링 (`languages/`) | ✅ | `LangSpec` dataclass + 13 모듈 |

### Phase 3 — TDD Corpus Pipeline (2026-03-14~15)
| 항목 | 상태 | 비고 |
|------|:----:|------|
| Stage 1: IR-Plag 감도 프로파일링 | ✅ | L1-L6 6단계 검증 |
| Stage 2-5: 코퍼스 확장/검증 | ✅ | 646쌍 기준 |
| Stage 6: 도메인 수렴 방어 | ✅ | Guava↔JDK, Apache↔JDK |
| Stage 7: 부정 제어 (Negative Control) | ✅ | FP 78% 감소 |
| Stage 8: Grid Search 최적화 | ✅ | 84K 조합, Precision 95.5% |
| 소스코드 Annotation (9 core + 3 peripheral) | ✅ | 시니어 아키텍트 수준 |
| TF-IDF / Boilerplate Filtering | ✅ | 보일러플레이트 자동 제외 |
| Comment 채널 강화 | ✅ | License filter, Javadoc stopwords |

### Phase 4 — 고도화 6건 (2026-03-15)
| # | 항목 | 상태 | 변경 파일 |
|:-:|------|:----:|----------|
| 5 | `_TOKEN_RE` 중복 통합 | ✅ | `fingerprint.py`, `evidence.py` |
| 6 | `autojunk` CLI 노출 | ✅ | `differ.py`, `cli.py`, `pipeline.py`, `models.py` |
| 1 | 분류 임계값 dataclass 외부화 | ✅ | `models.py`, `evidence.py` |
| 4 | JS 템플릿 리터럴 파서 보완 | ✅ | `parser.py`, `test_parser.py` |
| 2 | IDEX 임계값 외부화 | ✅ | `models.py`, `evidence.py`, `idex_threshold_calibration.py` |
| 3 | 역 인덱스 메모리 제한 | ✅ | `deep_compare.py`, `cli.py`, `pipeline.py` |

---

## 현재 코드베이스 통계

| 항목 | 수치 |
|------|:----:|
| 소스 모듈 | 26 `.py` (core 14 + `languages/` 12) |
| 단위/통합 테스트 | 253 passed, 4 skipped |
| TDD 코퍼스 테스트 | 50+ (별도 디렉토리) |
| 지원 언어 | 30+ 확장자 |
| 문서 | `doc/` 7파일 |
| 프로파일 | `industrial` / `academic` |

---

## 아키텍처 변경 이력 (고도화 상세)

### `TOKEN_RE` 통합 (#5)
- `_TOKEN_RE` (private) → `TOKEN_RE` (public) in `fingerprint.py`
- `evidence.py`: 로컬 정의 제거, import로 교체
- **근거**: 두 모듈의 토크나이저 불일치 시 채널 간 점수 비교 무의미

### `autojunk` CLI 노출 (#6)
- `compute_diff()`, `generate_html_diff()`에 `autojunk` 파라미터 추가
- `--no-autojunk` CLI 플래그 + `AnalysisMetadata.autojunk` 필드
- **근거**: `autojunk=True`는 대규모 파일에서 1,824× 빠르지만 세미콜론/중괄호를 junk 처리 → 포렌식 정밀 분석 시 비활성화 필요

### 분류 임계값 dataclass (#1)
- `_CLASSIFICATION_PROFILES` dict + 14개 모듈 상수 → `ClassificationThresholds` frozen dataclass (18 필드)
- `INDUSTRIAL_THRESHOLDS`, `ACADEMIC_THRESHOLDS` 인스턴스
- **근거**: IDE 자동완성, 타입 안전성, 프로파일 추가 시 1줄로 가능

### JS 템플릿 리터럴 파서 (#4)
- `_State.IN_TEMPLATE_LITERAL` 추가 (4-state → 5-state)
- `template_depth` 카운터로 `${...}` 중첩 추적
- **근거**: 기존 파서는 백틱을 일반 문자열로 취급 → `${expr /* comment */}` 내부 코드를 문자열로 오인

### IDEX 임계값 외부화 (#2)
- `IDEXThresholds` frozen dataclass (8 필드) in `models.py`
- 매직넘버 8개 (`0.20`, `0.70`, `0.40` 등) → 필드 참조로 교체
- **근거**: 코퍼스 ROC AUC 교정 시 코드 수정 없이 기본값만 변경 가능

### 역 인덱스 메모리 제한 (#3)
- `build_inverted_index(max_entries=10_000_000)` 추가
- 초과 시 `logger.warning()` + truncated index 반환 (graceful degradation)
- `--max-index-entries N` CLI 옵션
- **근거**: 대규모 코퍼스에서 역 인덱스가 수 GB로 증가 → OOM 방지

---

## 미완료 / 향후 과제

| 항목 | 상태 | 비고 |
|------|:----:|------|
| SOCO test set 코퍼스 확장 | 보류 | 사용자 지시 대기 |
| IDEX 임계값 교정 (ROC AUC) | 스크립트 준비 | `TDD/corpus/idex_threshold_calibration.py` |
| MinHash + LSH 근사 인덱싱 | 미착수 | `datasketch` 라이브러리 검토 |
| PDG 병렬 분석 (Phase 4) | 미착수 | Use-Def 체인 분석 |
