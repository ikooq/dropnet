import os
import subprocess
from pathlib import Path

import pytest

from dropnet.ftc import build, campaigns, networks, vault
from tests.test_networks import R, build as build_graph


def make(tmp_path):
    reps, i = [], 0
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        for blk in ("866771", "877578"):
            for k in range(3):
                i += 1
                reps.append(R(i, f"{blk}{k:04d}", victim_npa="303", subject="DEBT", day=day, state="Colorado"))
    c = build_graph(tmp_path, reps)
    networks.link_pools(c, min_shared=3)
    return c


def test_vault_files_and_links(tmp_path):
    c = make(tmp_path)
    out = tmp_path / "vault"
    stats = vault.export(c, out, top=10)
    c.close()
    assert stats["pools"] == 2 and stats["networks"] == 1
    pool = (out / "Pool" / "POOL-866771.md").read_text(encoding="utf-8")
    assert pool.startswith("---\ntype: Pool\n")
    assert '"[[Block/866771]]"' in pool and '"[[Pool/POOL-877578]]"' in pool and '"[[Network/NET-866771]]"' in pool
    assert '"[[Subject/DEBT]]"' in pool and "Caller ID" in pool
    assert (out / "Block" / "866771.md").exists() and (out / "Network" / "NET-866771.md").exists()
    assert (out / "README.md").exists()


def test_relate_opens_the_vault(tmp_path):
    cli = build.relate_cli()
    if not cli:
        pytest.skip("Relate CLI not installed")
    c = make(tmp_path)
    out = tmp_path / "vault"
    vault.export(c, out, top=10)
    c.close()
    r = subprocess.run([cli, "--mode", "json", "--snapshot-format", "markdown", "--markdown-body-properties", "text", "--database",
                        str(out), "query", "MATCH (p:Pool)-[:IN_NETWORK]->(n:Network) RETURN count(p) AS n"],
                       capture_output=True, text=True, env={**os.environ, "RELATE_TELEMETRY": "off"}, timeout=120)
    assert r.returncode == 0, r.stderr
    import json
    assert json.loads(r.stdout)["data"][0]["n"] == 2
