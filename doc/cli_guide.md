# CLI 사용 가이드

## 기본 사용법

```bash
diffinite <dir_a> <dir_b> [options]
```

---

## 실행 모드

```bash
# Simple 모드 (1:1 매칭만, 빠름)
diffinite dir_a dir_b --mode simple -o report.pdf

# Deep 모드 (기본값, N:M 크로스매칭 포함)
diffinite dir_a dir_b --mode deep -o report.pdf
```

---

## 출력 형식

```bash
# PDF (기본)
diffinite dir_a dir_b -o report.pdf

# 다중 형식 동시 출력
diffinite dir_a dir_b --report-pdf report.pdf --report-html report.html --report-md report.md

# 개별 파일 PDF (병합하지 않음)
diffinite dir_a dir_b --no-merge -o report.pdf
```

---

## 프로파일 시스템 (3-Tier)

### Tier 1: 프로파일 프리셋

```bash
# Industrial (기본): K=5, W=4, T=0.10 — 실무 코드
diffinite dir_a dir_b --profile industrial

# Academic: K=2, W=3, T=0.40 — 학술 코드 (엄격)
diffinite dir_a dir_b --profile academic
```

### Tier 2: 수동 오버라이드

```bash
# 프로파일 기본값을 개별 파라미터로 덮어쓰기
diffinite dir_a dir_b --profile industrial --k-gram 3 --window 5 --threshold-deep 0.20
```

### Tier 3: 감도 분석

```bash
# K×W 조합 스윕 (K∈[2,7], W∈[2,6])
diffinite dir_a dir_b --grid-search
```

---

## 포렌식 옵션

```bash
# 전체 법정 제출용 보고서
diffinite dir_a dir_b -o forensic_report.pdf \
    --no-comments \
    --page-number \
    --file-number \
    --bates-number \
    --show-filename \
    --collapse-identical \
    --multi-channel \
    --profile industrial
```

| 옵션 | 설명 |
|------|------|
| `--no-comments` | 주석 제거 후 비교 |
| `--squash-blanks` | 빈 줄 축소 (⚠ 라인 번호 변경) |
| `--page-number` | 페이지 번호 표시 |
| `--file-number` | 파일 번호 표시 |
| `--bates-number` | Bates 순번 스탬핑 |
| `--show-filename` | 파일명 표시 |
| `--collapse-identical` | 동일 코드 블록 접기 (양측 3줄 컨텍스트) |
| `--by-word` | 단어 단위 비교 (기본: 라인) |

---

## Deep Compare 옵션

| 옵션 | 기본값 | 설명 |
|------|:------:|------|
| `--multi-channel` | off | 6채널 증거 분석 활성화 |
| `--normalize` | off | 식별자 → ID, 리터럴 → LIT 정규화 |
| `--tokenizer` | `token` | 토크나이징 전략: `token`, `ast`, `pdg` |
| `--k-gram` | 5 | K-gram 크기 |
| `--window` | 4 | Winnowing 윈도우 크기 |
| `--threshold-deep` | 0.10 | 최소 Jaccard 유사도 |
| `--workers` | 4 | 병렬 워커 프로세스 수 |

---

## 사용 예시

```bash
# 1. 기본 소스코드 비교
diffinite original/ copy/ -o basic_report.pdf

# 2. AST 기반 구조 분석 + 다중 채널
diffinite plaintiff/ defendant/ --mode deep --tokenizer ast --multi-channel \
    --report-pdf expert_report.pdf --report-md summary.md

# 3. 학술 과제 표절 탐지
diffinite submissions/student_a/ submissions/student_b/ \
    --profile academic --multi-channel --no-comments

# 4. 파라미터 감도 분석
diffinite project_v1/ project_v2/ --grid-search --report-md sensitivity.md
```
