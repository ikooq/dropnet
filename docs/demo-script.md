# Dropnet: demo video script (1:50)

You record this yourself: your screen, your voice, your editing. The contest rules require the video to be the
entrant's own work. The voice-over below is about 220 words, so it fits in under two minutes at a calm pace.

## Before you record

- Run `python -m dropnet serve` and wait for "Dropnet is ready". Open `http://127.0.0.1:8000` once, so the first page
  is already loaded when you start recording.
- Open the browser demo (`https://ikooq.github.io/dropnet/`, or `python -m http.server` inside `docs/` before the
  merge) in a second tab.
- In a terminal, in the repository folder with the virtual environment active (or after the `claude mcp add` step in
  the README), start `claude` once and allow the
  `dropnet` MCP server. Close and reopen it so the recording starts clean.
- Screen at 1920×1080, browser zoom at 110%, notifications off. A free recorder is enough (OBS Studio, or Win+Alt+R
  on Windows, or Shift+Cmd+5 on macOS).
- Check every number on screen against `data/ftc/eval.json` before you publish.

## Shots and voice-over

| Time | Shot (what you click) | Voice-over |
|---|---|---|
| 0:00–0:12 | Browser demo, top of the page. | "People reported almost three hundred thousand unwanted calls to the FTC in five weeks. Ninety-two percent of the numbers were reported only once. A list of numbers is always one step behind." |
| 0:12–0:30 | Type `771-999-0716`, press **Check**. The 10,000-number grid lights up. | "So Dropnet looks at the range: the first six digits. This number was reported three times. Its range has fifty-three reported numbers. That is the pattern a list of single numbers never sees." |
| 0:30–0:52 | Scroll to **The range was known before its numbers were**. Point at the flag day, then the red bars. | "Range 365-826 was flagged on October nineteenth. In the next three weeks, three hundred twenty-three new numbers from it showed up in complaints. Nobody had reported them yet, but the range was already flagged. On later complaints, numbers alone matched 4.3 percent. Adding ranges: 14.3." |
| 0:52–1:18 | Local app. Point at the "per 100" column in **Who holds flagged ranges**. Then check `771-999-0716`: show the two cards (prefix holder FRACTEL, 1,000-block assignee ONVOY), click **Open range 771-999 in graph**, then one range under **Flagged ranges sharing OCN 965H**. | "Here the graph matters. Relate links each range to the carrier that holds it in the national numbering records. A few small carriers hold over twenty flagged ranges per hundred; the big wireless carriers, about one. From one number, the graph walks to its holder, and on to other flagged ranges that holder has." |
| 1:18–1:40 | Terminal with `claude`. Type: `Is 771-999-0716 a scam? Who holds its range?` Show the tool call to `assess_number` and the answer. | "Agents get the same evidence. Through Dropnet's MCP server, Claude checks the number in the graph, names the range's holder, and repeats the caution: a holder issued the number; it is not the caller." |
| 1:40–1:50 | Back to the browser demo, the GitHub link visible. | "Complaints are unverified and caller IDs can be faked, so Dropnet ranks leads for a person to check. It never blocks anything. Dropnet, on Relate." |

## After recording

- Trim to under 2:00 and add captions (the voice-over text above).
- Upload it so judges can watch without signing in (YouTube unlisted or Vimeo), and put the link in the submission.
- If you use music, it must be licensed for this use or your own.
