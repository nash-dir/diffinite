# Normalize-mode error rate (WS-A measurement)

Corpus: Karnalim IR-Plag, 7 cases. Negatives (independent same-domain submissions): **105** pairs. Positives (labelled copies L1–L6): **355** pairs. A negative scoring above threshold is a **false positive**.

## Headline — false-positive rate at the shipped default (`--threshold-deep 5`)

- **raw**: false-positive rate **100.0%**, recall (all levels) 100.0% at threshold 5.
- **normalize**: false-positive rate **100.0%**, recall (all levels) 100.0% at threshold 5.

### False positives stratified by submission size (normalize)

| Size stratum | FP rate @5 | FP rate @20 | FP rate @50 | Note |
|---|---|---|---|---|
| small (<150 tok) (n=75) | 100.0% | 85.3% | 33.3% | |
| medium (150–600) (n=30) | 100.0% | 100.0% | 80.0% | |
| large (>=600) (n=0) | — | — | — | _no samples in corpus_ |

### Recall by obfuscation level

| Threshold | L1 (raw/norm) | L2 (raw/norm) | L3 (raw/norm) | L4 (raw/norm) | L5 (raw/norm) | L6 (raw/norm) |
|---|---|---|---|---|---|---|
| 5 | 100/100 | 100/100 | 100/100 | 100/100 | 100/100 | 100/100 |
| 20 | 100/100 | 100/100 | 98/100 | 88/100 | 80/100 | 65/95 |
| 50 | 100/100 | 30/98 | 28/96 | 12/53 | 0/20 | 2/11 |

### Candidate normalize operating points

Lowest threshold at which the normalize false-positive rate falls to/below a target, and the recall there:

| Target FP | Threshold | Recall (all) |
|---|---|---|
| ≤5% | 77 | 33.5% |
| ≤1% | 93 | 21.7% |
| ≤0% | (unreachable) | — |

### Joint (floor, threshold) calibration frontier — normalize

The 'both' policy raises the threshold **and** withholds a verdict below a token floor. Excluding sub-floor files (precision unsalvageable there) lets the threshold for the rest come down while still meeting the false-positive target.

**Target FP ≤ 5%**

| Token floor | Threshold | FP rate | Recall (≥floor) | Coverage |
|---|---|---|---|---|
| 45 | 77 | 4.8% | 33.5% | 100% |
| 47 | 77 | 4.8% | 33.5% | 99% |
| 52 | 78 | 4.3% | 33.5% | 89% |
| 57 | 78 | 4.4% | 33.5% | 87% |
| 58 | 78 | 4.4% | 33.6% | 87% |
| 59 | 78 | 4.4% | 33.7% | 87% |
| 60 | 78 | 4.4% | 33.8% | 87% |
| 61 | 78 | 4.4% | 33.9% | 87% |
| 62 | 78 | 4.4% | 34.1% | 87% |
| 63 | 78 | 4.4% | 34.3% | 87% |
| 65 | 78 | 4.4% | 34.4% | 86% |
| 67 | 78 | 4.5% | 34.4% | 85% |
| 69 | 78 | 4.5% | 34.4% | 84% |
| 70 | 78 | 4.5% | 34.6% | 84% |
| 71 | 78 | 4.5% | 34.7% | 84% |
| 74 | 78 | 4.7% | 34.9% | 82%  ⟵ recommended |
| 78 | 78 | 4.7% | 34.9% | 81% |
| 80 | 78 | 4.8% | 34.9% | 80% |
| 81 | 78 | 4.8% | 34.9% | 79% |
| 82 | 78 | 4.8% | 34.5% | 79% |
| 84 | 77 | 4.9% | 32.1% | 78% |
| 86 | 77 | 4.9% | 32.1% | 77% |
| 89 | 77 | 5.0% | 32.1% | 76% |
| 91 | 78 | 3.8% | 32.1% | 75% |
| 92 | 78 | 3.9% | 32.1% | 74% |
| 93 | 78 | 3.9% | 32.2% | 74% |
| 96 | 78 | 3.9% | 32.3% | 74% |
| 97 | 78 | 3.9% | 32.3% | 73% |
| 98 | 78 | 3.9% | 32.4% | 73% |
| 100 | 78 | 3.9% | 32.5% | 73% |
| 102 | 78 | 3.9% | 32.7% | 73% |
| 103 | 78 | 3.9% | 32.9% | 73% |
| 104 | 78 | 3.9% | 33.1% | 73% |
| 105 | 78 | 3.9% | 33.3% | 73% |
| 106 | 78 | 4.0% | 33.3% | 72% |
| 107 | 78 | 4.0% | 33.4% | 72% |
| 108 | 78 | 4.0% | 33.5% | 71% |
| 111 | 78 | 4.0% | 33.7% | 71% |
| 112 | 78 | 4.2% | 32.9% | 68% |
| 113 | 78 | 4.3% | 33.5% | 67% |
| 114 | 78 | 5.0% | 29.3% | 57% |
| 116 | 85 | 3.4% | 21.6% | 56% |
| 117 | 85 | 3.4% | 21.7% | 56% |
| 118 | 78 | 3.5% | 29.5% | 55% |
| 119 | 78 | 4.3% | 29.9% | 45% |
| 120 | 78 | 4.8% | 28.9% | 40% |
| 121 | 78 | 4.9% | 28.4% | 39% |
| 165 | 85 | 3.3% | 12.6% | 29% |
| 167 | 85 | 3.3% | 12.8% | 29% |
| 171 | 85 | 3.5% | 12.8% | 28% |
| 173 | 85 | 3.5% | 12.9% | 28% |
| 174 | 85 | 3.5% | 13.0% | 28% |
| 175 | 85 | 3.5% | 13.1% | 28% |
| 177 | 85 | 3.5% | 13.4% | 28% |
| 179 | 85 | 3.5% | 13.7% | 28% |
| 181 | 85 | 3.5% | 13.8% | 28% |
| 188 | 85 | 3.5% | 14.0% | 28% |
| 189 | 85 | 3.6% | 12.1% | 27% |
| 211 | 90 | 0.0% | 13.5% | 14% |
| 212 | 90 | 0.0% | 14.0% | 14% |

> Recommended (highest recall with ≥50% coverage): **floor=74 tokens, threshold=78** → FP 4.7%, recall 34.9%.

**Target FP ≤ 1%**

| Token floor | Threshold | FP rate | Recall (≥floor) | Coverage |
|---|---|---|---|---|
| 45 | 93 | 0.9% | 21.7% | 100%  ⟵ recommended |
| 47 | 93 | 1.0% | 21.7% | 99% |
| 84 | 93 | 0.0% | 18.7% | 78% |
| 86 | 93 | 0.0% | 18.7% | 77% |
| 89 | 93 | 0.0% | 18.7% | 76% |
| 91 | 93 | 0.0% | 18.7% | 75% |
| 92 | 93 | 0.0% | 18.7% | 74% |
| 93 | 93 | 0.0% | 18.8% | 74% |
| 96 | 93 | 0.0% | 18.9% | 74% |
| 97 | 93 | 0.0% | 18.9% | 73% |
| 98 | 93 | 0.0% | 18.9% | 73% |
| 100 | 93 | 0.0% | 19.0% | 73% |
| 102 | 93 | 0.0% | 19.1% | 73% |
| 103 | 93 | 0.0% | 19.2% | 73% |
| 104 | 93 | 0.0% | 19.3% | 73% |
| 105 | 93 | 0.0% | 19.5% | 73% |
| 106 | 93 | 0.0% | 19.5% | 72% |
| 107 | 93 | 0.0% | 19.5% | 72% |
| 108 | 93 | 0.0% | 19.6% | 71% |
| 111 | 93 | 0.0% | 19.7% | 71% |
| 112 | 93 | 0.0% | 18.9% | 68% |
| 113 | 93 | 0.0% | 19.2% | 67% |
| 114 | 93 | 0.0% | 16.4% | 57% |
| 116 | 93 | 0.0% | 16.4% | 56% |
| 117 | 93 | 0.0% | 16.4% | 56% |
| 118 | 90 | 0.0% | 19.3% | 55% |
| 119 | 90 | 0.0% | 19.6% | 45% |
| 120 | 90 | 0.0% | 16.0% | 40% |
| 121 | 90 | 0.0% | 16.1% | 39% |
| 165 | 90 | 0.0% | 10.7% | 29% |
| 167 | 90 | 0.0% | 10.8% | 29% |
| 171 | 90 | 0.0% | 10.8% | 28% |
| 173 | 90 | 0.0% | 10.9% | 28% |
| 174 | 90 | 0.0% | 11.0% | 28% |
| 175 | 90 | 0.0% | 11.1% | 28% |
| 177 | 90 | 0.0% | 11.3% | 28% |
| 179 | 90 | 0.0% | 11.6% | 28% |
| 181 | 90 | 0.0% | 11.7% | 28% |
| 188 | 90 | 0.0% | 11.8% | 28% |
| 189 | 90 | 0.0% | 9.9% | 27% |
| 211 | 90 | 0.0% | 13.5% | 14% |
| 212 | 90 | 0.0% | 14.0% | 14% |

> Recommended (highest recall with ≥50% coverage): **floor=45 tokens, threshold=93** → FP 0.9%, recall 21.7%.

> These are candidate operating points for WS-B, not a decision. The threshold and the 'inconclusive' floor are forensic-defensibility calls for the maintainer to ratify.
