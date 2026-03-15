# Diffinite 일반화 가능성 점검 보고서

> **작성일**: 2026-03-15  
> **검토 대상**: `evidence.py` (1147 lines), `deep_compare.py` (466 lines), `cli.py` (335 lines)  
> **검토 관점**: 과적합(Overfitting), 일반화 불가능한 분기처리, 코드 위생(Code Hygiene)

---

## 요약

전체적으로 아키텍처는 건전하며, 법리 기반의 다중 채널 분석 + 2단계 분류 체계는 학술적으로도 타당한 설계이다.
다만 **3건의 버그**와 **3건의 일반화 위험**이 발견되었다.

| 구분 | 등급 | 건수 |
|:----:|:----:|:----:|
| 🔴 **버그** (런타임 에러) | Critical | 1 |
| 🟡 **코드 위생** (중복/불일치) | Medium | 2 |
| 🟠 **일반화 위험** (과적합/Java편향) | Warning | 3 |

---

## 🔴 Critical: `_IDENT_RE` NameError

### 위치
[evidence.py L470](file:///c:/projects/diffinite/src/diffinite/evidence.py#L470)

### 문제
`comment_string_overlap_tfidf()` 함수에서 `_IDENT_RE.findall()`을 호출하지만, `_IDENT_RE`는 evidence.py에 **정의되어 있지 않다**. `idf` 인자가 전달되면 즉시 `NameError`가 발생한다.

```python
# L470 — evidence.py
tokens_a.extend(_IDENT_RE.findall(frag.lower()))  # ← _IDENT_RE 미정의!
```

### 원인
`_TOKEN_RE` (L36)를 사용해야 하는데 잘못된 이름으로 참조. 테스트에서 `idf=None`으로만 호출했기 때문에 Jaccard 폴백만 실행되어 발견되지 않았다.

### 조치
`_IDENT_RE` → `_TOKEN_RE`로 변경 (2곳: L470, L472)

---

## 🟡 Medium: 중복 함수 `_jaccard_from_sets`

### 위치
- [evidence.py L259-266](file:///c:/projects/diffinite/src/diffinite/evidence.py#L259-266) — `_jaccard_from_sets(set, set)`
- [evidence.py L533-539](file:///c:/projects/diffinite/src/diffinite/evidence.py#L533-539) — `_jaccard_from_sets(set[int], set[int])`

### 문제
**완전히 동일한 로직**이 2번 정의되어 있다. L533 버전만 사용되면 L259 버전은 dead code이다. 반대로 양쪽 모두 호출된다면 Python은 마지막 정의(L533)만 사용하므로, L259 정의는 사실상 무효하다.

### 조치
L259-266의 첫 번째 정의를 삭제하고, L533의 정의만 유지한다.

---

## 🟡 Medium: `_DEFAULT_WEIGHTS` 내 `comment_string_overlap` AUC 값 미갱신

### 위치
[evidence.py L496](file:///c:/projects/diffinite/src/diffinite/evidence.py#L496)

### 문제
```python
"comment_string_overlap": 0.528,  # ROC AUC = 0.528 (lowest)
```
실제 측정된 AUC는 **0.8469**이다. 이 가중치가 composite 점수에 직접 영향을 미치므로, comment 채널이 과소 반영되고 있다.

### 조치
실측 AUC 값 0.847로 업데이트한다.

---

## 🟠 Warning: `_classify_relaxed()` 프로파일 미적용

### 위치
[evidence.py L735-767](file:///c:/projects/diffinite/src/diffinite/evidence.py#L735-L767)

### 문제
`_classify_strict()`는 `profile` 파라미터를 받아 `_CLASSIFICATION_PROFILES[profile]`에서 임계값을 동적으로 가져오지만, `_classify_relaxed()`는 **모듈 레벨** 상수(`_DC_IDENT_MIN`, `_SSO_RAW_MAX` 등)를 하드코딩으로 참조한다.

```python
# L750 — _classify_relaxed
if raw > _RELAXED_DC_RAW_MIN and ident > _DC_IDENT_MIN:  # ← 항상 industrial
```

따라서 `--profile academic`으로 실행해도 relaxed 분류는 항상 industrial 임계값을 사용한다. 현재는 relaxed가 SUSPICIOUS (참고용) 등급이므로 critical은 아니나, 프로파일 전환 시 일관성이 깨진다.

### 조치
`_classify_relaxed()`에도 `profile` kwarg을 추가하고 프로파일 기반 임계값을 사용하도록 통일한다.

---

## 🟠 Warning: Java 편향적 Stopword / Javadoc 필터

### 위치
- [evidence.py L42-48](file:///c:/projects/diffinite/src/diffinite/evidence.py#L42-L48) — `_JAVA_TYPE_STOPWORDS`
- [evidence.py L327-331](file:///c:/projects/diffinite/src/diffinite/evidence.py#L327-L331) — `_JAVADOC_TAGS`

### 문제
`_JAVA_TYPE_STOPWORDS`는 Java 전용 타입명(`String`, `Override`, `Serializable`)이며, Python/C++/Go 등의 코드를 분석할 때는 오히려 의미 있는 식별자를 잘못 제거할 수 있다.

마찬가지로 `_JAVADOC_TAGS`는 Java/Kotlin 전용이며, Python의 `docstring`이나 C++의 `Doxygen` (`/// @brief` 등)에는 적용되지 않는다.

### 과적합 등급: **낮음 (Low)**
현재 코퍼스가 Java 중심이라 실질 위험은 낮지만, 다국어 지원 시 반드시 `languages/` 패키지의 `LangSpec`에 stopword 목록을 이관해야 한다.

### 조치
즉시 수정보다는, `_is_noise_identifier()`와 `_strip_javadoc_tags()`에 `extension` 파라미터를 추가하여 `.java` 확장자일 때만 Java-specific 필터를 적용하도록 가드를 추가한다. 장기적으로는 `LangSpec`으로 이관.

---

## 🟠 Warning: 법리 분석 임계값의 데이터 근거 부재

### 위치
[evidence.py L1118-1123](file:///c:/projects/diffinite/src/diffinite/evidence.py#L1118-L1123)

### 문제
```python
if raw_w < 0.20 and acad_ast > 0.70 and delta > 0.40:
    pattern = "CLEAN_ROOM_PROBABLE"
elif raw_w > 0.60 and acad_c > 0.70 and abs(delta) < 0.15:
    pattern = "LITERAL_COPYING"
elif ind_c < 0.20 and acad_c < 0.30:
    pattern = "INDEPENDENT_CREATION"
```

이 임계값들은 **직관적 추정**이며, 실제 클린룸 사례(Phoenix BIOS, Wine Project) 데이터로 검증된 적이 없다. 전형적인 '골방 사상가의 독창적 분기처리' 위험이 있다.

### 과적합 등급: **중간 (Medium)**
단, TODO §9에 이미 "교정 전까지 참고 정보로만 사용" 경고가 명시되어 있고, 테스트도 보수적인 어설션만 사용하므로 현재로서는 통제된 상태이다.

### 조치
향후 코퍼스 확장(§7) 시 실제 클린룸 코드 쌍으로 임계값을 데이터 기반 교정해야 한다. 현재 코드에서는 이 패턴들을 보고서에 "참고 정보 (Reference Only)" 뱃지와 함께 표기하는 것을 권장한다.

---

## 정상 판정: 과적합 위험 없음

다음 항목들은 검토 결과 **일반화에 문제 없음**으로 판정되었다:

| 항목 | 판정 근거 |
|------|----------|
| 2단계 분류 체계 (`strict` + `relaxed`) | SUSPICIOUS는 참고용이며, precision 계산에서 제외됨. 논리적으로 타당 |
| `_CLASSIFICATION_PROFILES` | industrial/academic 분리는 도메인 분석 데이터에 근거하며, 프로파일 추가 구조가 확장 가능 |
| AFC 파이프라인 (`afc_analysis`) | Altai(1992) 3단계를 충실히 구현. filtration inflation을 별도 임계값으로 흡수하는 전략은 투명하고 법정 소명에 유리 |
| `_SSO_NORM_RAW_RATIO = 1.2` | 양성 median=1.44에서 충분한 margin. 현행 FP/FN 변화 0으로 검증됨 |
| Composite 가중치 방식 | ROC AUC 비례 가중치는 표준적인 앙상블 결합 전략. 과적합 위험 낮음 |
| Deep Compare inverted index | 아키텍처적으로 건전. O(|fp_A|) 탐색은 표준적인 information retrieval 기법 |
| CLI 3-tier 파라미터 체계 | profile → manual override → grid search 순서는 합리적이며, 사용자 친화적 |

---

## 즉시 수정 항목 요약

| # | 파일 | 수정 | 위험도 |
|:-:|------|------|:------:|
| 1 | `evidence.py` L470, L472 | `_IDENT_RE` → `_TOKEN_RE` | 🔴 Critical |
| 2 | `evidence.py` L259-266 | 중복 `_jaccard_from_sets` 삭제 | 🟡 Medium |
| 3 | `evidence.py` L496 | `comment_string_overlap` 가중치 0.528 → 0.847 | 🟡 Medium |
| 4 | `evidence.py` L735-767 | `_classify_relaxed()`에 `profile` kwarg 전파 | 🟠 Warning |
| 5 | `evidence.py` L42-48, L327-331 | Java-specific 필터에 extension 가드 추가 | 🟠 Warning |
