# SDD ledger — plan: docs/superpowers/plans/2026-11-16-dropnet-v2.md
V2 Task 1: Ruling: unquoted subjects with commas are re-joined from extra CSV columns — robustness — none.
V2 Task 1: TDD gap: fetch.py written in the same step as its test (RED not observed). Parse tests did go RED first.
V2 Task 1: Finding: ftc.gov returns 404 without an Accept header; added. Data: 25 files, 296,273 reports, 248,930 numbers, 96,126 NPA-NXX blocks, 35 report days (2026-10-09..2026-11-12), neighbor 36.8%, robocall 71%, numbers with >=2 reports 19,584 (7.9%).
V2 Task 1: complete (tests: test_ftc_parse 5 + test_ftc_fetch 3 passed)
V2 Task 2: Ruling: Report nodes slimmed (no created/city/subject props, no Day nodes) and the store is compacted with `relate clone --to-snapshot-format parquet` (150 MB -> 40 MB) so it fits git — cost if wrong: city not queryable; build needs the Relate CLI for compaction (falls back to a directory store).
V2 Task 3: Ruling: pool campaigns are built from NON-neighbor reports only — blocking blocks of spoofed local numbers would hit innocent subscribers — cost if wrong: misses some pools.
V2 Task 4: Real hold-out (train < 2026-11-02, 192,653; test 103,620): every number ever reported 163,606 rules -> 6.2%; blocklist >=2 reports 11,968 rules -> 4.3%; Dropnet 15,649 rules (11,968 numbers + 3,681 pool blocks) -> 22.0%; 17,532 caught reports came from never-before-reported numbers; 98% of neighbor-spoofed test reports come from never-seen numbers.
V2 Task 4: Ruling: split = 70% of distinct report days (build and eval now agree) — fixed inconsistency found by running both.
V2 Tasks 2-4: complete (tests: pytest -q -> 164 passed)
V2 Task 5: Real data: what-if on top-10 pool blocks since 2026-11-02 -> 4,197 reports, 839 numbers, 10 campaigns in 0.07 s; 833-766-1884 (1,202 reports, 50 states) sits in a 27-number pool; export of POOL-866771 -> 1,598 reports, 1.1 MB file, 0.5 s.
V2 Task 5: complete (tests: test_ftc_whatif 4 passed)
V2 Task 6a: Ruling: older web/MCP tests pass ftc_snapshot to a missing path — default copies the real 40 MB store per test (211 s -> 23 s). Found: request models must be module-level (from __future__ annotations) or FastAPI treats the body as a query param.
V2 Task 6b: Finding: Relate 1.0.1 does not use the property index for `UNWIND $list AS x MATCH (:Number {number: x})` on the 249k-number graph (21 s for 60 lookups) while the block-anchored query takes 0.03 s — campaign_graph rewritten; test_campaign_graph_is_fast_on_the_real_snapshot RED (38 s) -> GREEN (<2 s). Worth reporting to Relate.
V2 Task 6b: Finding: relate.Record (dict subclass) serialises only result columns — derived keys vanished from JSON (NaN in UI); store.rows now returns plain dicts — test_ftc_summary RED -> GREEN; suite 178/178.
V2 Task 6b: UI verified in browser via DOM (window minimised, no screenshot): spoof bars, number check (833-766-1884 pool, 1,202 reports, 50 states), what-if (1,598 reports / 138 numbers).
V2 Task 8: complete — hook via 'dropnet hook' (UserPromptSubmit, .claude/settings.json); 0.75 s on the real 40 MB snapshot; tests 4 passed.
V2 Task 7: Finding (Relate WASM 1.0.1): per-row property MATCH costs ~0.5 ms (26k edges = 13 s) and MERGE inside FOREACH ~0.7 ms; loading via collect()-into-lists + xs[i] index endpoints takes ~1 s. Page load 1.3 s for 7,872 nodes / 34,070 rels; queries ~4 ms.
V2 Task 7: Ruling: demo lives in docs/ (GitHub Pages serves only / or /docs) — none. Ruling: `dropnet site` CLI wrapper untested (thin) — low.
V2 Task 7: complete (tests: test_site 2 passed; verified in browser)
V2 Task 9: README v2 + docs/devpost.md; claims checked against the store (1,531,971 rels; 6,091 pools + 55 repeat; 184 tests).
V2 Final review (Opus): Critical none; Important 4; verdict "with fixes". Verified by reviewer: no train/test leakage; README numbers reproduce; rollback holds under injected exception; no XSS; no path traversal.
V2 Final: fixed Important-1 (block-rule cost hidden) — holdout reports numbers_blocked and a geographic-only variant (14.3%, 2,872 blocks, 28.7 M numbers) next to all-pools (22.0%, 36.8 M); README/devpost/UI reworded; test_holdout_evaluation RED->GREEN.
V2 Final: fixed Important-2 (demo labelled 109 likely-spoofed numbers as pool members) — export carries verdict; demo shows "Likely spoofed"; test_export_marks_spoofed_numbers RED->GREEN; verified in browser.
V2 Final: fixed Important-3 (temp folder per export) — served from memory, folder removed on all paths; test RED->GREEN.
V2 Final: fixed Important-4 (README Relate note inaccurate) — reworded to the multi-hop shape actually measured (doc-only).
V2 Final: fixed minor hook issues (odd JSON, 20k-char cap/early stop, silent when all numbers unknown) — tests RED->GREEN; web what-if now uses the split day and shows spoofed-in-scope as risk.
V2 Final: minor (deferred): MCP 40 MB temp copy not cleaned if the process is killed; since_day not format-validated; export_case does not embed the caution; CLI 6.2% vs UI 6.3% rounding of 0.0625.
V2 suite: 187 passed.
