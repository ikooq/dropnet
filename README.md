# Dropnet

**One complaint is a single data point. Dropnet connects reported numbers, ranges and complaint patterns for an analyst to investigate.**

[Open the browser demo](https://ikooq.github.io/dropnet/) · [Demo script](docs/demo-script.md) · [Submission draft](docs/devpost.md)

Dropnet explores 296,273 FTC Do Not Call complaints in a portable Relate graph. Check a reported US number, follow it to its six-digit range, explore other reports and test hypothetical rules. The browser demo loads a graph slice into Relate WASM; the local app opens the full snapshot. **Complaints are unverified. Caller ID may be spoofed; no result identifies the caller or proves wrongdoing.**

## Try it in a minute

Open the [demo](https://ikooq.github.io/dropnet/), enter `833-766-1884`, inspect the number and range, then explore the graph and what-if panel. Number lookup covers the loaded FTC window, not every complaint ever filed. The demo downloads its data and code from the web; lookup itself runs locally in your browser.

To run the full application locally, see [Setup and run](#setup-and-run). No API key is required for the default experience.

## The graph and its evidence

`Report → Number → Block` connects a complaint to its reported caller ID and six-digit NPA-NXX range. Reports also connect to a subject and consumer area code and state. A pool is a range with at least five distinct numbers in reports that do **not** have a matching consumer area code. This is a screening rule, not proof that a range is rented, fraudulent, or controlled by one group. A missing consumer area code is treated as a non-match by the current implementation (five reports in this dataset).

A reported caller area matching the consumer area is a possible indicator of neighbor spoofing, **not proof of spoofing**. A mismatch does not rule spoofing out. Caller identity and the number owner's conduct are unknown. Pool-network links reflect shared consumer area codes, complaint categories and **filing days**; they do not establish a common operator or calls made on the same day.

## What the holdout measures

Rules were learned from 192,653 complaints filed before 2026-11-02 and matched against 103,620 complaints filed afterwards. The baseline uses numbers reported at least twice; geographic pools add 2,872 six-digit range rules.

| Rule set | Share of later-filed complaints matching a rule |
|---|---:|
| Previously reported numbers, at least twice | 4.3% |
| Those numbers plus geographic pool ranges | 14.3% |
| Those numbers plus all pool ranges including toll-free | 22.0% |

These are **retrospective matches against complaints**, not confirmed fraud, blocked calls, recall across all calls, or a measure of harm prevented. A range contains up to 10,000 possible numbers; the geographic rules plus number rules cover approximately 28.73 million possible numbers after accounting for overlap. The dataset does not contain legitimate traffic, so false blocking cannot be measured. Toll-free ranges may be shared by legitimate businesses. Dropnet does not apply blocking rules.

Filing date is not necessarily call date. In the test set, **10,766** complaints concerned calls before the split; another **142** have an event date after filing. Of the remaining **92,712** complaints whose call date was on or after the split and no later than filing, 3.49% match the baseline and 12.67% match the geographic rules. This is a retrospective subset of complaints filed during the window, not a representative sample of all calls. Reproduce the audit with `python -m dropnet.ftc.time_audit`; saved output is in `data/ftc/time_audit.json`.

A second agency's complaints and rolling splits are reported in `data/ftc/eval.json`. They add context but do not establish ownership or a common operator. The previous 40-number agent experiment used labels and recommended actions derived from Dropnet's own rules, rather than independent truth. Its scores describe agreement with those historical rules; they do **not** validate spoofing or safe blocking decisions. The older saved result predates the current cautious advice.

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

Independent human review: see [the prepared review protocol and blinded cases](docs/independent-review/README.md). One human review of the original cards and its limitations are documented in the review pack.

Both the local app and the browser lookup flag reported call dates later than filing dates and report missing or invalid dates without changing source values. The browser lookup uses a date-quality index for the original full snapshot; its visual graph remains a sample. The [separate fresh-period evaluation](docs/evaluation/fresh-ftc-2026-11-18.md) does not change the demo snapshot.
