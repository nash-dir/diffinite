# Restructured (Type-3) corpus

Every case has `left/` (the original) and `right/` (the derived version). The runs produced `report_<profile>.json` and `log_<profile>.txt` in each case folder.
Profiles: default (deep, raw, threshold 5), simple, norm (--normalize, threshold 93), normlang (--normalize --lang-aware),
normstrip (--normalize --strip-comments, the calibrated profile), raw_t0 / normstrip_t0 (the same with --threshold-deep 0, to show suppressed scores).
Note: each run overwrites `manifest.sha256.json` in the case folder, so that manifest covers only the last run.

| Case | Lang | Transformation | Expected (fair, explainable tool) |
|---|---|---|---|
| 01_reorder | Python | The same 10 top-level defs/classes in a shuffled order. Bodies are byte-identical; only the blank lines between blocks changed. | Near-total similarity (>=90%) on the order-insensitive channel. The line channel may be lower, but it should not suggest the file is mostly different. |
| 02_insert_delete | Java | Logging and a counter were inserted. One validation and one method (largestOrder) were deleted. An idempotent-cancel branch and a tracking-number check were added. About 80% of the lines are unchanged. | High similarity (~70-85%), with the inserted and deleted regions localised. |
| 03_split_files | JS | One shop.js file was split verbatim into cart.js, pricing.js and format.js, plus require/exports glue. | No 1:1 name match. N:M should find all 3 pieces, and each piece should show as almost entirely contained in shop.js. |
| 04_merge_files | Go | cache.go, ratelimit.go and retry.go were merged verbatim into netkit.go with one combined import block, in a different order. | Each left file should show as ~100% present in netkit.go. |
| 05_extract_helper | C | config_load's inline trim, unquote, section and key/value logic was extracted into static helpers (trim, copy_field, unquote, parse_section, add_entry, parse_pair, matches_any). The other functions are unchanged. | Moderate-to-high similarity (~50-70%), with the unchanged functions shown as identical. |
| 06_loop_rewrite | Python | Every `for` loop was rewritten as an index-based `while` loop. Nothing else changed. | High similarity (~70-80%); the rewritten loops are the only differences. |
| 07_partial_copy | Python | haversine_km and bounding_box (about 26 of 116 lines, ~22% of geo.py) were copied verbatim into dispatch.py, a larger (210-line) unrelated courier-dispatch module. | Should be flagged: "~25% of geo.py appears in dispatch.py", localised to those two functions. |
| 08_trap_unrelated | Python | NEGATIVE CONTROL. left = the 06 left textstats.py. right = an independently written textstats.py with the same file name and the same domain (word counts, readability), written in a different style. | ~0% similarity. Any notable score is a false positive. |
