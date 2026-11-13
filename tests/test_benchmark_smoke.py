"""Identity smoke test using one public Karnalim IR-Plag case-01 file.

Both sides hold the same text, so this proves only that an identical file clears
the normalize auto threshold. It is not evidence about real L1 modifications.
"""

from pathlib import Path

from diffinite.calibration import resolve_threshold_deep
from diffinite.deep_compare import run_deep_compare


# Exact Apache-2.0 sample from IR-Plag case-01 original/T1.java and
# plagiarized/L1/04/T1.java:
# https://github.com/oscarkarnalim/sourcecodeplagiarismdataset
_IR_PLAG_T1 = """\
public class T1 {
    public static void main(String[] args) {
        System.out.println("Welcome to Java");
        System.out.println("Welcome to Java");
        System.out.println("Welcome to Java");
        System.out.println("Welcome to Java");
        System.out.println("Welcome to Java");
    }
}
"""


def test_ir_plag_case01_near_verbatim_smoke(tmp_path: Path):
    """An identical file still clears the normalize auto operating point."""
    original = tmp_path / "original"
    candidate = tmp_path / "plagiarized" / "L1" / "04"
    original.mkdir()
    candidate.mkdir(parents=True)
    (original / "T1.java").write_text(_IR_PLAG_T1, encoding="utf-8")
    (candidate / "T1.java").write_text(_IR_PLAG_T1, encoding="utf-8")

    threshold, provenance = resolve_threshold_deep(None, normalize=True)
    assert provenance == "normalize-default"

    results = run_deep_compare(
        str(original),
        str(candidate),
        ["T1.java"],
        ["T1.java"],
        workers=1,
        min_jaccard=threshold / 100.0,
        normalize=True,
        strip_comments=True,
    )

    assert results
    match = results[0].matched_files_b[0]
    assert match[0] == "T1.java"
    assert match[2] == 1.0
