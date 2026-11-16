# Dropnet

**Scattered fraud complaints → one connected case.** Dropnet reads victims' complaints (free Russian text),
puts every phone, card, IBAN, phishing link, scammer alias and money transfer into an embedded **Relate** graph,
and shows an investigator which complaints are one gang — with the path and the victim's own words as evidence.

> ⚠️ **All data in this repository is synthetic.** Phones use the fictional range `+7 799 0xx xx xx`, cards the test
> BIN `400000` (stored masked), IBANs start with `KZ00`, domains end in `.example` / `.test`. No real people.

---

## Use case

In Kazakhstan, internet and phone fraud is **57 % of all registered fraud** (13.1k cases in Jan–Jul 2026, per the
Committee on Legal Statistics as reported by 24.kz). The schemes are well known — "bank security calls", "move your
savings to a safe account", phishing "loan status" SMS, fake police threats, marketplace prepayments, money mules
recruited at ATMs.

The problem is that **complaints arrive one at a time, in different cities, to different officers**. A pensioner in
Pavlodar, a student in Almaty and a shop owner in Astana each file a report. Nobody sees that all three paid the
same mule card, that the "bank" called them from the same pool of SIM cards, or that the money from four different
cards ends up on one cash-out card two transfers later. **The fraud is only visible in the relationships.**

Dropnet is a tool for an **anti-fraud analyst or investigator**:

* paste a new complaint → in under a second see *"part of CAMP-0020: 45 complaints, 3 regions, 64.5M KZT — via card
  `4000 00** **** 7763`"* with the evidence path and quotes;
* open a campaign → see the money tree (victims → mule cards → transit → cash-out) and click any link to read the
  sentence it came from;
* export a **case file** (Markdown/HTML) with accounts to freeze, phones to subpoena, domains to take down;
* let an **AI agent** (Claude Code, any MCP client) investigate the same graph through MCP.

Relationships that matter:

| relationship | why it matters |
|---|---|
| `Complaint -[:PAID_TO]-> Card/Account` | two victims paying one account = one gang (a *mule*) |
| `Card -[:FORWARDED_TO]-> Card` (1–3 hops) | different mule cards that drain into one *cash-out* card |
| `Complaint -[:CONTACTED_BY]-> Phone` | SIM pools re-used across victims and regions |
| `Complaint -[:VISITED]-> Url -[:ON_DOMAIN]-> Domain` | one phishing site behind many "loan status" SMS |
| `Complaint -[:MENTIONS_PERSONA]-> Persona` + same tactic | gangs re-use aliases ("Erlan from financial monitoring") |
| `Complaint -[:SIMILAR_SCRIPT {score}]-> Complaint` | the same script retold by victims who kept no numbers |
| `Extraction -[:FROM]-> Complaint`, `-[:FOUND]-> entity` | **provenance**: every link points back to a quote |

A **hub filter** catches the classic false positive: a legitimate number (a marketplace's support line) mentioned in
complaints of many different tactics and regions is marked `hub = true` and never used as evidence. Without it,
everything collapses into one giant "campaign" (see results: F1 drops to 0.34).

## How it uses Relate

- **Mode: single file** — `data/dropnet.rl`.
- **Why this mode:** the whole investigation is one portable artifact. Judges (or a colleague) clone the repo and open
  the same graph we built — no server, no import step. A single file is also how an analyst would hand a case to
  another team. The web app never writes to it: it works on a copy in `data/live/` (git-ignored) so the committed
  snapshot and the evaluation stay reproducible.
- **What the graph models:** 250 complaints, their extracted identifiers (149 phones, 67 cards, 44 accounts, 35 URLs on
  9 domains, aliases), bank transfers between cards, tactics, regions, banks, 7 detected campaigns, 1,033 provenance
  nodes and 1,230 script-similarity edges.

Relate features we rely on:

| feature | where |
|---|---|
| embedded Python engine (`relate-db`), no server | `dropnet/store.py` |
| single-file store + read-only opens for analysis | `data/dropnet.rl`, `store.open_store(read_only=True)` |
| `UNWIND` + `MERGE` batch loading | `dropnet/load.py` |
| variable-length paths `[:FORWARDED_TO*0..3]` (money trails) | `dropnet/link.py`, `dropnet/tools.py` |
| `shortestPath` with node predicates (evidence path that avoids hubs) | `tools.explain_link` |
| **vector index** + `db.index.vector.queryNodes` inside a `MATCH` (hybrid vector + graph) | `link.add_similarity`, `ingest._add_similar` |
| Relate's error classification for safe retries / user-facing errors | web API |
| **MCP**: Relate's native `relate serve --mcp stdio --read-only` *and* our own MCP server | `.mcp.json` |

## Setup and run

Prerequisites: **Python 3.10+** (developed and tested on Python 3.14, Windows 11). No API key, no database server,
no model download.

```bash
git clone <this repo> && cd dropnet
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e .
python -m dropnet serve          # → http://127.0.0.1:8000
```

That's it: the graph is already in the repo. In the UI, click a sample on **New complaint** (e.g. *Known mule card*)
and press **Link it**.

Other commands:

```bash
python -m dropnet investigate CMP-0160        # which campaign is behind this complaint + case file
python -m dropnet case CAMP-0026 --html --out case.html
python -m dropnet ingest "Звонили с 8 799 012 34 56 ... перевела на карту 4000 00** **** 7763" --region Pavlodar
python -m dropnet build                       # regenerate data and rebuild data/dropnet.rl (deterministic, ~2 s)
python -m dropnet eval --hard --ablations     # linking quality on held-out seeds (see Results)
python -m dropnet serve --reset               # start the UI from a fresh copy of the snapshot (do this after `build` or `git pull`)
pip install -e ".[dev]" && pytest             # 146 tests
```

### Investigate with an AI agent (MCP)

`.mcp.json` registers two MCP servers for Claude Code (or any MCP host) opened in this folder. **Start Claude Code
from a terminal where the venv is activated**, so the `dropnet` command (installed by `pip install -e .`) is on PATH.

* **`dropnet`** — `dropnet mcp`: `find_campaign`, `explain_link`, `top_mules`, `similar_scripts`,
  `build_case`, `read_cypher` (read-only), `get_schema`, `list_campaigns`. If `dropnet serve` is running it proxies to
  it, so the agent sees complaints you ingested a second ago; otherwise it opens the snapshot read-only.
* **`relate-native`** — Relate's own MCP server on the snapshot (`read_cypher`, `get_schema`); needs the
  [Relate CLI](https://relatedb.ai/docs/get-started/install).

The skill `.claude/skills/dropnet-investigator/SKILL.md` teaches the agent the schema, six Cypher recipes and the rule
*"every claim cites node ids, a path and a victim quote"*. Try: *"Who is behind CMP-0160 and what should we freeze
first?"*

> Using the Relate CLI directly on the snapshot? Always pass `--read-only`, e.g.
> `relate query "MATCH (k:Campaign) RETURN k.id, k.size" --database data/dropnet.rl --read-only` — a writable open
> checkpoints (rewrites) the file.

## Where the data lives

| path | what |
|---|---|
| `data/dropnet.rl` | **the Relate store** (single file, committed) |
| `data/raw/complaints.jsonl` | the 250 synthetic complaints (Russian text + English gloss) |
| `data/raw/bank_transfers.jsonl` | synthetic card-to-card transfers |
| `data/raw/ground_truth.json` | which complaints the generator planted in which campaign (used only by `eval`) |
| `data/live/dropnet.rl` | working copy the web app writes to (git-ignored, created on `serve`) |

## Results

Pairwise precision / recall / F1 of "these two complaints are the same campaign" against the generator's ground truth.
Thresholds were tuned on seed 1 only; the numbers below are on **held-out seeds 2–5** (250 complaints each).
The *hard* variant adds typos, paraphrases, an extra script-only campaign and victims who lost the number or card.

| variant | mean F1 (seeds 2–5) | what it shows |
|---|---:|---|
| full system | **1.000** | |
| hard data | **1.000** | complaints with no identifiers are attached by script similarity |
| without vectors | 0.956 | the script-only campaign is missed |
| without money trails (`FORWARDED_TO`) | 0.910 | campaigns whose victims paid *different* mule cards fall apart |
| without hub filter | 0.335 | one legitimate support number glues unrelated gangs together |

Synthetic data is easier than reality — the value of the table is the ablations: each relationship type carries
part of the answer, and removing any one of them visibly breaks the result.

## How it works

```
complaints.jsonl ─► extract (regex + lexicon + alias gazetteer, with character spans)
                 ─► embed (hashed char 3-5-grams, 256-d, no model download)
                 ─► load into Relate (UNWIND/MERGE)            ─► data/dropnet.rl
                 ─► link: strong pairs (shared phone / domain / payee within 3 FORWARDED_TO hops / alias+tactic)
                          minus hubs, union-find → campaigns;
                          loose complaints attach by ≥2 script votes (≥0.80); script-only campaigns need ≥0.90
                 ─► campaigns get stable ids (CAMP- + earliest complaint), card roles (mule / cashout)

web / MCP / CLI ─► one read-only query layer (dropnet/tools.py) ─► case files with evidence paths and quotes
ingest          ─► incremental: attached | bridge (links two campaigns) | new_campaign | unlinked (+ closest scripts)
```

## Project layout

```
dropnet/synth/      synthetic data generator (deterministic, seeded)
dropnet/extract/    rule-based extraction + normalizers
dropnet/embed.py    script vectors
dropnet/load.py     write to Relate
dropnet/link.py     campaigns, hubs, card roles
dropnet/tools.py    read-only query layer (+ guarded read_cypher)
dropnet/report.py   case files
dropnet/ingest.py   live ingest
dropnet/web/        FastAPI + single-page UI (cytoscape.js)
dropnet/mcp_server.py
tests/              146 tests (pytest)
docs/               design, implementation plan, demo script
```

## Limits and honest notes

* Synthetic data only; the generator was written by the same people as the linker, so real complaints would be
  messier (that is what the hard variant and the ablations are for).
* Extraction is rule-based on purpose (works offline, explainable spans). An optional LLM extractor is a natural next
  step.
* The Relate store has one writer per file; the web app owns the live copy and MCP reads through its API.
* Cards are keyed by their masked form (`4000 00** **** 1234`), so two different cards with the same first six and
  last four digits would merge — acceptable for a demo, a real deployment would key on a bank-side token.
* Card numbers are masked before anything is stored (`400000******1234`); `read_cypher` is guarded against writes
  (comments, backticks and string literals are normalised before the check).

License: MIT. Built for the Relate by Neo4j hackathon (2026).
