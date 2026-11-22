# Dropnet

**Scam reports arrive one at a time. The scams don't.** Dropnet puts 296,273 real FTC phone-complaint reports into one
Relate graph and finds the number ranges behind them — the pattern a blocklist of single numbers never sees — while
refusing to blame the people whose numbers get faked.

**[Try it in your browser](https://ikooq.github.io/dropnet/)** · [Every result and how to reproduce it](docs/EVIDENCE.md) · [Submission](docs/devpost.md)

![Dropnet on 296,273 real FTC reports](docs/img/real-overview.png)

## Why ranges

92% of the 248,930 reported numbers in our window were reported exactly once: callers move to the next number long
before a list of numbers catches up. What repeats is the **range** — the first six digits (NPA-NXX), 10,000 possible
numbers. `Report → Number → Block` makes that visible: a range with many different reported numbers, the same
complaint categories and consumers in many states is a lead worth an analyst's time.

Dropnet builds ranges only from reports whose caller area code differs from the consumer's, because a caller ID that
copies the consumer's own area code is often faked and its real owner uninvolved. Every answer — on the page, in the
API, in the MCP tools and the Claude Code hook — carries that caution.

## Results

Rules learned from the 192,653 complaints filed before 2026-11-02, matched against later complaints:

| Test set | Numbers reported ≥ 2 times | + 2,872 geographic ranges | + toll-free ranges |
|---|---:|---:|---:|
| 103,620 complaints filed after the split | 4.3% | **14.3%** | 22.0% |
| 92,712 of them about calls made after the split | 3.5% | **12.7%** | — |
| **Fresh data:** 29,549 complaints filed Nov 13–16, after the snapshot ended | 3.6% | **13.2%** | 20.0% |
| Fresh data, calls made in the new period (21,834) | 3.3% | **11.8%** | 18.2% |

- **Early warning:** replaying all 239,932 geographic complaints day by day, using only what was known the day
  before, a blocklist of numbers already knew 2.6% of them; the range rule 11.9%. 4,713 ranges were flagged, a median
  of 14 days after their first complaint in the window, and 23,726 numbers first appeared in a range that was already
  flagged (`python -m dropnet ftc-early-warning`).
- **Stable:** 27 different start days, ranges ahead every time (at least 2.6×; `python -m dropnet ftc-robustness`).
- **Confirmed elsewhere:** 49 of the 50 largest ranges also appear in the FCC's separate complaints, against 9% of
  random reported ranges.
- **Searchable by meaning:** hybrid search finds the right complaint category in 78% of its top 10 for everyday
  descriptions, against 29% by words alone.
- **Agents:** a real Claude Code agent asked about 40 numbers answered "unknown" 37 times without Dropnet and advised
  blocking all 14 numbers whose caller ID matched the consumer's area code; with Dropnet's MCP tool its answers
  followed the evidence in 39 of 40. This measures agreement with our rules, not ground truth.
- **A human look:** one blinded reviewer rated all 10 strong ranges worth investigating and 1 of 10 controls
  ([report](docs/validation-study/EXPERT_REVIEW.md)).

Reproduce: `python -m dropnet ftc-eval`, `python -m dropnet.ftc.time_audit`,
`python scripts/evaluate_fresh_ftc.py --train-dir data/ftc/raw --test-dir data/ftc/fresh-2026-11-18`
([details](docs/evaluation/fresh-ftc-2026-11-18.md)).

**What these numbers are not.** They count matches against complaints, not fraud proven or calls blocked. Complaints
and caller IDs are unverified. The geographic rules cover about 28.7 million possible numbers, and the data hold no
legitimate calls, so their cost to legitimate callers is unknown. Dropnet ranks ranges for a person to decide; it never
blocks anything.

## How it uses Relate

- **Mode: single file.** `data/ftc.rl` (78 MB with the range embeddings, committed) holds the whole graph: 296,273 reports, 248,930 numbers,
  96,126 blocks, 1,531,971 relationships, 6,146 campaigns (6,091 pools, 55 repeat numbers). A second file, `data/dropnet.rl`, holds the free-text module.
- **Why this mode:** the investigation is one portable artifact — judges and colleagues open exactly the graph we built,
  and a single campaign can be handed over as its *own* `.rl` file (`Download case`). Built in a directory store,
  then compacted with `relate clone --to-snapshot-format parquet` (150 MB → 40 MB; the embeddings for hybrid search add 38 MB) so it fits a git repo.
- **What the graph models:** reports, numbers, NPA-NXX blocks, area codes, states, scam types, pool/repeat campaigns —
  plus, in the second module, free-text complaints, cards, IBANs, phishing domains, aliases and money transfers.

| Relate feature | where |
|---|---|
| embedded Python engine (`relate-db`), range indexes, `UNWIND`/`MERGE` batch load (296k reports in ~2 min) | `dropnet/ftc/load.py` |
| campaign detection as Cypher aggregations over the graph | `dropnet/ftc/campaigns.py` |
| **explicit transaction + rollback** for what-if blocking rules | `dropnet/ftc/whatif.py` |
| one campaign → its own single-file store | `whatif.export_case` |
| `relate clone --to-snapshot-format parquet` compaction | `dropnet/ftc/build.py` |
| **WebAssembly build** in the browser demo (in-memory, ~1 s load) | `docs/app.js` |
| **full-text index** + `db.index.fulltext.queryNodes` ("mortgage" → scam type → its pools; `GET /api/ftc/search?q=`) | `dropnet/ftc/api.py` |
| **hybrid search on the real ranges**: `SEARCH … IN (VECTOR INDEX …)` + `SEARCH … IN (FULLTEXT INDEX …)`, weighted Reciprocal Rank Fusion, then a graph filter (ranges reported by consumers in a state); local bge-small embeddings, no API key | `dropnet/ftc/semantic.py` |
| vector index + `db.index.vector.queryNodes`, `shortestPath`, variable-length money trails | free-text module |
| **MCP**: our server + Relate's native `relate serve --mcp stdio --read-only` | `.mcp.json` |
| **command extension** — `relate run dropnet-ftc --path data/ftc/raw -d graph`: FTC files → graph → pools inside Relate's own CLI (296,273 reports → 6,091 pools in 33 s, the same count as the full build) | `dropnet/relate_ext/` |
| **HTTP Query API v2** (`relate serve --http`, `POST /db/neo4j/query/v2`) and **Bolt** with the official `neo4j` driver | `dropnet/ftc/bolt.py` |
| `relate push` of a selected subgraph to Neo4j / Aura; markdown-vault snapshot format | Relate CLI |


## Setup and run

Python **3.10+** (tested on 3.14, Windows 11). No API key, no database server.

```bash
git clone https://github.com/ikooq/dropnet && cd dropnet
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e .
python -m dropnet serve        # → http://127.0.0.1:8000  (opens on "Real reports (FTC)")
```

Then: pick a pool, click a number, run **What-if**, check `833-766-1884`, download a case as `.rl`.

```bash
python -m dropnet ftc-eval                 # the hold-out table above, recomputed from data/ftc.rl
python -m dropnet ftc-build --fetch        # re-download the FTC files and rebuild (needs the Relate CLI to compact)
python -m dropnet site                     # refresh the browser demo data in docs/
python -m dropnet carrier-csv              # data/ftc/ranges.csv: 6,091 ranges, evidence, FCC check, price
pip install -e ".[dev]" && pytest          # run the test suite
```


## Data and limitations

- `data/ftc.rl`: persistent snapshot of FTC complaints; `data/ftc/raw/`: input files; `data/ftc/eval.json`: historical evaluations.
- `data/dropnet.rl`: separate synthetic Russian-language free-text demonstration; it is not part of the FTC results.
- `docs/data/graph.json`: top-pool graph slice for WASM; `docs/data/lookup.txt`: reported-number lookup. Browser visualizations are a sample, not the full graph.
- Complaint dates, caller IDs and categories are self-reported. Range concentrations and network links are investigative hypotheses. An NPA-NXX is a numbering prefix, not evidence of allocation or control by a particular operator.
- Full card redaction covers specific 16-digit formats; it is not general anonymization. The demo server has no user authentication and is intended for a trusted local environment, not public deployment or real sensitive complaints.
- `likely_spoofed` and `spoofed_*` remain legacy machine-readable names for area-code-match heuristics; their names do not establish verified spoofing.

## Development and disclosure

Built for the Relate by Neo4j Hackathon 2026. MIT license. FTC and FCC public datasets are used as described above. AI coding tools assisted implementation and documentation; the team is responsible for reviewing and testing the result. Historical agent-run artifacts were generated with Claude Code; consult their metadata for the particular model and settings.

Human review: the label-blinded review of 30 ranges is in [docs/validation-study/EXPERT_REVIEW.md](docs/validation-study/EXPERT_REVIEW.md). Two earlier rounds in [docs/independent-review/](docs/independent-review/README.md) were not independent enough to count as evidence and are kept only as a record.

Both the local app and the browser lookup flag reported call dates later than filing dates and report missing or invalid dates without changing source values. The browser lookup uses a date-quality index for the original full snapshot; its visual graph remains a sample. The [separate fresh-period evaluation](docs/evaluation/fresh-ftc-2026-11-18.md) does not change the demo snapshot.
