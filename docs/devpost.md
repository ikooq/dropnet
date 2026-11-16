# Devpost submission draft — Dropnet

**Tagline (≤ 200 chars):** 296,273 real phone-scam reports in one Relate file. Dropnet finds the number pools behind
them — 3× what a blocklist catches — and never blames people whose numbers were spoofed.

## Inspiration
Every day about 13,000 people report unwanted calls to the US Federal Trade Commission. Each report names one number,
so the standard defence is a blocklist of numbers. We loaded 35 days of those reports and found why it fails: 92 % of
the 248,930 reported numbers appear exactly once. Scammers rotate numbers faster than a list can grow. And 37 % of the
calls came from a number faked to carry the victim's own area code — numbers that belong to innocent neighbours.

## What it does
Dropnet turns the reports into a graph — report → number → NPA-NXX block → area code, plus scam type, victim state and
spoofing — and looks for *pools*: rented number ranges where many different reported numbers share a block, the same
scam types and victims in dozens of states. A pool is invisible in any single report and obvious in the graph.

- **Real results, measured honestly.** Rules learned from reports before 2 Nov, scored on the 103,620 reports that came
  after: a blocklist of every number with ≥ 2 reports (11,968 rules) would have caught 4.3 %; blocking every number
  ever reported (163,606 rules) 6.2 %; those numbers plus 2,872 geographic pool ranges 14.3 % (22.0 % with toll-free
  ranges). 17,532 catches came from numbers nobody had reported before. We show the price too: a range rule silences
  10,000 numbers, so Dropnet ranks ranges for a carrier's decision rather than blocking anything.
- **Pools are signal, not noise.** Control: the same number of *random* reported blocks catches 4.4 % of later reports;
  the pool blocks catch 20.3 % — a 4.7× lift. 83 % of pool rules caught at least one later report.
- **Measured for agents.** On 1,000 random reported numbers, an agent without the graph that treats every reported
  number as a scammer would blame 395 (39.5 %) likely-spoofed numbers whose owners are probably innocent, and dismiss
  246 (24.6 %) once-reported numbers that belong to an active pool. With Dropnet's hook / MCP tool it gets the right
  verdict for each, with the caution.
- **One operation, fifteen ranges.** Linking pools by multi-hop paths (same victim area code, same day, same scam)
  finds one network of 15 number ranges behind 11,071 reports.
- **Spoofing-aware by design.** Pools are built only from non-spoofed reports, so Dropnet never proposes blocking the
  local ranges spoofers hide in. `assess_number` labels a one-off local number "likely spoofed" and says so.
- **What-if in a transaction.** Pick pools, ask what blocking them on day one would have stopped: Dropnet writes the
  rules into the graph inside a Relate transaction, counts by traversal (0.07 s on the full graph), and rolls back.
- **A case in one file.** Any campaign exports to its own single-file Relate store — hand it over, archive it, delete it.
- **No-install demo.** The docs/ page runs Relate compiled to WebAssembly and loads the 200 biggest pools (7,872 nodes,
  34,070 relationships) in about a second; Cypher queries run locally in ~4 ms.
- **Agents that are careful.** MCP tools plus a Claude Code hook: whenever a prompt mentions a phone number, the agent
  gets the graph's evidence *and* the caution that caller ID is easily spoofed — before it answers.
- **Second module: free text, any language.** Victims' stories (demo: Russian) become phones, cards, IBANs, phishing
  domains, aliases and money trails; every link in a case file carries a path and the victim's own words.

## How we built it
Python + `relate-db` (embedded). FTC daily CSVs → parse → batched `UNWIND`/`MERGE` into a directory store with range
indexes (296k reports in ~2 min) → campaign detection as Cypher aggregations → `relate clone --to-snapshot-format
parquet` compacts it to a 40 MB single file committed to the repo. FastAPI + cytoscape.js UI, MCP server (official
SDK), a Claude Code hook, and a static page with `@relate/relate-wasm`. 191 tests.

## Challenges
- The graph had to fit in git: slimmed node properties and Parquet compaction took it from 150 MB to 40 MB.
- A multi-hop pattern started from an `UNWIND`-bound key took 21 s on the 249k-number graph; starting from an indexed
  anchor took 0.03 s. In WASM, per-row lookups cost ~0.5 ms, so the demo addresses nodes by list index — 13 s → 1 s.
- Being fair to spoofing victims shaped the method: no block rules from spoofed reports, cautions everywhere.

## What we learned
Blocking is a graph problem, not a list problem — and the graph also tells you whom *not* to blame.

## What's next
Longer windows, STIR/SHAKEN attestation data where available, and the free-text module on real complaint corpora.

## Built with
relate, cypher, python, fastapi, webassembly, mcp, claude-code, cytoscape.js, ftc-open-data
