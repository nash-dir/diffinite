# Source Code Comparison Report

## Particulars

| Item | Value |
|---|---|
| Directory A | `original` |
| Directory B | `plagiarized` |
| Report generated | 2026-11-10 04:28 UTC |
| Tool | Diffinite 0.14.0 |
| Comparison unit | line |
| Comments | stripped |
| Matched pairs | 1 |
| Unmatched files | 0 in A; 39 in B |

## Analysis Configuration

| Setting | Value |
|---|---|
| Mode | deep |
| K-gram size (K) | 5 |
| Window size (W) | 4 |
| Jaccard threshold | 93% |
| Threshold source | Default for normalized comparison |
| Identifier normalization | on |
| Line diff autojunk | on |
| Ignore policy | 0 rules; SHA-256 none |
| Selection filter | none; 0 paths; SHA-256 none |

## Analysis Status

| Item | Value |
|---|---|
| State | Complete |
| Inputs not read | 0 |
| File pairs compared | 1 of 1 |
| File pairs failed | 0 |
| Inline diffs truncated | 0 |
| Deep Compare files processed | 41 of 41 |
| Deep Compare files failed | 0 |
| Deep Compare files skipped (binary or not decodable as text) | 0 |
| Deep Compare files with fewer tokens than the k-gram size | 0 |
| Deep Compare pairs at or above the threshold | 18 |
| Deep Compare index | Complete |

## Scope and Limitations

1. Similarity figures in this report measure textual and token overlap between the files compared. They do not establish copying, derivation or infringement.
2. Short files and small code fragments can show high similarity even when written independently, because language syntax and common idioms leave little room for variation.
3. Normalization replaces identifiers and literals before fingerprinting, which raises the similarity of independently written code in the same domain. The default threshold of 93% was set using the IR-Plag Java corpus, where its false-positive rate was 0.95% (1 of 105 independent file pairs; Wilson 95% CI 0.17% to 5.2%). That false positive scored 100%. The pairs come from 7 assignments, so the true uncertainty is wider than this interval. In the measured pairs the smaller file had 212 tokens or fewer (largest file 307 tokens). Other languages and larger files were not measured, and the languages and file sizes of this run were not checked against that scope. At this threshold 65% of near-verbatim copies (level L1) and 0% of heavily restructured copies (levels L4 to L6) were detected.

## Summary

| # | File A | File B | Name similarity | Line match | Added | Deleted |
|--:|--------|--------|--:|--:|--:|--:|
| 1 | `T1.java` | `L1/04/T1.java` | 100.0% | 100.0% | +0 | −0 |

## Unmatched Files

### Only in B (`plagiarized`)

- `L1/01/L1.java`
- `L1/02/Main.java`
- `L1/03/Main.java`
- `L1/05/HelloWorld.java`
- `L1/06/HelloWorld.java`
- `L1/07/Main.java`
- `L1/08/Kasus1L1.java`
- `L1/09/Level1.java`
- `L2/01/L2.java`
- `L2/02/Main.java`
- `L2/03/WelcomeToJava.java`
- `L2/04/hellow.java`
- `L2/05/PrintJava.java`
- `L3/01/L3.java`
- `L3/02/Main.java`
- `L3/03/HelloWorld.java`
- `L3/04/hellow.java`
- `L3/05/Kasus1L3.java`
- `L3/06/Level3.java`
- `L4/01/L4.java`
- `L4/02/Main.java`
- `L4/03/Main.java`
- `L4/04/HelloWorld.java`
- `L4/05/hellow.java`
- `L4/06/Level4.java`
- `L5/01/L5.java`
- `L5/02/Main.java`
- `L5/03/WelcomeToJava.java`
- `L5/04/hellow.java`
- `L5/05/PrintJava.java`
- `L6/01/L6.java`
- `L6/02/Main.java`
- `L6/03/Main.java`
- `L6/04/WelcomeToJava.java`
- `L6/05/HelloWorld.java`
- `L6/06/hellow.java`
- `L6/07/PrintJava.java`
- `L6/08/Kasus1L6.java`
- `L6/09/Level6.java`

## Deep Compare: Cross-Match Results

| File A | File B | Shared hashes | Jaccard | A in B | B in A |
|--------|--------|--:|--:|--:|--:|
| `T1.java` | `L1/01/L1.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/02/Main.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/03/Main.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/04/T1.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/05/HelloWorld.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/06/HelloWorld.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/07/Main.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/08/Kasus1L1.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L1/09/Level1.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L2/01/L2.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L2/02/Main.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L2/04/hellow.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L2/05/PrintJava.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L3/01/L3.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L3/02/Main.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L3/03/HelloWorld.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L3/04/hellow.java` | 10 | 100.00% | 100.00% | 100.00% |
| `T1.java` | `L3/06/Level3.java` | 10 | 100.00% | 100.00% | 100.00% |

A in B is the number of shared hashes divided by the number of unique hashes of the A file; B in A is the same ratio for the B file. Rows are selected by the Jaccard threshold only.
