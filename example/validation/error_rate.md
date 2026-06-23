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

> These are candidate operating points for WS-B, not a decision. The threshold and any size-based 'inconclusive' floor are forensic-defensibility calls for the maintainer.
