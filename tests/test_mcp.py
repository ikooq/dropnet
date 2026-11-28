import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

from dropnet import mcp_server, store
from dropnet.ftc import campaigns, load
from tests.test_ftc_load import R


@pytest.fixture(scope="module")
def ftc(tmp_path_factory):
    p = tmp_path_factory.mktemp("mcp") / "ftc.rl"
    c = store.open_store(p)
    load.load_reports(c, [R(i, f"866771{i % 6:04d}", victim_npa="303") for i in range(30)])
    campaigns.write_campaigns(c, min_numbers=5)
    c.close()
    return p


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_tool_names_are_ftc_only():
    assert set(mcp_server.TOOL_NAMES) == {"ftc_summary", "ftc_campaigns", "assess_number", "whatif_block",
                                         "search_ranges", "carriers", "carrier_detail", "ftc_read_cypher",
                                         "ftc_schema"}
    assert "synthetic" not in mcp_server.INSTRUCTIONS.lower()


def test_ftc_tools_in_snapshot_mode(ftc):
    before = ftc.read_bytes()
    b = mcp_server.Backend(web_url="http://127.0.0.1:1", ftc_snapshot=ftc)
    try:
        assert b.mode() == "snapshot"
        assert b.call("assess_number", {"number": "866-771-0001"})["verdict"] == "pool"
        assert b.call("ftc_campaigns", {"limit": 3})[0]["id"] == "POOL-866771"
        assert b.call("ftc_read_cypher", {"statement": "MATCH (r:Report) RETURN count(r) AS n"})["rows"] == [{"n": 30}]
        with pytest.raises(ValueError):
            b.call("ftc_read_cypher", {"statement": "MATCH (n) DETACH DELETE n"})
        assert b.call("whatif_block", {"blocks": ["866771"]})["reports_stopped"] == 30
    finally:
        b.close()
    assert ftc.read_bytes() == before  # what-if ran on a temporary copy


def test_proxy_uses_the_running_app(ftc, tmp_path):
    import uvicorn
    from dropnet.web.app import create_app
    port = free_port()
    app = create_app(reset=True, ftc_snapshot=ftc, ftc_live=tmp_path / "ftc-live.rl")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    try:
        b = mcp_server.Backend(web_url=f"http://127.0.0.1:{port}", ftc_snapshot=tmp_path / "missing.rl")
        assert b.mode() == "proxy"
        assert b.call("assess_number", {"number": "8667710002"})["verdict"] == "pool"
        with pytest.raises(ValueError):
            b.call("ftc_read_cypher", {"statement": "CREATE (n)"})
        b.close()
    finally:
        server.should_exit = True
        t.join(timeout=5)


def test_stdio_server_lists_and_calls_tools(ftc):
    env = {**os.environ, "DROPNET_WEB_URL": "http://127.0.0.1:1", "DROPNET_FTC_SNAPSHOT": str(ftc)}
    p = subprocess.Popen([sys.executable, "-m", "dropnet", "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, env=env, text=True, encoding="utf-8")

    def rpc(i, method, params):
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
        p.stdin.flush()
        while True:
            msg = json.loads(p.stdout.readline())
            if msg.get("id") == i:
                return msg

    try:
        init = rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "t", "version": "0"}})
        assert init["result"]["serverInfo"]["name"] == "dropnet"
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        p.stdin.flush()
        tl = rpc(2, "tools/list", {})
        assert {t["name"] for t in tl["result"]["tools"]} >= {"assess_number", "carriers", "read_cypher"}
        call = rpc(3, "tools/call", {"name": "assess_number", "arguments": {"number": "8667710001"}})
        assert "caution" in json.dumps(call["result"])
    finally:
        p.kill()
