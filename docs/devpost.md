# Dropnet — Devpost submission draft

**Tagline:** One scam complaint names one phone number. Dropnet finds the number range behind thousands of them, in one Relate graph, and shows its evidence.

**Demo:** https://ikooq.github.io/dropnet/

**Code:** https://github.com/ikooq/dropnet

## Inspiration

Every day thousands of Americans report unwanted calls to the FTC. Each report names one caller ID, so the usual answer is a blocklist of numbers. But 92% of the 248,930 reported numbers in our window were reported exactly once: callers move on to the next number long before a list catches up. What repeats is not the number but the **range** it comes from, the first six digits, and that pattern is only visible when the reports are connected.

## What it does

Dropnet loads 296,273 real FTC Do Not Call complaints into one portable Relate graph: `Report → Number → Block (six-digit range) → Area code`, plus complaint category, consumer state and consumer area code.

- **Check a number.** The public page looks up any of the 248,930 reported numbers and 6,091 flagged ranges in the browser, shows the range as a grid of its 10,000 possible numbers with the reported ones lit, and flags source-data problems such as a call date later than the filing date.
- **Find ranges by what people say.** "Someone pretending to be the IRS" or "my car warranty is about to expire" finds the matching ranges through hybrid search (Relate vector + full-text `SEARCH`, rank fusion, then a graph filter by state).
- **Test a rule before anyone uses it.** The what-if writes candidate range rules into a Relate transaction, counts the historical complaints they match and the 10,000 numbers each range covers, then rolls back.
- **Give agents the same context.** An MCP server and a Claude Code hook return the evidence for a number together with a caution about spoofed caller IDs, before an agent answers.

## What we measured

All on public FTC data; each result is reproducible from the repository.

| Test | Numbers only | Numbers + ranges |
|---|---:|---:|
| **Hold-out:** rules learned before Nov 2, matched against the 103,620 complaints filed after | 4.3% | **14.3%** |
| **Same, counting only calls made after Nov 2** (92,712 complaints; filing date ≠ call date) | 3.5% | **12.7%** |
| **Fresh data:** the same rules on 29,549 complaints filed Nov 13–16, after our snapshot ended | 3.6% | **13.2%** |
| **Fresh data, calls made in the new period** (21,834) | 3.3% | **11.8%** |

- **Not one lucky split:** repeated from 27 different start days, ranges matched more complaints every time (at least 2.6×).
- **A second agency agrees:** 49 of our 50 largest ranges also appear in the FCC's separate complaint data for the same weeks, against 9% of randomly drawn reported ranges.
- **Search:** on 14 everyday descriptions, the right complaint category in 78% of the top 10 results, against 29% for full-text alone.
- **A real agent:** we asked Claude Code (Haiku) about 40 reported numbers, with and without Dropnet's MCP tool. Without the graph it answered "unknown" 37 times and still advised blocking the number in all 14 cases whose caller ID matched the consumer's area code. With the tool, its answers followed the evidence in 39 of 40 cases. This measures agreement with Dropnet's own rules, not ground truth.
- **A blinded human look:** one reviewer, who reports a background in risk assessment and suspicious-call analysis and did not help build Dropnet, rated 30 ranges without seeing our labels: all 10 strong ranges were worth investigating, 1 of 10 controls was.

The price is part of the result: the geographic rules cover about 28.7 million possible numbers. Dropnet ranks ranges for a person to decide; it never blocks anything.

## How we built it on Relate

- **One file is the product.** `data/ftc.rl` (78 MB, committed) holds 296,273 reports, 248,930 numbers, 96,126 ranges and 1.5 million relationships, built with batched `UNWIND`/`MERGE` and compacted with `relate clone --to-snapshot-format parquet`.
- **Cypher does the detection:** ranges, the network of 15 ranges that hit the same area codes on the same days, and the what-if inside an explicit transaction that is rolled back.
- **Every surface Relate offers:** the embedded Python engine, WebAssembly in the browser, Bolt with the official neo4j driver, the HTTP Query API, MCP, full-text and vector indexes with `SEARCH`, and our own Relate command extension: `relate run dropnet-ftc --path <FTC files> -d graph` turns raw files into the same 6,091 ranges in 33 seconds.

## Challenges

- Being fair to people whose numbers are faked shaped the method: ranges are built only from reports whose caller area code differs from the consumer's, and every answer carries a caution that a caller ID does not identify the caller.
- Filing date is not call date: 10,766 later-filed complaints described earlier calls, so we re-ran every test on call dates.
- A Relate extension that wrote 5,000 rows per statement exited silently with code 0; the handshake's `maxRowsPerStatement` (1,000) was the limit. We documented it for the Relate team.

## Limitations

Complaints and caller IDs are unverified, and an area-code match only suggests spoofing. A range is a screening signal, not proof of fraud or of a common operator. The data hold no legitimate calls, so the cost of a range rule to legitimate callers cannot be measured. The windows are short (five weeks, then four fresh days). The human review is one person on 30 cases, a sanity check rather than an accuracy estimate.

## Built with

relate, cypher, python, fastapi, webassembly, mcp, claude-code, cytoscape.js, fastembed, ftc-open-data

## AI-assisted development

Built with substantial help from Claude Code (Anthropic), as the rules allow. I chose the problem, the approach and the priorities, directed and reviewed each step, and am responsible for the result. Claude Code wrote much of the code, tests and documentation, ran the evaluations, and built the demo page and video. The video's voice-over is synthetic (Kokoro, a local text-to-speech model).
