import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest

from dropnet import mcp_server, pipeline
from dropnet.synth.generate import generate


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    p = tmp_path_factory.mktemp("mcp") / "snap.rl"
    pipeline.build(p, seed=1, n=150)
    return p


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_tool_names():
    assert set(mcp_server.TOOL_NAMES) == {"get_schema", "read_cypher", "find_campaign", "explain_link", "top_mules",
                                         "similar_scripts", "build_case", "list_campaigns"}


def test_snapshot_mode(snap):
    b = mcp_server.Backend(web_url="http://127.0.0.1:1", snapshot=snap)
    try:
        assert b.mode() == "snapshot"
        ds = generate(seed=1, n=150)
        r = b.call("find_campaign", {"complaint_id": ds.truth["A"][1]})
        assert r["campaign"]["id"] == "CAMP-" + ds.truth["A"][0].split("-")[1]
        assert "## Evidence paths" in b.call("build_case", {"campaign_id": r["campaign"]["id"]})
        with pytest.raises(ValueError):
            b.call("read_cypher", {"statement": "MATCH (n) DELETE n"})
    finally:
        b.close()


def test_proxy_sees_live_ingest(snap, tmp_path):
    import uvicorn
    from dropnet.web.app import create_app
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(snapshot=snap, live=tmp_path / "live.rl", reset=True),
                                           host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        import httpx
        r = httpx.post(f"http://127.0.0.1:{port}/api/ingest",
                       json={"text": "Перевела 10 000 тг на карту 4000 0012 3456 7890."}).json()
        b = mcp_server.Backend(web_url=f"http://127.0.0.1:{port}", snapshot=snap)
        assert b.mode() == "proxy"
        found = b.call("find_campaign", {"complaint_id": r["complaint_id"]})
        assert found["complaint"]["id"] == r["complaint_id"]  # snapshot could not know this complaint
        with pytest.raises(ValueError):
            b.call("read_cypher", {"statement": "CREATE (n)"})
        b.close()
    finally:
        server.should_exit = True
        t.join(timeout=5)


def test_stdio_server_lists_and_calls_tools(snap):
    env = {**os.environ, "DROPNET_WEB_URL": "http://127.0.0.1:1", "DROPNET_SNAPSHOT": str(snap)}
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
        assert {t["name"] for t in tl["result"]["tools"]} >= {"find_campaign", "explain_link", "read_cypher"}
        call = rpc(3, "tools/call", {"name": "list_campaigns", "arguments": {}})
        text = json.dumps(call["result"])
        assert "CAMP-" in text
    finally:
        p.kill()
