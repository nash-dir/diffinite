# 모듈 레퍼런스

> 각 모듈의 역할, 주요 함수, 설계 의도를 정리한다.

---

## 1. `cli.py` — CLI 진입점 (335 lines)

**역할**: `argparse` 기반 CLI. `diffinite` 콘솔 커맨드의 진입점.

### 주요 구조
- **`PROFILES`**: `industrial` (K=5, W=4, T=0.10) / `academic` (K=2, W=3, T=0.40) 프리셋
- **3-Tier 파라미터**: profile → manual override → grid search
- **`AnalysisMetadata`**: 모든 보고서에 분석 설정을 기록 (재현가능성)

### 주요 함수
| 함수 | 설명 |
|------|------|
| `main(argv)` | 인자 파싱 → `run_pipeline()` 호출 |

---

## 2. `pipeline.py` — 파이프라인 오케스트레이터 (758 lines)

**역할**: Collection → Preprocessing → Diff → Deep Compare → Report 전체 흐름을 조율.

### 주요 함수
| 함수 | 설명 |
|------|------|
| `run_pipeline(...)` | 전체 파이프라인 실행 (39개 파라미터) |
| `_run_grid_search(...)` | K×W 감도 분석 (K∈[2,7], W∈[2,6]) |
| `_generate_markdown_report(...)` | Markdown 보고서 생성 |
| `_generate_html_report(...)` | 독립형 HTML 보고서 생성 |
| `_generate_pdf_report(...)` | Divide-and-conquer PDF 생성 |
| `_build_metadata_banner_md/html(...)` | 분석 설정 배너 생성 |

---

## 3. `collector.py` — 파일 수집 & 퍼지 매칭 (111 lines)

**역할**: 디렉토리 스캔 + `rapidfuzz` 기반 1:1 파일 매칭.

### 알고리즘
1. **Phase 1 (Exact)**: O(N) — 동일 상대경로 exact match
2. **Phase 2 (Fuzzy)**: O(R²) — 나머지에 대해 greedy best-match (R ≪ N)

### 주요 함수
| 함수 | 설명 |
|------|------|
| `collect_files(directory)` | 재귀 파일 수집 → 정렬된 상대경로 목록 |
| `match_files(files_a, files_b, threshold)` | (matched, unmatched_a, unmatched_b) 반환 |

---

## 4. `parser.py` — 2-Pass 주석 제거 엔진 (349 lines)

**역할**: 문자열 리터럴 내부의 주석 마커 오탐을 방지하는 정밀 주석 제거.

### 알고리즘
- **Fast-path**: 주석 마커가 없는 라인은 즉시 통과 (문자 단위 스캔 불필요)
- **Slow-path**: 4-state 상태 머신 (`CODE`, `IN_STRING`, `IN_LINE_COMMENT`, `IN_BLOCK_COMMENT`)
- **Pre-pass**: C-family의 `#if 0 … #endif` 블록 제거

### 주요 구조
- **`COMMENT_SPECS`**: `_RegistryProxy` — `languages/` 레지스트리에서 동적으로 조회
- **`strip_comments(text, extension)`**: 메인 API

---

## 5. `differ.py` — Diff 계산 & HTML 생성 (262 lines)

**역할**: `difflib` 기반 유사도 계산 + `Pygments` 구문 강조 side-by-side HTML diff.

### 주요 함수
| 함수 | 설명 |
|------|------|
| `read_file(path)` | `charset-normalizer`로 인코딩 자동 감지 |
| `compute_diff(text_a, text_b, by_word)` | `(ratio, additions, deletions)` 반환 |
| `generate_html_diff(...)` | Side-by-side HTML 테이블 (context folding 지원) |

### 설계 포인트
- `autojunk=True`: 12K-line 파일에서 **1,824× 성능 향상**, 정확도 손실 <0.03%
- `ln_col_width`: 최대 라인 번호 기반 반응형 열 너비

---

## 6. `fingerprint.py` — Winnowing 핑거프린트 (258 lines)

**역할**: Stanford MOSS 스타일 문서 핑거프린팅. Tokenize → K-gram → Rolling Hash → Winnow.

### 핵심 상수
| 상수 | 값 | 설명 |
|------|:--:|------|
| `DEFAULT_K` | 5 | K-gram 크기 (grid search 최적값) |
| `DEFAULT_W` | 4 | Winnowing 윈도우 (≥8 토큰 공유 보장) |
| `HASH_BASE` | 257 | Rabin 다항식 해시 밑 |
| `HASH_MOD` | 2⁶¹−1 | Mersenne 소수 (충돌 최소화) |

### 주요 함수
| 함수 | 설명 |
|------|------|
| `tokenize(source, normalize)` | 토크나이징 (normalize: ID/LIT/STR 치환) |
| `rolling_hash(tokens, k)` | Rabin 롤링 해시 |
| `winnow(hash_values, w)` | 윈도우 최소값 선택 → `FingerprintEntry` 목록 |
| `extract_fingerprints(...)` | 통합 파이프라인 (mode=token/ast/pdg) |

---

## 7. `deep_compare.py` — N:M 크로스매칭 엔진 (466 lines)

**역할**: 역 인덱스 기반 O(|fp_A|) 크로스매칭. 병렬 핑거프린트 추출.

### 알고리즘
1. `ProcessPoolExecutor`로 병렬 핑거프린트 추출
2. B-파일의 **역 인덱스** 구축: `hash_value → {file_ids}`
3. A-파일별 인덱스 조회 → Jaccard 유사도 계산

### 모드
| 모드 | 함수 | 출력 |
|------|------|------|
| Single-channel | `_run_single_channel()` | Jaccard만 |
| Multi-channel | `_run_multi_channel()` | 6채널 + 분류 + AFC |

---

## 8. `ast_normalizer.py` — AST/PDG 정규화 (905 lines)

**역할**: tree-sitter 기반 AST 파싱 → 정규화 토큰 시퀀스 + SSO 탐지 도구.

### 핵심 기능

| 함수 | Phase | 설명 |
|------|:-----:|------|
| `ast_tokenize()` | Phase 2 | AST DFS → 구조 태그 + ID/LIT/STR 정규화 |
| `pdg_tokenize()` | Phase 4 | Use-def 분석 → dead code 제거 → 의존성 재정렬 |
| `extract_declaration_identifiers()` | SSO | API 표면 식별자만 추출 (local var 제외) |
| `linearize_structure_only()` | SSO | 선언 구조 스켈레톤 토큰화 |
| `extract_class_declarations()` | AFC | 클래스 선언 추출 |

### 설계 포인트
- **Lazy Import**: tree-sitter 미설치 시 `None` 반환 → 호출자가 Phase 1 폴백
- **Parser Cache**: `_parser_cache` 딕셔너리로 파서 재생성 방지
- **Boilerplate Filter**: `equals`, `hashCode`, `toString`, getter/setter 자동 제외
- **per-language 타입 호출**: `_get_identifier_types(ext)` 등으로 언어별 노드 타입 조회

---

## 9. `evidence.py` — 다중 증거 채널 분석 (1147 lines)

이 모듈이 Diffinite의 **핵심 분석 엔진**이다. 별도 문서 참조: [evidence_channels.md](evidence_channels.md)

---

## 10. `models.py` — 데이터 모델 (118 lines)

| 클래스 | 용도 |
|--------|------|
| `CommentSpec` | 언어별 주석 마커 사양 (frozen) |
| `FileMatch` | 1:1 매칭 결과 (path_a, path_b, similarity) |
| `DiffResult` | Diff 결과 (ratio, additions, deletions, html_diff) |
| `FingerprintEntry` | Winnowing 핑거프린트 (hash_value, position, frozen) |
| `DeepMatchResult` | N:M 매칭 결과 (channel_scores, classification, afc_results) |
| `AnalysisMetadata` | 실행 파라미터 기록 (재현가능성, frozen) |

---

## 11. `pdf_gen.py` — PDF 보고서 생성 (23KB)

**역할**: Cover page, Diff page HTML 생성 → `xhtml2pdf` 변환 → `pypdf` 병합/Bates 번호.

### 주요 함수
| 함수 | 설명 |
|------|------|
| `build_cover_html(...)` | 커버 페이지 HTML (요약 테이블, 채널 매트릭스, AFC) |
| `build_diff_page_html(...)` | 개별 diff 페이지 HTML |
| `html_to_pdf(html, dest)` | HTML → PDF 변환 |
| `merge_with_bookmarks(...)` | 북마크 포함 PDF 병합 |
| `add_bates_numbers(...)` | Bates 번호 스탬핑 |

---

## 12. `languages/` — 언어 레지스트리 패키지 (13 modules)

**역할**: 언어별 설정(주석, 키워드, tree-sitter 매핑, AST 노드 타입)을 중앙 관리.

| 모듈 | 커버리지 |
|------|----------|
| `_spec.py` | `LangSpec` 데이터클래스 정의 |
| `_registry.py` | 전역 레지스트리 (`_REGISTRY`, `register`, `get_spec`) |
| `_defaults.py` | 기본 AST 노드 타입 세트 |
| `python.py` | `.py` |
| `java.py` | `.java`, `.kt` |
| `javascript.py` | `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs` |
| `c_family.py` | `.c`, `.h`, `.cpp`, `.hpp`, `.cc` |
| `csharp.py` | `.cs` |
| `go_rust_swift.py` | `.go`, `.rs`, `.swift` |
| `scripting.py` | `.rb`, `.php`, `.pl`, `.sh`, `.bash`, `.lua`, `.r` |
| `markup.py` | `.html`, `.xml`, `.htm`, `.svg` |
| `data.py` | `.sql`, `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg` |
