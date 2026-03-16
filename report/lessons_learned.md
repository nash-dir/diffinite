# Diffinite Lessons Learned — Paper-Grade Clean Rebuild 가이드

> **작성일**: 2026-03-16  
> **목적**: dev 브랜치 시행착오에서 도출한 교훈을 정리하고, 논문 수준의 논증이 가능한 `paper` 브랜치 재설계를 위한 단일 참조 문서.  
> **원칙**: 최종 코드에는 **학술 논문에서 엄밀한 논증이 가능한 로직만** 남긴다. 설명 불가능한 매직넘버, hand-tuned 파라미터, ad-hoc 가중치는 허용하지 않는다.

---

## 1. 모듈별 판정: 유지 / 수정 / 재설계

### 1.1 그대로 유지 (엔지니어링 — 논증 불필요)

이 모듈들은 **표준 알고리즘의 구현**이거나 **presentation 계층**이다. 학술적 주장을 포함하지 않으므로 그대로 가져간다.

| 모듈 | 근거 |
|------|------|
| `fingerprint.py` | Winnowing (Schleimer et al., 2003) 표준 구현. K/W는 외부 주입 파라미터로 분리되어 있음. `TOKEN_RE`는 아래 "수정" 항목에서 검토. |
| `parser.py` | 주석 제거 전처리. 5-state FSM은 표준 파서 설계. 점수 산출과 무관. |
| `differ.py` | `difflib.SequenceMatcher` 래퍼. `autojunk` 옵션은 Python 표준 라이브러리 파라미터 노출. |
| `collector.py` | 파일 매칭 유틸리티. `rapidfuzz` 기반 greedy matching. |
| `pipeline.py` | 오케스트레이션 계층. 로직 없음. |
| `pdf_gen.py` | HTML/PDF 보고서 렌더링. |
| `languages/` | 언어별 사양 레지스트리. 데이터 정의만 포함. |
| `models.py` | 데이터 구조 (dataclass 프레임). 임계값 dataclass의 **기본값**만 재설계 대상. |
| `cli.py` | argparse 구조. |
| `ast_normalizer.py` | tree-sitter 래퍼. AST/PDG 토큰화 자체는 표준. |

### 1.2 소규모 수정 (근거 보강 필요)

| 영역 | 현재 문제 | 논문 수준 조치 |
|------|----------|---------------|
| `TOKEN_RE` 범용 토크나이저 | 단일 정규식으로 모든 언어 처리. 논문 심사자가 "언어별 토크나이저와 비교했는가?" 물을 것 | **실험 1**: 범용 vs. 언어별 토크나이저 AUC 비교 → 유의차 없으면 "simplicity principle"로 정당화 가능. 유의차 있으면 언어별 토크나이저로 교체. |
| `_is_noise_identifier()` Java stopwords | 20개 hand-crafted. "왜 이 20개인가?" | **실험 2**: corpus에서 TF-IDF 상위 N개 공통 식별자를 자동 추출 → hand-crafted 대비 성능 비교. 자동 추출이 동등하면 교체. |
| `_JAVA_FAMILY_EXTS` 가드 | `.java`, `.kt`, `.scala`, `.groovy` 4개 — 합리적이지만 검증 없음 | 언어별 실험으로 자연 도출되면 유지. |

### 1.3 근본 재설계 (ad-hoc → 실증 도출)

> ⚠️ 이 영역이 논문의 **핵심 기여(contribution)**이자 **가장 큰 약점**이다.

#### A. 채널 선택 및 가중치

**현재**: 6채널, ROC AUC 비례 가중치 (ad-hoc).

**문제**:
- 채널 선택 근거 없음 (왜 6개인가? 5개나 7개는?)
- `raw_winnowing` ↔ `normalized_winnowing` 상관 > 0.9 → 이중 계산
- 가중치 = 개별 AUC는 이론적 근거 없음 (채널 상관 무시)

**재설계**:
```
1. 전체 후보 채널을 열거 (현재 6 + 추가 후보)
2. 채널 간 상관행렬(Pearson/Spearman) 보고
3. Ablation study: LOO-channel (각 채널 제거 시 AUC 변화)
4. 최종 채널 세트: ablation에서 유의한 기여를 한 채널만 유지
5. 가중치: Logistic Regression 계수 (5-fold CV)
   → coefficient sign/magnitude가 각 채널의 기여를 "설명"
   → 해석: "raw_winnowing 1 std 증가 → log-odds 2.3 증가"
```

**논문 문장 예시**: "We selected K channels via leave-one-out ablation, retaining only those whose removal resulted in a statistically significant AUC decrease (paired DeLong test, p < 0.05)."

---

#### B. 분류 임계값 도출

**현재**: `ClassificationThresholds` 18필드, 646쌍 grid search, train=test.

**문제**:
- **Data leakage**: 도출(train)과 평가(test)가 동일 데이터
- 18 파라미터 / 646 데이터 = 과소결정
- "zero-FP" 목표는 비현실적이고 보고할 수 없음
- Confidence interval 없음

**재설계**:
```
1. 코퍼스를 최소 5-fold로 분할
2. 각 fold에서:
   a. Train set으로 임계값 최적화 (grid search)
   b. Test set으로 평가 → per-fold metrics 기록
3. 5개 fold의 평균 ± std 보고
4. Bootstrap (B=1000)으로 95% CI 산출
5. 최종 임계값 = 5-fold 평균값 (또는 전체 데이터 re-fit 후 CI만 CV에서 가져옴)
```

**파라미터 수 축소 검토**: 18필드가 모두 필요한가?
- `susp_*` 5개 필드는 Stage 2용 → 하나의 ratio로 축소 가능 (e.g., `relaxation_factor = 0.8`)
- `conv_*` 3개 필드 → 단일 임계값으로 통합 가능
- **목표**: 18 → 8~10개로 축소하여 코퍼스 크기 대비 자유도 개선

**논문 지표**: "Precision 95.5%"가 아니라 → **FPR@95%TPR**, **AUC**, **F1**, 각각 ± 95% CI.

---

#### C. IDEX 법리 분석 임계값

**현재**: `IDEXThresholds` 8필드, "직관적 추정".

**문제**: 8개 임계값 전부 근거 없음. 논문에서 사용 불가.

**재설계**:
```
1. IDEX 패턴별로 labeled data 필요:
   - CLEAN_ROOM: 공개 클린룸 사례 (Android/Oracle, Compaq BIOS)
   - LITERAL_COPYING: IR-Plag L1 (직접 복사)
   - INDEPENDENT_CREATION: 동일 과제 독립 제출
2. 각 패턴에 대해 ROC curve 그리기
3. Youden's J statistic으로 최적 operating point 도출
4. 임계값 = operating point ± CI
```

**대안 (데이터 부족 시)**: IDEX 패턴 분류를 **rule-based에서 ML-based로 전환** — 같은 Logistic Regression으로 패턴 확률 출력. 이 경우 IDEXThresholds dataclass 자체가 불필요해진다.

**핵심 판단**: labeled IDEX 데이터를 확보할 수 없다면, 이 기능 자체를 "exploratory analysis"로 격하하고 논문 본문에서 빼야 한다. **근거 없는 분류기를 논문에 포함하는 것이 가장 위험하다.**

---

#### D. AFC 인플레이션 보정

**현재**: `_AFC_SSO_DECL_MIN = 0.75`, `_AFC_SSO_GAP_MIN = 0.35` (hand-tuned).

**문제**: "인플레이션 1.3-1.7×"라고 했지만, 이 범위의 출처와 0.75의 도출 근거가 없다.

**재설계**:
```
1. 코퍼스 전체에 대해 AFC 전/후 점수를 쌍으로 수집
2. inflation_ratio = filtered_score / raw_score 의 분포 보고
3. Paired t-test 또는 Wilcoxon signed-rank로 유의성 검증
4. AFC 전용 임계값 = base_threshold × median(inflation_ratio)
   → 이렇게 하면 "0.75"가 아니라 "0.60 × 1.24 (median inflation, 95% CI [1.18, 1.31])"로 보고 가능
```

---

#### E. 2단계 분류 아키텍처

**현재**: Strict (zero-FP) → Relaxed (recall 보완) 고정 파이프라인.

**핵심 질문**: 이 2단계가 단일 분류기보다 나은가?

**재설계**:
```
1. 단일 Logistic Regression (all channels → binary label) vs. 2-stage 비교
2. McNemar test로 유의차 검증
3. 유의차 있으면 유지 + "cascade classifier" 프레임워크로 설명
4. 유의차 없으면 단일 분류기로 단순화
```

---

## 2. 실험 프로토콜 체크리스트

논문 게재를 위해 **반드시** 수행해야 하는 실험:

| # | 실험 | 보고 대상 | 섹션 |
|:-:|------|----------|------|
| E1 | 채널 간 상관행렬 | Pearson r, VIF | Method |
| E2 | LOO-channel ablation | ΔAUC ± CI, DeLong p-value | Method |
| E3 | 임계값 5-fold CV | Per-fold metrics ± std | Evaluation |
| E4 | Bootstrap 95% CI | AUC, F1, FPR@95%TPR | Evaluation |
| E5 | 범용 vs. 언어별 토크나이저 | AUC 비교 | Method |
| E6 | noise identifier: hand-crafted vs. corpus-driven | AUC 비교 | Method |
| E7 | AFC inflation 분포 | 중앙값, IQR, paired test | Results |
| E8 | 2-stage vs. 단일 분류기 | McNemar p-value | Evaluation |
| E9 | 파라미터 수 축소 (18→N) | AUC 비교 + 자유도 분석 | Method |

---

## 3. 코퍼스 요구사항

| 요구 | 현재 | 논문 수준 |
|------|------|----------|
| 총 쌍 수 | 646 | ≥ 2,000 (파라미터 × 100 rule of thumb) |
| 언어 다양성 | Java 중심 | Java + C + Python + JS (최소 4) |
| 라벨 품질 | IR-Plag 기반 | 2인 독립 라벨링 + Cohen's κ ≥ 0.80 |
| Train/Test | 없음 | 5-fold CV 또는 80/20 held-out |
| 공개 재현성 | 비공개 | 코퍼스 + 스크립트 공개 (또는 공개 데이터셋만 사용) |

---

## 4. `paper` 브랜치에서 제거해야 할 레거시 목록

아래 항목들이 최종 코드에 남아 있으면 **"설명 불가능한 레거시"**가 된다:

| 위치 | 대상 | 이유 | 대체 |
|------|------|------|------|
| `evidence.py` | `INDUSTRIAL_THRESHOLDS` 기본값 | grid search overfit | CV 도출값 |
| `evidence.py` | `ACADEMIC_THRESHOLDS` 전체 | "neg_max 분석 기반 상향" — 비형식적 | 도메인 적응 실험으로 재도출 |
| `evidence.py` | `_RELAXED_SSO_GAP_MIN = 0.25` | 근거 없음 | CV 또는 ratio-based |
| `evidence.py` | `_AFC_SSO_DECL_MIN = 0.75` | hand-tuned | inflation 실측 기반 |
| `evidence.py` | `_AFC_SSO_GAP_MIN = 0.35` | hand-tuned | inflation 실측 기반 |
| `evidence.py` | composite 가중치 (AUC 비례) | ad-hoc | LR 계수 |
| `evidence.py` | `_SSO_NORM_RAW_RATIO` | 출처 불명 | 코퍼스 기반 도출 또는 제거 |
| `models.py` | `IDEXThresholds` 기본값 | "직관적 추정" | ROC 최적점 또는 기능 제거 |
| `evidence.py` | `_extract_identifiers` Java stopwords | hand-crafted 20개 | corpus-driven 또는 비교 실험 |

---

## 5. 다음 대화를 위한 프롬프트

아래 프롬프트를 **새 대화**에서 사용한다.

```
너는 신중하고 숙련된 10년차 포렌직 엔지니어이자 학술 논문 심사 경험이 있는 연구자야.

# 배경
Diffinite(소스코드 유사도 포렌식 도구)의 dev 브랜치에서 기능 구현은 완료되었으나,
파라미터 도출 과정의 학술적 엄밀성이 부족하다는 진단을 받았다.
상세 내용은 `report/lessons_learned.md`에 기술되어 있다.

# 목표
dev 브랜치에서 `paper` 브랜치를 분기하고,
evidence.py의 "주장(claims) 계층"을 학술 논문에서 엄밀한 논증이 가능한 수준으로 재설계한다.
최종 코드에는 설명 불가능한 매직넘버, hand-tuned 파라미터, ad-hoc 가중치가 없어야 한다.

# 작업 순서
1. `report/lessons_learned.md` 전체를 읽고 현재 상태를 파악
2. `paper` 브랜치 생성 (dev에서 분기)
3. 아래 실험 프로토콜을 순서대로 수행:
   - E1: 채널 간 상관행렬 분석
   - E2: LOO-channel ablation study
   - E9: 파라미터 수 축소 검토
   - E3: 분류 임계값 5-fold CV 재도출
   - E4: Bootstrap 95% CI 산출
   - E7: AFC inflation 분포 실측
   - E8: 2-stage vs. 단일 분류기 비교
4. 실험 결과에 따라 evidence.py 리팩토링
5. §4의 "제거해야 할 레거시 목록" 항목들이 모두 대체되었는지 검증
6. 테스트 전체 통과 확인 후 커밋

# 원칙
- 모든 파라미터는 코드 내 주석에 "도출 근거" 한 줄 명시 (예: "5-fold CV mean, see E3")
- 실험 결과는 `report/experiments/` 디렉토리에 기록
- 각 실험 전에 가설(H0, H1)을 명시하고, 결과에 p-value 또는 CI 포함
```

---

## 6. 기대 결과물

`paper` 브랜치 완성 시:

```
evidence.py 내 모든 수치 상수 옆에:
# 5-fold CV mean=0.63, std=0.04, see report/experiments/E3_threshold_cv.md

모든 채널 선택 결정에:
# ablation ΔAUC=−0.034 (p=0.012), see report/experiments/E2_ablation.md

IDEX 임계값:
# Youden's J optimal point, AUC=0.89, see report/experiments/idex_roc.md
# 또는: 기능 제거됨 (labeled data 부족으로 논증 불가)
```
