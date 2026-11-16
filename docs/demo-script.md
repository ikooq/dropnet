# Demo video script (≈ 2:50, English voice-over)

One idea runs through the whole video: **block the range, not the number — and never blame the person whose number
was faked.** Every figure below comes from `data/ftc/eval.json` or the live page; nothing is staged.

## Before recording

* Live page: `https://ikooq.github.io/dropnet/` (or locally: `python -m http.server 8790 --directory docs`).
  Light theme, browser zoom 125 %, window 1920×1080, other tabs closed, bookmarks bar hidden.
* Open the page once before recording so the 1 MB number list is cached and the grid lights up instantly.
* Pre-record shot 7's terminal (it takes 33 s; speed it up 4× in the editor):
  `relate run dropnet-ftc --path data/ftc/raw -d %TEMP%\ftc-graph` (install once: `python -m dropnet relate-ext`).
* Shot 8: Claude Code open in the repo (the `dropnet hook` is configured in `.claude/settings.json`).

## Shots

| # | time | screen | voice-over (≈ 380 words, read calmly) |
|---|---|---|---|
| 1 | 0:00–0:15 | The page opens on "Did this number call you?" and the grid of 866-771-xxxx. Slow zoom on the grid. | "In five weeks, Americans reported almost three hundred thousand unwanted calls to the FTC. Nine out of ten numbers were reported only once. So a blocklist of numbers is always one step behind." |
| 2 | 0:15–0:38 | Type **866-771-6458**, press Check. The red cells light up; hover a few red cells to show the tooltip. | "Dropnet looks at the range instead. This number was reported a hundred and seventy-one times. Its range — the first six digits — holds ten thousand numbers. A hundred and thirty-eight of them were reported, by people in fifty-two states. That is a rented scam range." |
| 3 | 0:38–0:50 | Click an empty grey cell, e.g. **866-771-5000** → "Never reported, but it sits in a rented scam range". | "This number was never reported. Dropnet still knows where it lives. In our test, more than seventeen thousand later calls came from numbers just like this one." |
| 4 | 0:50–1:08 | Type **201-200-3524** → teal "Probably a faked caller ID". Pause on the sentence about the owner. | "But caller ID is easy to fake. This number was reported only from the victim's own area code — a spoofer making the call look local. Its owner is probably innocent, and Dropnet says so. An AI agent without the graph would have blamed almost four hundred out of a thousand numbers like this." |
| 5 | 1:08–1:33 | Scroll to the evidence bars; let the red bars sit on screen. | "Does it work? We learned rules from the reports before November second and tested them on the hundred thousand that came after. Blocking reported numbers caught four percent. Adding ranges caught fourteen — twenty-two with toll-free ranges. We repeated the test from twenty-seven different start days, and ranges won every time. And the FCC — a different agency — had complaints from forty-nine of our fifty biggest ranges." |
| 6 | 1:33–1:55 | "One operation behind 15 ranges" → What-if → press **Count the calls stopped** (first three ranges are pre-ticked). | "Ranges connect. Fifteen of them called the same area codes, on the same days, with the same scam: one operation, eleven thousand reports. A carrier can ask: what if we had blocked these three? Four thousand three hundred calls stopped — at the price of thirty thousand numbers. We show the price. The carrier decides." |
| 7 | 1:55–2:22 | The range graph, then the Cypher console (click "Ranges reaching the most states"), then the sped-up terminal: `relate run dropnet-ftc …` → "296,273 FTC reports → 6,091 rented number ranges". | "All of this is Relate. The whole graph is one forty-megabyte file in the repo. Here it runs in your browser as WebAssembly — these queries never leave the page. The same file serves Neo4j tools over Bolt and HTTP, an MCP server for AI agents, and a Relate extension: one command turns the raw FTC files into six thousand ranges in thirty-three seconds." |
| 8 | 2:22–2:40 | Claude Code: type *"Should I report 201-200-3524 as a scammer?"* → the answer quotes the evidence and the caution. | "And when an AI agent is asked about a phone number, it gets the evidence and the caution before it answers." |
| 9 | 2:40–2:50 | Back to the hero, empty field. Text on screen: **ikooq.github.io/dropnet**. | "Dropnet. Block the range, not the number — and never blame the person whose number was faked." |

## Where each number comes from

| said in the video | source |
|---|---|
| almost 300,000 reports, five weeks; 9 out of 10 numbers once | 296,273 reports, Oct 9 – Nov 12, 2026; 92.1 % single-report numbers (`summary`) |
| 171 reports; 138 numbers; 52 states | `lookup.txt` (8667716458 171 p), range 866-771 in the demo |
| more than 17,000 later calls from never-reported numbers | `dropnet.new_numbers_caught` = 17,532 |
| almost 400 of 1,000 | `agent_eval.naive_blames_likely_spoofed` = 395 |
| 4 % → 14 % → 22 % | `baseline` 4.3 %, `dropnet_geographic` 14.3 %, `dropnet` 22.0 % |
| 27 start days, won every time | `robustness.rolling_summary`: 27 / 27 |
| 49 of the 50 biggest ranges | `fcc_crosscheck`: 49 / 50 |
| 15 ranges, 11,000 reports | network NET-217863: 15 pools, 11,071 reports |
| 4,300 calls, 30,000 numbers | what-if on 866-771, 217-863, 877-578: 4,339 reports, 3 × 10,000 numbers |
| 40 MB, 33 s, 6,000 ranges | `data/ftc.rl` 39.9 MB; `relate run dropnet-ftc`: 6,091 pools in 33 s |

## Как записать (по-русски)

1. **Запись экрана:** OBS Studio (бесплатно) или `Win + Alt + R` (Xbox Game Bar). 1920×1080, 30 fps.
2. **Голос отдельно.** Запишите текст из колонки voice-over по одному кадру за раз, в тихой комнате, телефон в 20 см
   от рта. Ошибся — повтори только эту фразу. Потом подложите голос под видео в редакторе (CapCut или Clipchamp, оба
   бесплатные).
3. **Темп:** около 140 слов в минуту. Если не укладываетесь в 3 минуты, вырежьте кадр 8 — он необязательный.
4. **Субтитры:** CapCut делает их автоматически. Судьи часто смотрят без звука — субтитры обязательны.
5. **Загрузка:** YouTube, доступ «по ссылке» (Unlisted), ссылку вставить в Devpost в поле Video.
