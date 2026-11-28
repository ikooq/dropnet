import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, get_ident
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from dropnet.web import app as web


@pytest.fixture
def paused_graph(monkeypatch, tmp_path):
    entered, release = Event(), Event()
    opens, closes, summaries = [], [], []

    class Graph:
        def close(self):
            closes.append(get_ident())

    def open_store(_path):
        opens.append(get_ident())
        entered.set()
        assert release.wait(10), "test did not release the graph load"
        return Graph()

    def summary(_graph):
        summaries.append(get_ident())
        return {"reports": 42}

    monkeypatch.setattr(web.store, "open_store", open_store)
    monkeypatch.setattr(web, "_summary", summary)
    snapshot = tmp_path / "ftc.rl"
    snapshot.touch()
    app = web.create_app(ftc_snapshot=snapshot, ftc_live=tmp_path / "live" / "ftc.rl",
                         ftc_eval=tmp_path / "eval.json")
    return SimpleNamespace(app=app, entered=entered, release=release,
                           opens=opens, closes=closes, summaries=summaries)


def test_first_data_request_loads_graph_once_for_concurrent_requests(paused_graph, monkeypatch):
    both_waiting = Barrier(3, timeout=5)

    class ObserveGraphWaiters(ThreadPoolExecutor):
        def submit(self, fn, /, *args, **kwargs):
            future = super().submit(fn, *args, **kwargs)
            if fn.__name__ == "load_graph":
                result = future.result

                def observe_result(*args, **kwargs):
                    if not future.done():
                        both_waiting.wait()
                    return result(*args, **kwargs)

                future.result = observe_result
            return future

    monkeypatch.setattr(web, "ThreadPoolExecutor", ObserveGraphWaiters)
    with TestClient(paused_graph.app) as client, ThreadPoolExecutor(max_workers=2) as requests:
        assert "Loading the graph" in client.get("/").text
        assert client.get("/api/health").json()["loading"] is False
        assert not paused_graph.entered.is_set()
        pending = [requests.submit(client.get, "/api/ftc/summary") for _ in range(2)]
        try:
            assert paused_graph.entered.wait(5)
            both_waiting.wait()
        finally:
            paused_graph.release.set()
        assert [request.result(timeout=5).json()["reports"] for request in pending] == [42, 42]
        assert client.get("/api/ftc/summary").json()["reports"] == 42
        assert paused_graph.summaries == paused_graph.opens
        assert len(paused_graph.opens) == 1


def test_health_responds_while_graph_is_loading(paused_graph):
    with TestClient(paused_graph.app) as client, ThreadPoolExecutor(max_workers=2) as requests:
        pending = requests.submit(client.get, "/api/ftc/summary")
        try:
            assert paused_graph.entered.wait(5)
            health = requests.submit(client.get, "/api/health").result(timeout=0.5)
            assert health.status_code == 200
            assert health.json()["loaded"] is False
            assert health.json()["loading"] is True
            assert not pending.done()
        finally:
            paused_graph.release.set()
        assert pending.result(timeout=5).status_code == 200


def test_load_failure_returns_503_and_keeps_html_available(paused_graph, monkeypatch):
    def fail(_path):
        raise OSError("graph open failed")

    monkeypatch.setattr(web.store, "open_store", fail)
    with TestClient(paused_graph.app) as client:
        for path in ("/api/ftc/summary", "/api/ftc/number/7719990716"):
            response = client.get(path)
            assert response.status_code == 503
            assert response.json()["detail"] == "Could not load the FTC graph. See the server log."
        health = client.get("/api/health").json()
        assert health["loaded"] is False and health["loading"] is False
        page = client.get("/")
        assert page.status_code == 200 and "Dropnet" in page.text


def test_shutdown_during_load_closes_graph_on_relate_thread(paused_graph):
    loop_responsive = Event()

    async def serve_and_shutdown():
        app = paused_graph.app
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with app.router.lifespan_context(app):
                pending = asyncio.create_task(client.get("/api/ftc/summary"))
                assert await asyncio.to_thread(paused_graph.entered.wait, 5)
                pending.cancel()
                # The callback only runs once lifespan shutdown yields control to the loop.
                asyncio.get_running_loop().call_soon(loop_responsive.set)
            with pytest.raises(asyncio.CancelledError):
                await pending

    with ThreadPoolExecutor(max_workers=1) as worker:
        shutdown = worker.submit(asyncio.run, serve_and_shutdown())
        try:
            assert loop_responsive.wait(5), "shutdown blocked the event loop during graph loading"
            assert not shutdown.done()
            assert paused_graph.closes == []
        finally:
            paused_graph.release.set()
        shutdown.result(timeout=5)
    assert len(paused_graph.opens) == 1
    assert paused_graph.closes == paused_graph.opens
