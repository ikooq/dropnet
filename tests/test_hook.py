import json
import subprocess
import sys

from dropnet import hook, store
from dropnet.ftc import campaigns, load
from tests.test_ftc_load import R


def make(tmp_path):
    p = tmp_path / "ftc.rl"
    c = store.open_store(p)
    load.load_reports(c, [R(i, f"866771{i % 6:04d}", victim_npa="303") for i in range(30)]
                      + [R(99, "3035550001", victim_npa="303", subject="MEDICAL")])
    campaigns.write_campaigns(c, min_numbers=5)
    c.close()
    return p


def test_no_numbers_no_context(tmp_path):
    assert hook.number_guard("Write a SQL query for monthly revenue", make(tmp_path)) is None


def test_context_for_spoofed_and_pool(tmp_path):
    ctx = hook.number_guard("Is (303) 555-0001 a scammer? Also check 866-771-0002 and +1 866 771 0003.", make(tmp_path))
    assert "303-555-0001" in ctx and "area-code match" in ctx.lower()
    assert "866-771-0002" in ctx and "pool" in ctx.lower()
    assert "not proof" in ctx  # the caution travels with every answer
    assert ctx.count("866-771-") == 2


def test_cli_hook_json(tmp_path):
    p = make(tmp_path)
    out = subprocess.run([sys.executable, "-m", "dropnet", "hook", "--ftc", str(p)],
                         input=json.dumps({"prompt": "who owns 303-555-0001?", "hook_event_name": "UserPromptSubmit"}),
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert out.returncode == 0, out.stderr
    data = json.loads(out.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "303-555-0001" in data["hookSpecificOutput"]["additionalContext"]


def test_unknown_numbers_only_stay_silent(tmp_path):
    assert hook.number_guard("order 2125550147 shipped", make(tmp_path)) is None


def test_hook_survives_odd_input(tmp_path):
    p = make(tmp_path)
    for raw in ["[]", '{"prompt": 5}', "not json", "", '{"prompt": "' + " 303-555-0001" * 20000 + '"}']:
        out = subprocess.run([sys.executable, "-m", "dropnet", "hook", "--ftc", str(p)], input=raw,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, (raw[:20], out.stderr[-300:])


def test_cli_hook_silent_without_numbers(tmp_path):
    out = subprocess.run([sys.executable, "-m", "dropnet", "hook", "--ftc", str(make(tmp_path))],
                         input=json.dumps({"prompt": "hello"}), capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and out.stdout.strip() == ""


def git_bash() -> str | None:
    """The bash Claude Code runs hooks with. On Windows that is Git Bash: `bash` on PATH is often WSL's
    C:\\Windows\\System32\\bash.exe, which fails without a Linux distribution (Bash/Service/0x8007072c)."""
    import os
    import shutil
    import sys
    from pathlib import Path
    if sys.platform != "win32":
        return shutil.which("bash")
    candidates = [os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")]
    if git := shutil.which("git"):  # ...\Git\cmd\git.exe or ...\Git\bin\git.exe
        candidates += [Path(git).parent.parent / "bin" / "bash.exe", Path(git).parent / "bash.exe"]
    candidates += [Path(os.environ.get(v, "")) / "Git" / "bin" / "bash.exe"
                   for v in ("ProgramFiles", "ProgramW6432", "LOCALAPPDATA") if os.environ.get(v)]
    candidates.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "bin" / "bash.exe")
    return next((str(c) for c in candidates if c and Path(c).is_file()), None)


def test_settings_hook_is_silent_without_the_package(tmp_path):
    """A judge who opens the repo in Claude Code before `pip install` must not see a failing hook."""
    from pathlib import Path
    bash = git_bash()
    if not bash:
        import pytest
        pytest.skip("Git Bash not available")
    root = Path(__file__).resolve().parent.parent
    cmd = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    r = subprocess.run([bash, "-c", cmd], input='{"prompt": "is 866-771-0001 a scam?"}', capture_output=True,
                       text=True, env={"PATH": str(tmp_path)})  # no dropnet on PATH
    assert r.returncode == 0 and r.stdout == ""


def test_running_app_answers_first(tmp_path):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class App(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"verdict": "pool", "reports": 7, "states": 2, "subjects": ["DEBT"],
                               "neighbor_share": 0.0, "block": "771999", "block_numbers": 53,
                               "holder": {"range_holder": "HOLDER A", "block_carrier": "CARRIER B",
                                          "rate_center": "RC", "state": "DC"}}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), App)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        ctx = hook.number_guard("771-999-0716?", tmp_path / "missing.rl", web_url=f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()
    assert "7 reports" in ctx and "HOLDER A as the range's holder" in ctx and "assigned to CARRIER B" in ctx
    assert "it is not the caller" in ctx


def test_no_app_falls_back_to_the_file(tmp_path):
    ctx = hook.number_guard("866-771-0001", make(tmp_path), web_url="http://127.0.0.1:1")
    assert "NUMBER POOL" in ctx


def _app(handler_body):
    """A stand-in for `dropnet serve` whose number endpoint runs handler_body(self)."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class App(BaseHTTPRequestHandler):
        def do_GET(self):
            handler_body(self)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), App)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_app_still_loading_its_graph_falls_back_to_the_file_quickly(tmp_path):
    """While `serve` loads the graph (~10 s) the number endpoint does not answer; the hook must not wait for it."""
    import threading
    import time
    release = threading.Event()
    srv = _app(lambda h: release.wait(10))
    try:
        t = time.monotonic()
        ctx = hook.number_guard("866-771-0001", make(tmp_path), web_url=f"http://127.0.0.1:{srv.server_port}")
        elapsed = time.monotonic() - t
    finally:
        release.set()
        srv.shutdown()
    assert "NUMBER POOL" in ctx  # answered from data/ftc.rl
    assert elapsed < 4  # one 1-second timeout, then the file; not one timeout per number


def test_app_that_cannot_load_the_graph_falls_back_to_the_file(tmp_path):
    def unavailable(h):
        h.send_response(503)
        h.end_headers()
        h.wfile.write(b'{"detail": "Could not load the FTC graph."}')
    srv = _app(unavailable)
    try:
        ctx = hook.number_guard("866-771-0001 or 866-771-0002", make(tmp_path),
                                web_url=f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()
    assert "NUMBER POOL" in ctx
