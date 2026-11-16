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
    assert "303-555-0001" in ctx and "likely spoofed" in ctx.lower()
    assert "866-771-0002" in ctx and "pool" in ctx.lower()
    assert "innocent" in ctx  # the caution travels with every answer
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
