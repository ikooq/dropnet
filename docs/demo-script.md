# Demo video script (≈ 1:45, English voice-over)

Setup before recording: `python -m dropnet serve --reset`, browser at `http://127.0.0.1:8000`, a Claude Code window
opened in the repo with the `dropnet` MCP server connected. Close other tabs. 1440×900.

| time | screen | voice-over |
|---|---|---|
| 0:00–0:12 | Title card: "57 % of fraud in Kazakhstan is phone & internet fraud" → three complaint cards from Pavlodar, Almaty, Astana | "Fraud complaints arrive one at a time, in different cities. Each looks like a small, isolated case." |
| 0:12–0:20 | Dropnet header: 250 complaints · 7 campaigns · linked damage | "Dropnet puts every phone, card, link and money transfer from those complaints into one embedded Relate graph — a single file in the repo." |
| 0:20–0:45 | **New complaint** → click *Known mule card* → **Link it** → result card | "A new complaint from Pavlodar. In under a second: it's part of a campaign of 45 complaints across three regions — through this mule card. And here is the evidence: the victims' own words." |
| 0:45–0:55 | Click *Two gangs, one victim* → **Link it** → BRIDGE | "Sometimes one victim connects two campaigns — a hint they're one gang." |
| 0:55–1:15 | **Campaigns** → CAMP-0026 graph; click the red cash-out card; click an edge → quote | "This is the money tree: four mule cards, two transit cards, one cash-out. Freeze this one and the whole chain stops. Every link points back to a sentence a victim wrote." |
| 1:15–1:30 | Claude Code: "Who is behind CMP-0160 and what should we freeze first?" → answer with path + quote | "An AI agent can investigate the same graph through MCP — and it has to cite the path and the quote." |
| 1:30–1:40 | Terminal: `python -m dropnet eval --ablations` table | "Remove the money trails, the script vectors or the hub filter, and the results break — every relationship carries part of the answer." |
| 1:40–1:45 | README: `pip install -e . && python -m dropnet serve` | "Clone, install, serve. No server, no API key. Context, connected." |

Shots to grab for Devpost: the result card (attached), the campaign money tree, the case file HTML, the eval table.
