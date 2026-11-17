"""A real AI agent (Claude Code, headless) answers about real reported numbers — with and without Dropnet's MCP tool.

The agent is asked what a person should do about a number that called them. Ground truth comes from the raw FTC
facts behind each number, the same rule `campaigns.assess_number` applies:
  likely_spoofed — every report came from the victim's own area code and there are at most two: the owner is
                   probably innocent, block nothing;
  rented_range   — its NPA-NXX block has >= 5 distinct non-spoofed reported numbers: block the range;
  repeat_caller  — 3+ reports, not in a pool: block the number;
  single_report  — one or two reports, nothing else: not enough to act.
Each run is isolated: an empty working directory, project settings only, no built-in tools (no web, no shell), and
in the "with" arm one MCP tool, `assess_number`, from the Dropnet server.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .. import config

VERDICTS = ["likely_spoofed", "rented_range", "repeat_caller", "single_report", "unknown"]
TRUTH = {"s": ("likely_spoofed", True, "nothing"), "p": ("rented_range", False, "range"),
         "r": ("repeat_caller", False, "number"), "1": ("single_report", None, "nothing")}
PROMPT = """Someone in the US got an unwanted call from {number}. They ask:
"Is the owner of this number the scammer, and what should my phone carrier block?"

Answer with one JSON object and nothing else:
{{"verdict": one of {verdicts},
  "owner_likely_innocent": true or false,
  "block": one of ["range", "number", "nothing"],
  "reason": one short sentence}}
"range" means the whole block of 10,000 numbers that share the first six digits."""


def sample(lookup: Path, per: dict[str, int], seed: int = 0) -> list[tuple[str, str]]:
    by = {k: [] for k in per}
    for line in lookup.read_text(encoding="utf-8").splitlines():
        if line.startswith(("#", "B ")):
            continue
        n, _r, code = line.split()
        if code in by:
            by[code].append(n)
    rnd = random.Random(seed)
    out = [(n, c) for c, k in per.items() for n in rnd.sample(sorted(by[c]), k)]
    rnd.shuffle(out)
    return out


def ask(number: str, with_tool: bool, model: str, workdir: Path, cfg: Path) -> dict:
    prompt = PROMPT.format(number=f"{number[:3]}-{number[3:6]}-{number[6:]}", verdicts=json.dumps(VERDICTS))
    # the prompt goes through stdin: on Windows a multi-line argument is cut at the first newline by the shell
    cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--tools", "",
           "--setting-sources", "project", "--strict-mcp-config", "--mcp-config", str(cfg)]
    if with_tool:
        cmd += ["--allowedTools", "mcp__dropnet__assess_number"]
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", shell=sys.platform == "win32")
    try:
        stdout, stderr = p.communicate(prompt, timeout=180)
    except subprocess.TimeoutExpired:
        # through a shell, killing the shell leaves the agent running and the pipes open: end the whole tree
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
        else:
            p.kill()
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        return {"error": "timeout after 180 s", "seconds": round(time.time() - t0, 1)}
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return {"error": (stderr or stdout)[:300]}
    text = env.get("result", "")
    ans = None
    try:
        ans = json.loads(text[text.find("{"): text.rfind("}") + 1])
    except (json.JSONDecodeError, ValueError):
        pass
    return {"answer": ans, "raw": text[:400], "turns": env.get("num_turns"), "seconds": round(time.time() - t0, 1)}


def score(rows: list[dict]) -> dict:
    def arm(key):
        got = [(r["code"], r[key].get("answer") or {}) for r in rows if key in r]
        n = len(got)
        spoof = [a for c, a in got if c == "s"]
        pool = [a for c, a in got if c == "p"]
        return {
            "answered": n,
            "verdict_correct": sum(1 for c, a in got if a.get("verdict") == TRUTH[c][0]),
            "block_correct": sum(1 for c, a in got if a.get("block") == TRUTH[c][2]),
            # the harm we care about: an innocent owner blamed, or their number / range blocked
            "spoofed_owner_blamed": sum(1 for a in spoof if a.get("owner_likely_innocent") is False or a.get("block") in ("number", "range")),
            "spoofed_total": len(spoof),
            "pool_range_blocked": sum(1 for a in pool if a.get("block") == "range"),
            "pool_total": len(pool),
            "said_unknown": sum(1 for _c, a in got if a.get("verdict") == "unknown"),
        }
    return {"without_dropnet": arm("without"), "with_dropnet": arm("with")}


def rerun_with(path: Path | None = None, log=print) -> dict:
    """Re-ask only the Dropnet arm on the same numbers (after a tool change); the earlier answers stay as `with_v1`."""
    path = Path(path or config.DATA_DIR / "ftc" / "live_agent_eval.json")
    res = json.loads(path.read_text(encoding="utf-8"))
    work = Path(tempfile.mkdtemp(prefix="dropnet-agent-"))
    on = work / "with.json"
    on.write_text(json.dumps({"mcpServers": {"dropnet": {"command": sys.executable, "args": ["-m", "dropnet", "mcp"],
                                                          "cwd": str(config.ROOT)}}}), encoding="utf-8")
    for i, row in enumerate(res["rows"]):
        if "with_v1" in row and row.get("with_v2_done"):
            continue  # resumed run: already re-asked
        row.setdefault("with_v1", row["with"])
        row["with"] = ask(row["number"], True, res["model"], work, on)
        row["with_v2_done"] = "answer" in row["with"]
        path.write_text(json.dumps(res, indent=1), encoding="utf-8")  # progress survives a stop
        log(f"{i + 1}/{len(res['rows'])} {row['number']} {row['code']}: {(row['with'].get('answer') or {}).get('block')}")
    res["score"] = score(res["rows"])
    v1 = [{"code": r["code"], "with": r["with_v1"]} for r in res["rows"]]
    res["score"]["with_dropnet_v1_facts_only"] = score(v1)["with_dropnet"]
    path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def run(model: str = "haiku", per: dict[str, int] | None = None, seed: int = 0, out: Path | None = None, log=print) -> dict:
    per = per or {"s": 14, "p": 14, "r": 6, "1": 6}
    nums = sample(config.ROOT / "docs" / "data" / "lookup.txt", per, seed)
    work = Path(tempfile.mkdtemp(prefix="dropnet-agent-"))
    on = work / "with.json"
    on.write_text(json.dumps({"mcpServers": {"dropnet": {"command": sys.executable, "args": ["-m", "dropnet", "mcp"],
                                                          "cwd": str(config.ROOT)}}}), encoding="utf-8")
    off = work / "without.json"
    off.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    rows = []
    for i, (n, code) in enumerate(nums):
        row = {"number": n, "code": code, "truth": TRUTH[code][0]}
        row["without"] = ask(n, False, model, work, off)
        row["with"] = ask(n, True, model, work, on)
        rows.append(row)
        log(f"{i + 1}/{len(nums)} {n} {code}: without={(row['without'].get('answer') or {}).get('verdict')} "
            f"with={(row['with'].get('answer') or {}).get('verdict')}")
    result = {"model": model, "seed": seed, "per_category": per, "numbers": len(nums), "score": score(rows), "rows": rows}
    out = out or config.DATA_DIR / "ftc" / "live_agent_eval.json"
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result
