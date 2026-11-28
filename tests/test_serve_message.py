import argparse

import uvicorn
from fastapi.testclient import TestClient

from dropnet import cli_live, config


def test_serve_prints_the_page_and_the_load_time_without_promising_ready(monkeypatch, capsys):
    started = {}

    def fake_run(app, host, port, **kw):
        # Start the app the way uvicorn would, without opening a socket or the graph.
        with TestClient(app) as client:
            started["health"] = client.get("/api/health").json()
        started["at"] = f"{host}:{port}"

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert cli_live.cmd_serve(argparse.Namespace(host="127.0.0.1", port=8123, reset=False)) == 0
    out = capsys.readouterr().out
    size_mb = round((config.DATA_DIR / "ftc.rl").stat().st_size / 1e6)

    assert out.strip() == (f"Dropnet page: http://127.0.0.1:8123. The graph ({size_mb} MB) loads when you first "
                           f"open it: about 10 seconds, during which the server does not respond.")
    assert "ready" not in out.lower()
    # the message is printed before any data request, and the graph is indeed not loaded yet
    assert started == {"health": started["health"], "at": "127.0.0.1:8123"}
    assert started["health"]["loaded"] is False and started["health"]["loading"] is False


def test_serve_message_rounds_the_file_size():
    assert "The graph (89 MB)" in cli_live.serve_message("http://x", 89_223_168)
