# Dropnet

Dropnet helps analysts investigate concentrations of unwanted-call complaints by phone-number range. It connects FTC reports, caller IDs, number ranges and NANPA assignments in an embedded Relate graph.

**The 365-826 case.** Dropnet flagged this range on October 19. Another **323 distinct numbers** from that range appeared in FTC complaints for the first time after the flag. Explore the filing timeline and then use the local graph to trace US ranges through their numbering assignments. Caller IDs can be spoofed, and a numbering assignment identifies who holds a numbering resource.

[Open the browser demo](https://ikooq.github.io/dropnet/#early) · [Evidence, methods and limits](docs/EVIDENCE.md)

## Run locally

Use Python 3.10 or later. From a checkout of this repository, run:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
python -m dropnet serve
```

Open [localhost:8000](http://127.0.0.1:8000). Select a range in the case graph and follow its OCN to other flagged ranges. Run **Operators by flagged ranges** under **Query the graph**. You can also try a what-if or download the complaint evidence as a standalone Relate file.

## Relate

The checked-in `data/ftc.rl` holds the full graph in a single file. The embedded engine walks from a complaint to its number, range, rate center and carrier. Where a US thousands-block has an assignment, the graph also records that assignment separately. The browser uses Relate WebAssembly with a smaller graph. The local what-if runs in a transaction and rolls back.

Built for the Relate by Neo4j Hackathon. MIT-licensed code. AI-assisted development and source details are documented in [EVIDENCE.md](docs/EVIDENCE.md).
