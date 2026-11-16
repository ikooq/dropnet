# Dropnet

**Scam reports arrive one at a time. The scams don't.** Dropnet puts 296,273 real phone-scam complaints into an
embedded **Relate** graph and finds the number pools behind them — the rented number ranges a blocklist of single
numbers can never keep up with — while refusing to blame the innocent people whose numbers get spoofed.

**Try it without installing anything:** open `docs/index.html` via GitHub Pages (Settings → Pages → branch, `/docs`).
Relate runs in your browser as WebAssembly and loads the 200 biggest real pools in about a second.

---

## Use case

Every day ~13,000 Americans report unwanted calls to the FTC. Each report names one caller number. Analysts at
carriers, regulators and anti-fraud teams block numbers — and lose, because:

* **92.1 % of the 248,930 reported numbers were reported exactly once.** Scammers rotate numbers faster than
  blocklists grow.
* **36.8 % of reports come from a number faked to carry the victim's own area code** ("neighbor spoofing"; 82 % for
  medical robocalls). Those numbers belong to innocent people.

The relationship that matters is **Number → Block (NPA-NXX, the first six digits)**. Rented number ranges show up as
*pools*: many different reported numbers in one block, the same scam types, victims in dozens of states. A pool is
visible only in the graph — never in a single report.

| relationship | why it matters |
|---|---|
| `(Report)-[:FROM_NUMBER]->(Number)-[:IN_BLOCK]->(Block)` | one-off numbers that share a rented range |
| `(Report)-[:ABOUT]->(Subject)`, `-[:VICTIM_IN]->(State)`, `-[:VICTIM_AREA]->(AreaCode)` | scam type, reach, and spoofing (caller area = victim area) |
| `(FtcCampaign)-[:USES_BLOCK]->(Block)` | a pool: the unit worth blocking |
| `(Rule)-[:BLOCKS]->(Block or Number)` | what-if rules, written in a transaction and rolled back |

## Results on real data (temporal hold-out)

Rules are learned from reports filed **before 2026-11-02** (192,653) and scored on the **103,620 reports filed after**
— numbers the rules could not have seen.

| rule set | rules | later reports caught |
|---|---:|---:|
| block every number ever reported | 163,606 | 6.2 % |
| classic blocklist: numbers with ≥ 2 reports | 11,968 | 4.3 % |
| **Dropnet: those numbers + 3,681 pool blocks** | 15,649 | **22.0 %** |

**5× the coverage** of the blocklist with a comparable number of rules; **17,532** of Dropnet's catches came from numbers
nobody had reported before. Pools are built from *non-spoofed* reports only, so Dropnet never recommends blocking the
local ranges spoofers hide in (the 1,358 spoofed calls it still catches sit inside genuine pools).
Reproduce: `python -m dropnet ftc-eval`.

## How it uses Relate

- **Mode: single file.** `data/ftc.rl` (40 MB, committed) holds the whole graph: 296,273 reports, 248,930 numbers,
  96,126 blocks, 1,531,971 relationships, 6,146 campaigns (6,091 pools, 55 repeat numbers). A second file, `data/dropnet.rl`, holds the free-text module.
- **Why this mode:** the investigation is one portable artifact — judges and colleagues open exactly the graph we built,
  and a single campaign can be handed over as its *own* `.rl` file (`Download case`). Built in a directory store,
  then compacted with `relate clone --to-snapshot-format parquet` (150 MB → 40 MB) so it fits a git repo.
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
| vector index + `db.index.vector.queryNodes`, `shortestPath`, variable-length money trails | free-text module |
| **MCP**: our server + Relate's native `relate serve --mcp stdio --read-only` | `.mcp.json` |

## Setup and run

Python **3.10+** (tested on 3.14, Windows 11). No API key, no database server.

```bash
git clone <this repo> && cd dropnet
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
pip install -e ".[dev]" && pytest          # 184 tests
```

### With an AI agent

Start Claude Code **from the activated venv** in this folder:

* **MCP** (`.mcp.json`): `assess_number`, `ftc_campaigns`, `whatif_block`, `ftc_summary` (+ the free-text tools) via
  `dropnet mcp`; Relate's own MCP server on the snapshot via `relate-native`.
* **Hook** (`.claude/settings.json`, `UserPromptSubmit`): whenever a prompt mentions a phone number, the agent receives
  the graph's evidence about it *and* the spoofing caution before it answers (0.75 s). Ask *"Should we block
  833-766-1884?"* — the agent learns it sits in a 27-number pool reported 1,202 times in 50 states, and is told not to
  call the owner of a one-off local number a scammer.

## Where the data lives

| path | what |
|---|---|
| `data/ftc.rl` | **the Relate store** — real FTC reports (single file, committed) |
| `data/ftc/raw/*.csv.gz` | the 25 daily FTC files as downloaded (US public data) |
| `data/ftc/eval.json` | the hold-out result |
| `docs/data/graph.json` | the slice the browser demo loads into Relate WASM |
| `data/dropnet.rl`, `data/raw/` | second module: free-text complaints (synthetic, Russian) |
| `data/live/` | working copies the app writes to (git-ignored) |

## Second module: free-text complaints, any language

Real reports name a number; many victims write a story instead. The second module turns free text (demo: synthetic
Russian complaints) into a graph of phones, cards, IBANs, phishing domains, scammer aliases and bank transfers, links
complaints through shared identifiers and **money trails up to three transfers deep**, attaches victims who kept no
numbers by script similarity (Relate vector index), and writes case files with an evidence path and the victim's own
quote for every link. Tabs *New complaint*, *Campaigns*, *Inbox* and *Query the graph*.

## What we learned about Relate 1.0.1 (shared for the team)

* `UNWIND $list AS x MATCH (:Number {number: x})` did not use the range index on a 249k-node label (21 s for 60
  lookups); anchoring on an indexed node first took 0.03 s.
* In the WASM build a per-row property `MATCH` costs ~0.5 ms and `MERGE` inside `FOREACH` ~0.7 ms; collecting nodes
  into lists once and addressing them as `xs[i]` loaded 34k relationships in ~1 s instead of 13–19 s.
* `relate.Record` serialises only its result columns, so keys added in Python vanish from JSON — copy to `dict`.
* A writable open of a `.rl` file checkpoints (rewrites) it; open snapshots with `--read-only` / `read_only=True`.

## Limits and honest notes

* FTC numbers are numbers people *reported*, not proven offenders; caller ID is easily spoofed. The UI, the MCP tools
  and the hook all carry that caution, and spoofed local ranges are never proposed for blocking.
* A pool block covers up to 10,000 numbers; blocking one is a carrier decision with collateral risk. The what-if shows
  the reports a rule would have stopped, not the legitimate calls it might block.
* The hold-out spans 35 days of reports; longer windows may shift the numbers.

License: MIT. Built for the Relate by Neo4j hackathon (2026). FTC Do Not Call complaint data is US public data.
