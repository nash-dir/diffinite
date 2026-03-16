# Cherrypick 전략: "Trustworthy Toaster" 빌드

> **작성일**: 2026-03-16  
> **목표**: 변호사가 신뢰할 수 있는 단순한 도구. "얼마나, 어디가 비슷한지"만 보고한다.  
> **원칙**: 모든 수치 상수에 대해 "이 값이 왜 이 값인지" 한 문장으로 설명할 수 있어야 한다.

---

## 1. 브랜치 전략

```
master (diffinite.py 단일 파일, src/ 패키지 없음)
  └── dev (src/diffinite/ 14 모듈, 253 tests)
        └── dev2 ← 여기서 수술 (불필요한 것 제거)
```

**핵심 결정**: master에는 `src/` 패키지가 없고 `diffinite.py` 단일 파일만 존재한다.
cherry-pick보다 **dev에서 분기 후 제거(prune)**하는 것이 현실적이다.

---

## 2. 파일별 판정

### 2.1 그대로 유지 (손 안 댐)

| 파일 | 줄 수 | 이유 |
|------|:-----:|------|
| `__init__.py` | ~5 | 버전 문자열 |
| `__main__.py` | ~3 | 진입점 |
| `collector.py` | 111 | 표준 파일 매칭 |
| `differ.py` | ~290 | difflib 래퍼 + Pygments. `autojunk` param 포함 |
| `pdf_gen.py` | ~740 | 보고서 렌더링 |
| `languages/_spec.py` | 39 | LangSpec dataclass |
| `languages/_registry.py` | 51 | 레지스트리 메커니즘 |
| `languages/_defaults.py` | 72 | 기본 AST 노드 |
| `languages/python.py` | 36 | 언어 사양 |
| `languages/java.py` | 58 | 언어 사양 |
| `languages/javascript.py` | 62 | 언어 사양 |
| `languages/c_family.py` | 51 | 언어 사양 |
| `languages/csharp.py` | 38 | 언어 사양 |
| `languages/go_rust_swift.py` | 66 | 언어 사양 |
| `languages/scripting.py` | 76 | 언어 사양 |
| `languages/markup.py` | 46 | 언어 사양 |
| `languages/data.py` | 36 | 언어 사양 |
| `languages/__init__.py` | 36 | 자동 import |

### 2.2 유지하되 수정

| 파일 | 변경 내용 |
|------|----------|
| `fingerprint.py` (~264줄) | `TOKEN_RE` (public) — 유지. K/W 기본값 주석에 근거 보강: "Schleimer 2003, §4.2 권장 범위" |
| `parser.py` (~400줄) | 5-state FSM. `#if 0` 전처리. 모두 유지. 주석만 정리 (과도한 annotation 제거) |
| `models.py` (~290줄) | **대폭 축소**: `CommentSpec`, `FileMatch`, `DiffResult`, `FingerprintEntry`, `DeepMatchResult`, `AnalysisMetadata`만 유지. `ClassificationThresholds`(18필드) 삭제. `IDEXThresholds`(8필드) 삭제. `AnalysisMetadata`에서 불필요 필드 정리 |
| `deep_compare.py` (~466줄) | `_run_multi_channel()` 제거 → `_run_single_channel()`만 유지. `max_entries` 유지. `DeepMatchResult`에서 `channel_scores`, `classification`, `afc_results` 필드 제거 → `jaccard` 하나만 |
| `cli.py` (~360줄) | `--profile`, `--grid-search`, `--multi-channel`, `--tokenizer` 제거. 남길 것: `--mode`, `--k-gram`, `--window`, `--threshold-deep`, `--workers`, `--normalize`, `--no-autojunk`, `--max-index-entries`, 출력 옵션들 |
| `pipeline.py` (~780줄) | `_run_grid_search()` 제거. `multi_channel` 전파 코드 제거. 증거 채널 관련 보고서 섹션 단순화 |

### 2.3 대폭 축소 (핵심 수술)

| 파일 | 현재 | dev2 목표 | 변경 |
|------|:----:|:---------:|------|
| `evidence.py` | 1168줄 | **~150줄** | 아래 §3 참조 |

### 2.4 삭제

| 파일 | 이유 |
|------|------|
| `ast_normalizer.py` (905줄) | tree-sitter 의존성 제거. AST/PDG 채널은 검증 전 불포함 |

---

## 3. evidence.py 수술 상세

### 남길 것 (설명 가능한 메트릭)

```python
def compute_similarity(
    fp_raw_a: set[int], fp_raw_b: set[int],
    source_a: str, source_b: str,
    cleaned_a: str, cleaned_b: str,
) -> dict[str, float]:
    """Winnowing Jaccard + identifier cosine.

    Returns:
        {"jaccard": 0.73, "identifier_cosine": 0.65}
    """
```

| 메트릭 | 수식 | 설명 가능성 |
|--------|------|------------|
| `jaccard` | `|A∩B| / |A∪B|` | "두 파일의 코드 지문 중 73%가 일치합니다" |
| `identifier_cosine` | `cos(tf_a, tf_b)` | "변수/함수 이름의 사용 패턴이 65% 유사합니다" |

### 삭제할 것

| 대상 | 줄 수 (추정) | 이유 |
|------|:-----------:|------|
| `normalized_winnowing` 채널 | ~30 | raw와 상관 >0.9, 이중 계산 |
| `ast_winnowing` 채널 | ~30 | tree-sitter 의존, 독립 가치 미검증 |
| `declaration_cosine` 채널 | ~60 | ROC AUC 0.550 — 노이즈 수준 |
| `comment_string_overlap` + TF-IDF | ~100 | IDF 코퍼스 불필요. 주석은 이미 strip 후 비교 |
| `_classify_strict()` | ~50 | 18-파라미터 매직넘버 분류기 |
| `_classify_relaxed()` | ~50 | 상동 |
| `INDUSTRIAL_THRESHOLDS` / `ACADEMIC_THRESHOLDS` | ~40 | 프로파일 시스템 전체 제거 |
| `_get_thresholds()` | ~10 | 상동 |
| `afc_analysis()` | ~120 | AFC 인플레이션 보정 hand-tuned |
| `analyze_legal_defense_pattern()` | ~80 | IDEX 8개 매직넘버 |
| `compute_channel_scores()` 6채널 | ~80 | 2채널 `compute_similarity()`로 교체 |
| `_CLASSIFICATION_PROFILES` backward compat | ~20 | 삭제 |
| TF-IDF 인프라 (`_build_idf`, `_tfidf_vector` 등) | ~80 | 단일 비교 시 코퍼스 없음 → 사용 불가 |
| `_COMMON_KEYWORDS` 267개 | ~30 | identifier_cosine 내장으로 남김 |
| `_JAVA_TYPE_STOPWORDS` | ~10 | identifier_cosine에서 계속 사용 (Java family guard 포함) |
| `_is_noise_identifier()` | ~10 | identifier_cosine에서 계속 사용 |
| `_extract_identifiers()` | ~15 | identifier_cosine에서 계속 사용 |
| `identifier_cosine()` | ~25 | **유지** |

### 남는 evidence.py 구조

```python
"""Diffinite 유사도 메트릭.

두 파일의 유사도를 계산하는 함수 2개를 제공한다:
- jaccard_similarity: Winnowing 핑거프린트 기반 (Schleimer 2003)
- identifier_cosine: 식별자 빈도 벡터 코사인 유사도

이 모듈은 "얼마나 비슷한가"만 계산한다.
"어떤 유형의 복제인가"는 판단하지 않는다.
"""

# ── 식별자 필터링 (scènes à faire 제거) ──
_COMMON_KEYWORDS = frozenset({...})
_JAVA_TYPE_STOPWORDS = frozenset({...})
_JAVA_FAMILY_EXTS = frozenset({...})

def _is_noise_identifier(token, extension): ...
def _extract_identifiers(source, extension): ...

# ── 공개 API ──
def jaccard_similarity(fp_a: set[int], fp_b: set[int]) -> float: ...
def identifier_cosine(source_a, source_b, extension) -> float: ...
def compute_similarity(fp_a, fp_b, source_a, source_b, extension) -> dict: ...
```

---

## 4. 테스트 정리

| 파일 | 판정 |
|------|------|
| `test_parser.py` | 유지 (JS 템플릿 테스트 3건 포함) |
| `test_collector.py` | 유지 |
| `test_differ.py` | 유지 |
| `test_differ_extended.py` | 유지 |
| `test_fingerprint.py` | 유지 |
| `test_deep_compare.py` | 수정 — multi_channel 테스트 제거 |
| `test_evidence.py` | **대폭 수정** — 분류/AFC/IDEX 테스트 제거, jaccard+cosine만 |
| `test_cli.py` | 수정 — `--profile`, `--grid-search` 테스트 제거 |
| `test_pipeline.py` | 수정 — multi_channel 경로 제거 |
| `test_languages.py` | 유지 |
| `test_normalize.py` | 유지 |
| `test_pdf_gen.py` | 유지 |
| `test_ast_normalizer.py` | **삭제** (모듈 삭제에 따름) |
| `test_plagiarism_dataset.py` | 유지 (Winnowing 기반 → 영향 없음) |
| `test_sqlite_integration.py` | 유지 |

---

## 5. dev2에서의 최종 확인 기준

모든 수치 상수에 이 테스트를 적용:

> **"이 값의 근거를 상대방 변호사에게 한 문장으로 설명할 수 있는가?"**

| 상수 | 설명 | 판정 |
|------|------|:----:|
| `K=5` | "5개 연속 토큰을 지문 단위로. Schleimer 2003 §4.2" | ✅ |
| `W=4` | "4개 지문 중 최소값 선택. ≥8 토큰 공유 보장" | ✅ |
| `HASH_BASE=257` | "Rabin hash 표준 밑수" | ✅ |
| `HASH_MOD=2⁶¹−1` | "Mersenne 소수, 해시 충돌 최소화" | ✅ |
| `min_jaccard=0.05` | "5% 미만 유사도는 노이즈로 간주하여 보고 제외" | ✅ |
| `max_entries=10M` | "메모리 안전장치. 10M항목 ≈ 800MB" | ✅ |
| `_COMMON_KEYWORDS` | "프로그래밍 언어 예약어. 모든 코드에 존재하므로 유사도 부풀림 방지" | ✅ |
| `_JAVA_TYPE_STOPWORDS` | "Java 표준 타입명. scènes à faire (필수적 표현) 원칙에 따라 제외" | ✅ |

---

## 6. AI Agent용 프롬프트

아래 프롬프트를 새 대화에서 사용한다.

```
너는 신중하고 숙련된 10년차 포렌직 엔지니어야.

# 배경
Diffinite 프로젝트의 dev 브랜치에서 기능 구현 실험이 완료되었다.
지금부터 dev에서 `dev2` 브랜치를 분기하고,
"저작권 변호사의 쓸만한 도구" 수준으로 코드를 정리한다.

# 설계 원칙
- "works like a toaster" — 단순하고 신뢰할 수 있게
- 도구는 "얼마나, 어디가 비슷한지"만 보고한다
- "어떤 유형의 복제인지"는 판단하지 않는다 (감정인의 몫)
- 모든 수치 상수는 한 문장으로 근거를 설명할 수 있어야 한다
- 설명 불가능한 매직넘버, ad-hoc 가중치, hand-tuned 임계값은 전부 제거한다

# 참조 문서
- `report/cherrypick.md` — 파일별 유지/수정/삭제 판정 (이 문서를 반드시 먼저 읽을 것)
- `report/lessons_learned.md` — 시행착오 교훈
- `report/lessons_learned_user.md` — 의사결정 복기

# 작업 순서
1. `report/cherrypick.md`를 읽고 전체 계획 파악
2. `git checkout dev && git checkout -b dev2` 실행
3. `ast_normalizer.py` 삭제 + 관련 import 제거
4. `evidence.py`를 §3 "남는 evidence.py 구조"로 재작성 (~150줄)
   - jaccard_similarity() + identifier_cosine() + compute_similarity()만 남김
   - 분류기/AFC/IDEX/TF-IDF/프로파일 전부 삭제
5. `models.py`에서 ClassificationThresholds, IDEXThresholds 삭제
6. `deep_compare.py`에서 _run_multi_channel() 제거, DeepMatchResult 단순화
7. `cli.py`에서 --profile, --grid-search, --multi-channel, --tokenizer 제거
8. `pipeline.py`에서 grid_search, multi_channel 코드 제거, 보고서 단순화
9. 테스트 파일 정리 (cherrypick.md §4 참조)
10. `pyproject.toml`에서 tree-sitter optional dep 제거
11. `pytest tests/ -x -q` 전체 통과 확인
12. doc/, CHANGELOG.md, README.md를 "toaster" 기능에 맞게 단순화
13. 커밋

# 금지 사항
- "다음 단계로 X를 추가하면 좋겠습니다" 류의 기능 제안 금지
- 새로운 분석 채널이나 분류 기능 추가 금지
- 검증되지 않은 파라미터 도입 금지
- 사용자가 명시적으로 요청하지 않은 기능 추가 금지

# 완료 기준
- evidence.py ≤ 200줄
- 모든 수치 상수에 근거 주석 1줄
- ast_normalizer.py 삭제됨
- ClassificationThresholds, IDEXThresholds 삭제됨
- 분류기(7-class), AFC, IDEX 코드 없음
- 테스트 전체 통과
- diffinite dir_a dir_b -o report.pdf 가 작동
```
