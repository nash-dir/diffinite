# 알고리즘 & 이론적 배경

## 1. Winnowing 핑거프린팅

### 참조
- Schleimer, Wilkerson, Aiken. *"Winnowing: Local Algorithms for Document Fingerprinting"*. SIGMOD 2003.

### 파이프라인
```
Source → Tokenize → K-gram → Rolling Hash → Winnow → Fingerprint Set
```

### 밀도 보장 (Density Guarantee)
**공유 부분 문자열의 길이가 ≥ (W + K − 1) 토큰이면, 반드시 최소 1개의 공통 핑거프린트가 생성된다.**

현재 설정 (K=5, W=4): ≥ 8토큰 공유 시 탐지 보장.

### 롤링 해시
Rabin-style 다항식 해시:
```
h = Σ(token_hash[i] × BASE^(k-1-i)) mod MOD
```
- `BASE = 257`
- `MOD = 2⁶¹ − 1` (Mersenne 소수 → 저충돌)

### 유사도 메트릭
```
Jaccard(A, B) = |fp(A) ∩ fp(B)| / |fp(A) ∪ fp(B)|
```

---

## 2. AST 정규화 (Phase 2)

### 선형화 규칙
| 노드 유형 | 처리 |
|----------|------|
| 구조 노드(`for_statement` 등) | `<for_statement> … </for_statement>` 태깅 |
| 식별자 | `"ID"` |
| 숫자 리터럴 | `"LIT"` |
| 문자열 리터럴 | `"STR"` |
| 키워드/연산자 | 원문 보존 |

### 탐지 능력
- **Type-2 클론**: 변수명 변경 → ID 정규화로 무력화
- **Type-3 클론**: 구조 태그로 레이아웃 차이 흡수

---

## 3. PDG 정규화 (Phase 4)

### Use-Def 분석
```
문(Statement)별로:
  - defined: 좌변(LHS) 식별자 수집
  - used: 우변(RHS) 식별자 수집
```

### 3단계 처리
1. **Use-Def 추출**: 각 문의 정의/사용 변수 분석
2. **Independent 문 제거**: 다른 문과 의존 관계 없는 문 제거 (dead code)
3. **의존성 재정렬**: 위상 정렬 → 정준(canonical) 순서

### 공격 저항력
| 공격 | 방어 |
|------|------|
| Dead code 삽입 | Independent 문 필터링 |
| 문 순서 섞기 | 위상 정렬로 정준화 |

---

## 4. TF-IDF Cosine 유사도

### IDF (Inverse Document Frequency)
```python
idf(t) = log((N + 1) / (df(t) + 1)) + 1  # scikit-learn smooth IDF
```

### TF-IDF 벡터
```python
tfidf(t, d) = tf(t, d) × idf(t)
```

### Cosine 유사도
```python
cos(A, B) = (A · B) / (|A| × |B|)
```

### 효과
- `size`, `get`, `set` 등 범용 식별자 → IDF 낮음 → 유사도 기여 ↓
- `computeBloomFilter`, `mergeIntervals` 등 고유 API → IDF 높음 → 유사도 기여 ↑

---

## 5. AFC (Abstraction-Filtration-Comparison) 테스트

### 법적 근거
- *Computer Associates v. Altai* (2d Cir. 1992)

### 3단계

| 단계 | 목적 | 구현 |
|------|------|------|
| **Abstraction** | 계층 분해 | file → class → method → statement |
| **Filtration** | 비보호 요소 제거 | boilerplate + import + TF-IDF 하향 |
| **Comparison** | 보호 표현만 비교 | filtered 코드 재점수화 |

### 위양성 방지
Filtration은 유사도를 부풀리므로 (`filtration inflation`), AFC 전용 임계값은 1.3–1.7× 상향 보정.

---

## 6. 2단계 분류 체계

### 설계 근거
단일 임계값 → 정밀도(Precision) vs 재현율(Recall) 트레이드오프 발생. 2단계로 분리:

| Stage | 목적 | 출력 | 정밀도 역할 |
|:-----:|------|------|:-----------:|
| **Strict** | Zero-FP 분류 | DIRECT_COPY, SSO_COPYING 등 | 정밀도 계산 포함 |
| **Relaxed** | 재현율 보완 | SUSPICIOUS_COPY, SUSPICIOUS_SSO | 참고용 (제외) |

### 프로파일 분리
- **Industrial** (K=5, W=4): 실무 코드 — 넓은 유사도 범위 탐색
- **Academic** (K=2, W=3): 학술 코드 — 짧은 코드 기본 유사도 반영하여 임계값 상향

---

## 7. 아이디어-표현 이분법 (IDEX)

### 이론
- *Baker v. Selden* (1879): 아이디어는 보호받지 못하고 표현만 보호
- *Lotus v. Borland* (1st Cir. 1995): 메뉴 구조 = 조작 방법 ≠ 보호 표현

### 정량화 전략
| 프로파일 | 감지 | 해석 |
|----------|------|------|
| Industrial (K=5 W=4) | 문자적 복제 | **표현(Expression)** 수준 |
| Academic (K=2 W=3 + AST) | 구조적 유사성 | **아이디어(Idea)** 수준 |

```
delta = academic_composite - industrial_composite
```

- `delta > 0.40`: 아이디어는 유사하나 표현은 독립 → **Clean Room 가능**
- `delta ≈ 0`: 아이디어와 표현 모두 유사 → **Literal Copying 가능**
