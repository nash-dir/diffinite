# false-positive-traps corpus

Every pair here is independently written code (except the control) that shares
structure for legitimate reasons. A fair tool should report the shared parts
truthfully ("where") but the overall score should stay low, or the report should
make it obvious that the shared region is boilerplate / third-party.

| case | left | right | why it looks similar | expected |
|---|---|---|---|---|
| flask_boilerplate | app.py: task tracker (SQLite, 127 lines) | app.py: bookshelf API (139 lines) | identical Flask idiom: `get_db`/`close_db` teardown pattern (copied from Flask tutorial), errorhandler 404, `if __name__` run block | low line ratio (<0.35), low raw Jaccard (<0.2); normalize mode will inflate because the code shapes are similar but should stay below the calibrated 93 cut |
| express_boilerplate | server.js: URL shortener | server.js: inventory API | identical helmet/cors/json/morgan setup, 404 + 500 handlers, listen, module.exports | low line ratio, low raw Jaccard; normalize expected higher but < 93 |
| license_header_only | Config.java: weather station config | Config.java: retry policy | identical 17-line Apache-2.0 header; rest unrelated | line ratio driven only by header (~0.2-0.3); raw Jaccard modest; --strip-comments must drop it to ~0 |
| generated_protobuf | user_pb.go (User/GetUserRequest) | order_pb.go (Order/CancelOrderRequest) | protoc-gen-go output: identical Reset/String/ProtoReflect/getter skeletons | different filenames -> 1:1 line channel likely unmatched; deep should find substantial overlap (machine-generated). Normalized Jaccard very high -> genuine FP trap for normalize mode |
| independent_algorithms | algos.py (Lomuto quicksort, closed binary search, bfs, dijkstra...) + search.c (binary search, insertion/bubble sort) | algos.py (functional quicksort, half-open binary search, sieve...) + search.c (sensor table bsearch, qsort) | same algorithms, same function names in places, different authors and styles | low across all modes; normalize may raise somewhat |
| vendored_library | blog.py + vendor/textkit.py | renamer.py + vendor/textkit.py | byte-identical vendored MIT library in both trees; own code unrelated | textkit.py reported as 100% identical (correct, it IS identical), blog.py/renamer.py unmatched or low; aggregate should not be presented as "projects are X% copied" without noting the vendored file |
| tiny_files | 1-3 line files: `__init__.py`, index.js, main.py stub, setup.cfg, run.sh, .gitignore | same shapes, different content | files too short for k-gram fingerprinting | must not report high similarity from tiny files; ideally flagged inconclusive / too short |
| control_renamed_copy (positive control) | flask_boilerplate/left/app.py | same file with identifiers renamed via sed (task->item, get_db->open_conn ...) | genuine copying with renaming | should be clearly higher than every trap; normalize Jaccard ~1.0 |

Outputs: `<case>/out/<mode>/report.json` (+ stderr.txt, manifest). Modes run by
`scratchpad/run_fp.py`: default, default_t0 (--threshold-deep 0), strip
(--strip-comments, t0), norm (--normalize --strip-comments, calibrated default 93),
norm_t0, lang_t0 (--normalize --lang-aware --strip-comments, t0), simple (--mode simple).
