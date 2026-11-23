# Dropnet

**Scam reports arrive one at a time. The scams don't.** Dropnet puts 296,273 real FTC phone-complaint reports into one
Relate graph and finds the number ranges behind them — a pattern a blocklist of single numbers never sees — without
blaming the people whose numbers get faked.

**[Try it in your browser](https://ikooq.github.io/dropnet/)** · [Every result and how to reproduce it](docs/EVIDENCE.md) · [Submission](docs/devpost.md)

![Dropnet on 296,273 real FTC reports](docs/img/real-overview.png)

## Why ranges

92% of the 248,930 reported numbers were reported exactly once: callers move on before a list of numbers catches up.
What repeats is the **range**, the first six digits (10,000 numbers). `Report → Number → Block` makes it visible.
Ranges are built only from reports whose caller area code differs from the consumer's, because a caller ID that copies
the consumer's own area code is often faked. Every answer, in the app, API, MCP tools and Claude Code hook, says so.

## Results

Rules learned from the 192,653 complaints filed before 2026-11-02:

| Test set | Numbers reported ≥ 2 times | + 2,872 geographic ranges | + toll-free ranges |
|---|---:|---:|---:|
| 103,620 complaints filed after the split | 4.3% | **14.3%** | 22.0% |
| 92,712 of them about calls made after the split | 3.5% | **12.7%** | — |
| **Fresh data:** 29,549 complaints filed Nov 13–16, after the snapshot ended | 3.6% | **13.2%** | 20.0% |
| Fresh data, calls made in the new period (21,834) | 3.3% | **11.8%** | 18.2% |

- **Early warning:** replayed day by day with only the previous days' knowledge, a number blocklist knew 2.6% of
  239,932 complaints, the range rule 11.9%. 23,726 numbers first appeared in a range that was already flagged.
- **Pre-registered:** on 2026-11-23 the rule's output (5,765 geographic ranges, 23,740 repeat numbers) was frozen with
  hashes, test set and pass marks in [docs/prediction/](docs/prediction/README.md). It is scored on 2026-12-08.
- **Stable:** ahead from all 27 start days, at least 2.6×.
- **Confirmed elsewhere:** 49 of the 50 largest ranges also appear in the FCC's own complaints, against 9% of random ranges.
- **Search by meaning:** the right complaint category in 78% of the top 10, against 29% by words alone.
- **Agents:** without Dropnet a real Claude Code agent answered "unknown" for 37 of 40 numbers and advised blocking all
  14 whose caller ID matched the consumer's area code; with the MCP tool it followed the evidence in 39 of 40 (agreement with our rules, not ground truth).
- **Human look:** one blinded reviewer rated 10 of 10 strong ranges and 1 of 10 controls worth investigating
  ([report](docs/validation-study/EXPERT_REVIEW.md)).

**What these numbers are not:** matches against unverified complaints, not fraud proven or calls blocked. The
geographic rules cover about 28.7 million numbers and the data hold no legitimate calls, so their cost to legitimate
callers is unknown. Dropnet ranks ranges for a person to decide; it never blocks anything.

## How it uses Relate

`data/ftc.rl` (78 MB, committed) is the whole investigation in one file: 296,273 reports, 248,930 numbers, 96,126
blocks, 1.5 million relationships, 6,146 campaigns. Built in a directory store, then compacted with
`relate clone --to-snapshot-format parquet`; a single campaign can be exported as its own `.rl` file.

| Relate feature | where |
|---|---|
| embedded engine (`relate-db`), `UNWIND`/`MERGE` batch load (296k reports in ~2 min) | `dropnet/ftc/load.py` |
| campaign detection as Cypher aggregations | `dropnet/ftc/campaigns.py` |
| explicit transaction + rollback for what-if rules; one campaign → its own `.rl` | `dropnet/ftc/whatif.py` |
| WebAssembly in the browser demo (~1 s load) | `docs/app.js` |
| hybrid search: vector + full-text `SEARCH`, rank fusion, then a graph filter by state; local embeddings | `dropnet/ftc/semantic.py` |
| MCP: our server and Relate's `relate serve --mcp stdio --read-only` | `.mcp.json` |
| command extension: `relate run dropnet-ftc --path data/ftc/raw -d graph` (296,273 reports → 6,091 ranges in 33 s) | `dropnet/relate_ext/` |
| HTTP Query API v2 and Bolt with the official `neo4j` driver | `dropnet/ftc/bolt.py` |

## Setup and run

Python **3.10+** (tested on 3.14, Windows 11). No API key, no database server.

```bash
git clone https://github.com/ikooq/dropnet && cd dropnet
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e .
python -m dropnet serve        # → http://127.0.0.1:8000
```

Then pick a pool, click a number, run **What-if**, check `833-766-1884`, download a case as `.rl`.

```bash
python -m dropnet ftc-eval                 # the hold-out table, from data/ftc.rl
python -m dropnet ftc-build --fetch        # re-download the FTC files and rebuild (needs the Relate CLI)
python -m dropnet site                     # refresh the browser demo data in docs/
pip install -e ".[dev]" && pytest          # tests
```

## Data and limitations

- Complaint dates, caller IDs and categories are self-reported. A range is an investigative lead, not proof of fraud or
  of a common operator; an NPA-NXX is a numbering prefix, not evidence of who controls it.
- The app and the browser lookup flag call dates later than filing dates without changing source values.
- `data/dropnet.rl` is a separate synthetic demo of free-text complaints; it is not part of the FTC results.
- The demo server has no authentication and is meant for a trusted local machine, not public deployment.
- `likely_spoofed` is a legacy field name for the area-code-match heuristic; it does not establish verified spoofing.

## Disclosure

Built for the Relate by Neo4j Hackathon 2026. MIT license. FTC and FCC public data. AI coding tools assisted the
implementation and documentation; I am responsible for reviewing and testing the result. The human review is in
[docs/validation-study/](docs/validation-study/EXPERT_REVIEW.md); two earlier rounds in
[docs/independent-review/](docs/independent-review/README.md) were not independent enough to count as evidence.
