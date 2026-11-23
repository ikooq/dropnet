# Evidence index

Every number in the README and the submission, where it is stored, and how to reproduce it. Run the commands from the
repository root after `pip install -e .`.

| Claim | Result file | Reproduce |
|---|---|---|
| Hold-out: 4.3% → 14.3% (22.0% with toll-free) of 103,620 later complaints | `data/ftc/eval.json` (`baseline`, `dropnet_geographic`, `dropnet`) | `python -m dropnet ftc-eval` |
| Same, on call dates after the split: 3.5% → 12.7% | `data/ftc/time_audit.json` | `python -m dropnet.ftc.time_audit` |
| Fresh data after the snapshot: 3.6% → 13.2% (3.3% → 11.8% by call date) | `docs/evaluation/fresh-ftc-2026-11-18.json`, [report](evaluation/fresh-ftc-2026-11-18.md) | `python scripts/evaluate_fresh_ftc.py --train-dir data/ftc/raw --test-dir data/ftc/fresh-2026-11-18` |
| Early warning: 2.6% vs 11.9% replayed day by day; 4,713 ranges, median 14 days; 23,726 numbers seen first in a flagged range | `data/ftc/eval.json` (`early_warning`) | `python -m dropnet ftc-early-warning` |
| Pre-registered forward test: lists frozen 2026-11-23, checked on files published after 2026-11-19 | `docs/prediction/` (`manifest.json`, hashes) | `python scripts/preregister.py check --prediction docs/prediction --test-dir data/ftc/after-freeze` |
| 27 of 27 start days, lift ≥ 2.6×; bootstrap intervals; threshold sweep; ablations | `data/ftc/eval.json` (`robustness`) | `python -m dropnet ftc-robustness` |
| Random-range control: 20.3% vs 4.4% | `data/ftc/eval.json` (`controls`) | `evaluate.controls(conn, "2026-11-02")` in `dropnet/ftc/evaluate.py` |
| FCC cross-check: 49 of 50 largest ranges vs 9% random | `data/ftc/eval.json` (`fcc_crosscheck`), `data/fcc/` | `crosscheck.crosscheck(...)` in `dropnet/ftc/crosscheck.py` |
| Hybrid search: 0.78 vs 0.29 precision at 10 on 14 descriptions | `data/ftc/search_eval.json` | `dropnet/ftc/semantic.py` (`evaluate`), needs `pip install -e .[semantic]` |
| Real agent, 40 numbers, with and without the MCP tool | `data/ftc/live_agent_eval.json` | `python -m dropnet ftc-live-agent-eval` (calls the `claude` CLI) |
| Blinded review of 30 ranges by one reviewer | [validation-study/EXPERT_REVIEW.md](validation-study/EXPERT_REVIEW.md) | protocol in [validation-study/PROTOCOL.md](validation-study/PROTOCOL.md) |
| Relate extension: 296,273 reports → 6,091 ranges in 33 s | — | `python -m dropnet relate-ext`, then `relate run dropnet-ftc --path data/ftc/raw -d graph` |

Not evidence, kept as a record: the two review rounds in [independent-review/](independent-review/README.md) (see the
note at the top of each report).

All results are matches against unverified FTC complaints. They are not calls blocked, fraud proven or a measure of
harm to legitimate callers; the data contain no legitimate calls.
