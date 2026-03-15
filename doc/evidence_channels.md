# 증거 채널 & 분류 시스템

> `evidence.py` (1147 lines) — Diffinite의 핵심 분석 엔진

---

## 6개 증거 채널

| # | 채널명 | 메트릭 | 탐지 대상 | ROC AUC |
|:-:|--------|--------|----------|:-------:|
| 1 | `raw_winnowing` | Jaccard | 원문 토큰 시퀀스 유사도 | 0.836 |
| 2 | `normalized_winnowing` | Jaccard | 식별자/리터럴 정규화 유사도 | 0.818 |
| 3 | `ast_winnowing` | Jaccard | 구조적 패턴 유사도 | 0.813 |
| 4 | `identifier_cosine` | Cosine | 식별자 빈도 벡터 유사도 | 0.741 |
| 5 | `declaration_cosine` | Cosine | API 표면(선언부) 유사도 | 0.550 |
| 6 | `comment_string_overlap` | Jaccard/TF-IDF | 주석/문자열 보존 여부 | 0.847 |

### Composite 점수
```python
composite = Σ(score_i × weight_i) / Σ(weight_i)
```
가중치는 ROC AUC에 비례 (앙상블 결합). 프로파일별 가중치 사전 지원.

---

## TF-IDF 시스템

### IDF 구축
```python
idf[token] = log((N + 1) / (df + 1)) + 1   # smoothed
```
- `N`: 전체 문서 수
- `df`: 해당 토큰을 포함한 문서 수
- 공통 식별자 (`size`, `get`, `set`) 가중치 ↓, 고유 API명 (`compareTo`) 가중치 ↑

### TF-IDF 적용 함수
| 함수 | 채널 |
|------|------|
| `identifier_cosine_tfidf()` | identifier_cosine |
| `declaration_cosine_tfidf()` | declaration_cosine |
| `comment_string_overlap_tfidf()` | comment_string_overlap |

---

## 2단계 분류 체계

### Stage 1 — Strict (고확신)

Grid search 최적화 임계값 사용 (646쌍, zero-FP 목표).

| 분류 | raw | ident | decl | ast | 해석 |
|------|:---:|:-----:|:----:|:---:|------|
| `DIRECT_COPY` | HIGH | HIGH | — | — | 문자적 복사 |
| `SSO_COPYING` | LOW | HIGH | HIGH | MED+ | API 구조 복제 |
| `OBFUSCATED_CLONE` | LOW | LOW | — | HIGH | 난독화 클론 |
| `DOMAIN_CONVERGENCE` | LOW | any | LOW | LOW | 도메인 수렴 (FP) |

### Stage 2 — Relaxed (중확신)

Strict에서 `INCONCLUSIVE` 시 relaxed 임계값으로 재시도.

| 분류 | 조건 | 용도 |
|------|------|------|
| `SUSPICIOUS_COPY` | raw 0.40–0.65+, ident/comment 높음 | 수동 검토 권고 |
| `SUSPICIOUS_SSO` | raw LOW, decl/ident MED | 수동 검토 권고 |

> SUSPICIOUS 등급은 **참고용**이며 정밀도 계산에 포함하지 않는다.

### 도메인 프로파일

```python
_CLASSIFICATION_PROFILES = {
    "industrial": { ... },  # 실무 코드
    "academic":   { ... },  # 학술 코드 (더 엄격한 임계값)
}
```
- Academic 프로파일은 짧은 코드의 높은 기본 유사도를 반영하여 임계값 상향
- `_classify_relaxed()`도 `profile` kwarg으로 프로파일-aware

---

## AFC 파이프라인 (Altai 3단계)

`afc_analysis()` — Computer Associates v. Altai (1992) 판례 기반.

```
Step 1: Abstraction    — 계층 분해 (file → class → method → statement)
Step 2: Filtration     — 비보호 요소 제거 (boilerplate, scènes à faire, import)
Step 3: Comparison     — 보호 가능 표현만 재점수화
```

### 필터링 대상
- **Boilerplate**: `equals`, `hashCode`, `toString`, getter/setter
- **Import 문**: `import/package` 선언 제거
- **TF-IDF**: 코퍼스 빈출 식별자 가중치 하향

### AFC-specific 임계값
- `_AFC_SSO_DECL_MIN = 0.75` (인플레이션 1.3–1.7× 보정)
- `_AFC_SSO_GAP_MIN = 0.35`

---

## 법리 델타 분석기

`analyze_legal_defense_pattern()` — 아이디어-표현 이분법 정량화.

### 이중 프로파일 분석
| 프로파일 | K | W | AST 정규화 | 감지 대상 |
|----------|:-:|:-:|:----------:|----------|
| Industrial | 5 | 4 | ❌ | 표현(Expression) 복제 |
| Academic | 2 | 3 | ✅ | 아이디어(Idea) 유사도 |

### 5가지 법리 분류

| 패턴 | 조건 | 법적 해석 |
|------|------|----------|
| `CLEAN_ROOM_PROBABLE` | raw<0.20, acad_ast>0.70, delta>0.40 | 클린룸 설계 |
| `LITERAL_COPYING` | raw>0.60, acad>0.70, delta<0.15 | 표현 복제 |
| `INDEPENDENT_CREATION` | ind<0.20, acad<0.30 | 독립 작성 |
| `MERGER_FILTERED` | AFC 후 composite >20% 하락 | 합체(Merger) 원칙 |
| `INCONCLUSIVE` | 기타 | 수동 검토 필요 |

> ⚠️ 법리 분석 임계값은 직관적 추정이며, 실제 클린룸 사례 데이터로 교정 필요.  
> 모든 출력에 법적 면책 조항이 포함된다.

---

## 주석/문자열 채널 강화

### 필터링
- **라이선스 헤더**: `_LICENSE_KEYWORDS` 13개 키워드 매칭 → 제거
- **Javadoc 태그**: `_JAVADOC_TAGS` 18개 태그 → Java-family 확장자에서만 적용
- **Java Family Guard**: `_JAVA_FAMILY_EXTS = {".java", ".kt", ".scala", ".groovy"}`

### TF-IDF 코사인
`comment_string_overlap_tfidf()`: `_TOKEN_RE` 토크나이저 + `_tfidf_vector()` + `_cosine_from_counters()` 패턴 사용. IDF 없으면 기존 Jaccard 폴백.
