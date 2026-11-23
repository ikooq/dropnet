# Dropnet — Devpost submission draft

**Tagline:** One scam complaint names one phone number. Dropnet finds the number range behind thousands of them, in one Relate graph, and shows its evidence.

**Demo:** https://ikooq.github.io/dropnet/

**Code:** https://github.com/ikooq/dropnet

## Inspiration

Thousands of Americans report unwanted calls to the FTC every day, and each report names one caller ID, so the usual answer is a blocklist of numbers. But 92% of the 248,930 reported numbers in our window were reported exactly once: callers move on before a list catches up. What repeats is the **range** a number comes from, its first six digits, and that only shows when the reports are connected.

## What it does

Dropnet loads 296,273 real FTC Do Not Call complaints into one Relate graph: `Report → Number → Block (six-digit range) → Area code`, plus complaint category and consumer state.

- **Check a number.** The page looks up any reported number in the browser and shows its range as a grid of 10,000 numbers, with the reported ones lit.
- **Watch a range get flagged.** A timeline shows one range flagged on Oct 19, then 323 numbers nobody had reported yet appearing in it.
- **Search by description.** "Someone pretending to be the IRS" finds matching ranges through hybrid search (Relate vector + full-text `SEARCH`, then a graph filter by state).
- **Test a rule first.** The what-if writes candidate range rules in a Relate transaction, counts the complaints they match, then rolls back.
- **Give agents the same context.** An MCP server and a Claude Code hook return a number's evidence with a caution about faked caller IDs before an agent answers.

## What we measured

| Test | Numbers only | Numbers + ranges |
|---|---:|---:|
| **Hold-out:** rules learned before Nov 2, matched against the 103,620 complaints filed after | 4.3% | **14.3%** |
| **Same, calls made after Nov 2** (92,712; filing date ≠ call date) | 3.5% | **12.7%** |
| **Fresh data:** 29,549 complaints filed Nov 13–16, after our snapshot ended | 3.6% | **13.2%** |
| **Fresh data, calls in the new period** (21,834) | 3.3% | **11.8%** |

- **Early warning:** replaying 239,932 complaints day by day with only the previous days' knowledge, a number blocklist knew 2.6% of them, the range rule 11.9%. 23,726 numbers first appeared in a range Dropnet had already flagged.
- **A prediction made before the data existed:** on Nov 23 we froze the rule's output (5,765 geographic ranges, 23,740 repeat numbers) with SHA-256 hashes, the test set and the pass marks, in a public commit. On Dec 8 it is scored, unchanged, on complaints filed after Nov 18 ([protocol](https://github.com/ikooq/dropnet/tree/main/docs/prediction)).
- **Not one lucky split:** ranges led from all 27 start days we tried, by at least 2.6×.
- **A second agency agrees:** 49 of our 50 largest ranges also appear in the FCC's complaint data, against 9% of random ranges.
- **Search:** the right complaint category in 78% of the top 10 results, against 29% for full-text alone.
- **A real agent:** without Dropnet, Claude Code (Haiku) answered "unknown" for 37 of 40 numbers and advised blocking all 14 whose caller ID matched the consumer's area code. With Dropnet's MCP tool, its answers followed the evidence in 39 of 40. This measures agreement with our rules, not ground truth.
- **A blinded human look:** one reviewer who reports a background in suspicious-call analysis and did not help build Dropnet rated 10 of 10 strong ranges and 1 of 10 controls worth investigating.

The price: the geographic rules cover about 28.7 million possible numbers. Dropnet ranks ranges for a person to decide; it never blocks anything.

## How we built it on Relate

- **One file is the product.** `data/ftc.rl` (78 MB) holds 296,273 reports, 248,930 numbers, 96,126 ranges and 1.5 million relationships, compacted with `relate clone --to-snapshot-format parquet`.
- **Cypher does the detection:** ranges, a network of 15 ranges that hit the same area codes on the same days, and the what-if in a rolled-back transaction.
- **Every surface Relate offers:** the embedded Python engine, WebAssembly in the browser, Bolt, the HTTP Query API, MCP, full-text and vector indexes with `SEARCH`, and our own command extension, `relate run dropnet-ftc`, which turns raw FTC files into the same 6,091 ranges in 33 seconds.

## Challenges

- Fairness to people whose numbers are faked shaped the method: ranges use only reports whose caller area code differs from the consumer's.
- Filing date is not call date: 10,766 later-filed complaints described earlier calls, so every test was re-run on call dates.
- An extension writing 5,000 rows per statement exited silently with code 0; the handshake's `maxRowsPerStatement` (1,000) was the limit. We documented it for the Relate team.

## Limitations

Complaints and caller IDs are unverified, and an area-code match only suggests spoofing. A range is a screening signal, not proof of fraud or of a common operator. The data hold no legitimate calls, so a range rule's cost to legitimate callers can't be measured. The windows are short, and the human review is one person on 30 cases.

## Built with

relate, cypher, python, fastapi, webassembly, mcp, claude-code, cytoscape.js, fastembed, ftc-open-data

## AI-assisted development

Built with substantial help from Claude Code (Anthropic), as the rules allow. I chose the problem, the approach and the priorities, directed and reviewed each step, and am responsible for the result. Claude Code wrote much of the code, tests and documentation, ran the evaluations, and built the demo page and video. The video's voice-over is synthetic, generated with ElevenLabs (elevenlabs.io).
