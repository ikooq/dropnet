"""The Dropnet graph speaks Bolt: the official Neo4j driver queries it unchanged."""
import pytest

from dropnet import config
from dropnet.ftc import bolt


def test_neo4j_driver_reads_the_real_store():
    if not (config.DATA_DIR / "ftc.rl").exists():
        pytest.skip("real FTC snapshot not built")
    pytest.importorskip("neo4j")
    r = bolt.query_via_bolt(config.DATA_DIR / "ftc.rl",
                            "MATCH (c:FtcCampaign {kind: 'pool'}) RETURN count(c) AS pools")
    if r is None:
        pytest.skip("Relate CLI not installed")
    assert r[0]["pools"] > 1000


def test_http_query_api_reads_the_real_store():
    if not (config.DATA_DIR / "ftc.rl").exists():
        pytest.skip("real FTC snapshot not built")
    r = bolt.query_via_http(config.DATA_DIR / "ftc.rl",
                            "MATCH (c:FtcCampaign {kind: 'pool'}) WHERE c.numbers >= $m RETURN count(c) AS pools", {"m": 5})
    if r is None:
        pytest.skip("Relate CLI not installed")
    assert r[0]["pools"] > 1000
