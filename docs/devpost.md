# Dropnet — Devpost submission draft

**Tagline:** Connect individual unwanted-call complaints to range-level patterns, with evidence and uncertainty, in a portable Relate graph.

**Demo:** https://ikooq.github.io/dropnet/

**Code:** https://github.com/ikooq/dropnet

## The problem

An analyst may see one complaint about one caller ID and miss a concentration of complaints involving other numbers in the same range. At the same time, caller IDs can be spoofed, so a report does not identify the person who placed a call.

## What Dropnet does

Dropnet puts 296,273 FTC Do Not Call complaints into a portable graph. An analyst can look up a number, explore its range and related reports, and model how a proposed range rule would match historical complaints. A browser demo runs a sample graph in Relate WASM; the full local application opens the saved database. The same context is accessible to agents through MCP.

An area-code match is a possible indicator of spoofing, not proof. The graph does not establish who made a call, who controls a range, or that related ranges are one operation. Dropnet does not block calls or determine whether a caller is guilty.

## A two-minute investigation

Check 833-766-1884 in the live demo. Its caller ID appears in 1,202 complaints in the loaded window. The graph connects the number to its six-digit prefix and other reported numbers, consumer states and complaint categories. Select a range and run the what-if counter to see historical matches alongside the potential scope of a rule. A report is a lead, not a verified identification, and the prefix alone does not establish a shared operator.

Relate is central to this workflow: the same portable graph supports relationship traversal, transactional what-if queries and agent access, while the browser demonstration runs an inspectable subset with WebAssembly.

## What we measured

Rules derived from complaints filed before 2026-11-02 were matched against 103,620 later-filed complaints. A baseline using numbers previously reported at least twice matched 4.3%; adding 2,872 geographic ranges matched 14.3%. These are historical complaint matches, not a measure of all calls or fraud prevented. The range rules plus number rules cover approximately 28.73 million possible numbers; the dataset cannot measure the impact on legitimate traffic.

Filing date is not call date: 10,766 later-filed complaints concerned earlier calls and 142 have an event date after filing. Among 92,712 later-filed complaints with valid call dates on or after the split, the baseline matched 3.49% and geographic ranges 12.67%. This retrospective subset is not representative of all calls. Run `python -m dropnet.ftc.time_audit` to reproduce it.

A historical agent experiment compares the agent's answers to labels and advice produced by Dropnet's own rules. It measures agreement with those rules, not independently verified spoofing or the correctness of blocking decisions. Saved historical runs predate our revised cautious advice.

## How Relate helps

- `Report → Number → Block` joins individual complaints to the range-level pattern; subject, state and consumer area links give context.
- Relate's embedded Python engine, persistent single-file store and Cypher support the local investigation.
- The browser demo uses Relate WASM; the full dataset remains in `data/ftc.rl`.
- What-if creates hypothetical rule nodes inside a transaction and rolls back. Case export creates a portable Relate file.
- Full-text and optional vector search, MCP tools and a Claude Code hook make graph context available to agents.

## Try it

Open the demo above and check `833-766-1884`; explore the range, graph and what-if. For the full graph, clone the repository, create a Python environment, run `pip install -e .` and `python -m dropnet serve`. See the README for all commands and limitations.

## Sources and tools

FTC Do Not Call complaints; FCC consumer complaints for a separate comparison; synthetic Russian-language complaints are confined to a separate demonstration. Built with Python, Relate, FastAPI, JavaScript and WebAssembly. Claude Code and other AI coding tools assisted development and documentation; the team reviewed the output and is responsible for it. Relate 1.0.1 is used as an embedded database, through Cypher, WASM, MCP, and other interfaces documented in the repository.

## Limitations

Complaints and caller IDs are unverified; area-code matches are only indicators. Some consumer area codes are missing and treated as non-matches by the current pool heuristic. Co-occurrence links use complaint filing day, not necessarily call day. The sample window is short and there is no denominator of legitimate calls. The local demo server is intended for a trusted environment and is not suitable for sensitive real complaints.


## Human review and data quality

Two exploratory 30-case reviews examined whether complaint summaries warranted follow-up. The follow-up used different number ranges from the same historical snapshot; prior answers were available and the review was not fully blinded. These judgments do not establish fraud or measure detection accuracy. Methods and limitations are documented in the repository.

The local app and browser lookup flag reported call dates later than filing dates and preserve the original source values. The browser graph remains a sample; its lookup and date-quality index cover the original snapshot.

## Fresh-period check

On 29,549 complaints filed November 13–16 after the original snapshot, the same pre-November 2 rules matched 3.57% for the repeated-number baseline and 13.18% with geographic ranges. The event-date subset (21,834 reports) produced 3.31% and 11.81%. These are complaint matches, not fraud accuracy or prevented calls; legitimate-call impact remains unknown. The separate reproducible evaluation does not change the demo dataset.

A further 30-range review was performed by a reviewer with reported experience in complaint analysis who, according to the supplied account, did not see the group labels or previous answers. They recommended follow-up for 17 cases and were unsure about 6. This is one label-blinded review, not verified fraud ground truth or proof of improved investigative efficiency.
