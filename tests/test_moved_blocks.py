"""Moved-block detection: exact paired indices, no gap-fill, no boilerplate anchors.

Opcodes are hand-crafted (instead of via SequenceMatcher) so the relocation
scenarios are deterministic and the invariants are unambiguous.
"""

from diffinite.differ import detect_moved_blocks


def test_pairs_are_equal_length_and_exact():
    lines_a = ["m0", "m1", "m2", "x", "y"]
    lines_b = ["x", "y", "q", "r", "s", "m0", "m1", "m2"]
    opcodes = [
        ("delete", 0, 3, 0, 0),
        ("equal", 3, 5, 0, 2),
        ("insert", 5, 5, 2, 8),
    ]
    blocks = detect_moved_blocks(opcodes, lines_a, lines_b)
    assert len(blocks) == 1
    mb = blocks[0]
    assert len(mb.a_lines) == len(mb.b_lines) == 3
    assert mb.a_lines == (0, 1, 2)
    assert mb.b_lines == (5, 6, 7)


def test_gap_line_is_not_marked_as_moved():
    # A2 ("GAP") matches nothing in B; it must NOT be filled into the block.
    lines_a = ["m0", "m1", "GAP", "m3", "x"]
    lines_b = ["x", "q", "r", "s", "s2", "m0", "m1", "DIFF", "m3"]
    opcodes = [
        ("delete", 0, 4, 0, 0),
        ("equal", 4, 5, 0, 1),
        ("insert", 5, 5, 1, 9),
    ]
    blocks = detect_moved_blocks(opcodes, lines_a, lines_b)
    assert len(blocks) == 1
    mb = blocks[0]
    assert 2 not in mb.a_lines
    assert mb.a_lines == (0, 1, 3)
    assert len(mb.a_lines) == len(mb.b_lines)


def test_boilerplate_only_lines_do_not_anchor_moves():
    # Three brace-only lines "relocated" must not form a moved block.
    lines_a = ["}", "}", "}", "real_a"]
    lines_b = ["real_b", "}", "}", "}"]
    opcodes = [
        ("delete", 0, 3, 0, 0),
        ("replace", 3, 4, 0, 1),
        ("insert", 4, 4, 1, 4),
    ]
    blocks = detect_moved_blocks(opcodes, lines_a, lines_b)
    assert blocks == []
