# 개발 가이드

## 환경 설정

```bash
# 기본 설치
pip install -e "."

# 개발 의존성 추가 (pytest)
pip install -e ".[dev]"

# AST 분석 지원 (tree-sitter)
pip install -e ".[ast]"

# 전체
pip install -e ".[dev,ast]"
```

### 요구사항
- **Python**: ≥ 3.10
- **OS**: Windows, macOS, Linux

---

## 프로젝트 구조

```
diffinite/
├── src/diffinite/           # 메인 패키지
│   ├── __init__.py          # 버전 (v0.2.0)
│   ├── __main__.py          # python -m diffinite
│   ├── cli.py               # CLI 진입점
│   ├── pipeline.py          # 파이프라인 오케스트레이터
│   ├── collector.py         # 파일 수집 & 매칭
│   ├── parser.py            # 2-pass 주석 제거
│   ├── differ.py            # Diff & HTML 생성
│   ├── fingerprint.py       # Winnowing 핑거프린트
│   ├── deep_compare.py      # N:M 크로스매칭
│   ├── ast_normalizer.py    # AST/PDG 정규화
│   ├── evidence.py          # 증거 채널 엔진 (핵심)
│   ├── models.py            # 데이터 클래스
│   ├── pdf_gen.py           # PDF 보고서 생성
│   └── languages/           # 언어 레지스트리
│       ├── _spec.py         # LangSpec 데이터클래스
│       ├── _registry.py     # 전역 레지스트리
│       ├── _defaults.py     # 기본 AST 노드 타입
│       ├── python.py        # Python 사양
│       ├── java.py          # Java/Kotlin
│       ├── javascript.py    # JS/TS
│       ├── c_family.py      # C/C++
│       ├── csharp.py        # C#
│       ├── go_rust_swift.py # Go/Rust/Swift
│       ├── scripting.py     # Ruby/PHP/Perl/Shell/Lua/R
│       ├── markup.py        # HTML/XML
│       └── data.py          # SQL/JSON/YAML/TOML
│
├── tests/                   # 단위/통합 테스트 (304+)
├── TDD/                     # TDD 코퍼스 + 법리 방어 테스트
├── doc/                     # 문서 (이 디렉토리)
├── example/                 # 예제 파일
├── report/                  # 생성된 보고서
├── pyproject.toml           # 빌드 설정
├── requirements.txt         # 의존성
└── README.md                # 프로젝트 소개
```

---

## 테스트

```bash
# 전체 테스트 실행
python -m pytest tests/ -x -q

# TDD 코퍼스 테스트 포함
python -m pytest tests/ TDD/corpus/ TDD/legal_defense/ -x -q

# 커버리지
python -m pytest tests/ --cov=diffinite --cov-report=term-missing
```

### 테스트 파일 목록

| 파일 | 대상 | 테스트 수 |
|------|------|:---------:|
| `test_ast_normalizer.py` | AST/PDG 정규화 | 다수 |
| `test_cli.py` | CLI 인자 파싱 | 다수 |
| `test_collector.py` | 파일 수집 & 매칭 | 다수 |
| `test_deep_compare.py` | N:M 크로스매칭 | 다수 |
| `test_differ.py` | Diff 계산 | 다수 |
| `test_differ_extended.py` | 확장 diff 기능 | 다수 |
| `test_evidence.py` | 증거 채널 | 다수 |
| `test_fingerprint.py` | Winnowing | 다수 |
| `test_languages.py` | 언어 레지스트리 | 다수 |
| `test_normalize.py` | 토큰 정규화 | 다수 |
| `test_parser.py` | 주석 제거 | 다수 |
| `test_pdf_gen.py` | PDF 생성 | 다수 |
| `test_pipeline.py` | 파이프라인 통합 | 다수 |
| `test_plagiarism_dataset.py` | IR-Plag 데이터셋 | 다수 |
| `test_sqlite_integration.py` | SQLite 통합 | 다수 |

### TDD 코퍼스 테스트

```
TDD/
├── corpus/              # 코퍼스 기반 TDD
│   ├── conftest.py      # 점수 데이터 로드
│   ├── test_*.py        # 8-stage 파이프라인
│   └── report/          # 분석 보고서
└── legal_defense/       # 법리 방어 테스트
    ├── conftest.py
    └── test_idex_*.py   # IDEX 테스트
```

---

## 신규 언어 추가

1. `languages/` 에 새 모듈 생성 (예: `kotlin.py`)
2. `LangSpec` 인스턴스 정의:

```python
from diffinite.languages._spec import LangSpec
from diffinite.languages._registry import register
from diffinite.models import CommentSpec

_KOTLIN_SPEC = LangSpec(
    comment=CommentSpec(
        line_markers=("//",),
        block_start="/*",
        block_end="*/",
    ),
    keywords=frozenset({"fun", "val", "var", "when", "data", ...}),
    tree_sitter_module="tree_sitter_kotlin",
    tree_sitter_func="language",
)

register(".kt", _KOTLIN_SPEC)
```

3. `languages/__init__.py` 에서 import 추가
4. `tests/test_languages.py` 에 테스트 추가

---

## 분류 프로파일 추가

`evidence.py`에 새 `ClassificationThresholds` 인스턴스를 생성:

```python
from diffinite.models import ClassificationThresholds

CUSTOM_THRESHOLDS = ClassificationThresholds(
    dc_raw_min=0.55,
    dc_ident_min=0.35,
    # ... 18 필드 (미지정 시 industrial 기본값)
)
```

`_THRESHOLDS_MAP`에 등록 후 `cli.py`의 `PROFILES` 및 `--profile` choices에도 반영 필요.

---

## Git 브랜치 전략

```
main     ← 안정 릴리스
  └── dev   ← 개발 브랜치 (TDD → src 반영)
```

### 커밋 컨벤션
```
feat(module): description        # 신규 기능
fix(module): description         # 버그 수정
docs: description                # 문서
refactor(module): description    # 리팩토링
test: description                # 테스트
```
