"""Export the case work as a markdown vault that Relate opens as a graph (and Obsidian opens as notes).

    relate --snapshot-format markdown --markdown-body-properties text --database data/vault

Codec (Relate markdown vault): top-level folder = label, file name = key, frontmatter = properties,
one frontmatter list of "[[Folder/key]]" wikilinks per relationship type, note body = the `text` property.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import relate

from ..store import rows
from .campaigns import CAUTION
from .parse import SUBJECT_LABEL

VAULT_README = """---
type: Vault
---
# Dropnet case vault

One note per number pool, block, pool network and scam type, built from real FTC Do Not Call reports.
Open it as a graph:

    relate --snapshot-format markdown --markdown-body-properties text --database data/vault
    relate --database data/vault query "MATCH (p:Pool)-[:IN_NETWORK]->(n:Network) RETURN n.name, collect(p.name)"

Edit a note (add a finding, a status) and the change is in the graph at the next open — the analyst's notebook
and the database are the same files.

Caution: """ + CAUTION + "\n"


def _yaml(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace('"', "'") + '"'


def _note(path: Path, typ: str, props: dict, links: dict[str, list[str]], body: str) -> None:
    lines = ["---", f"type: {typ}"]
    for k, v in props.items():
        if v is not None:
            lines.append(f"{k}: {_yaml(v)}")
    for rel, targets in links.items():
        if targets:
            lines.append(f"{rel}:")
            lines += [f'  - "[[{t}]]"' for t in targets]
    lines += ["---", body.strip(), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def export(conn: relate.Connection, out: Path | str, top: int = 50) -> dict:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    pools = rows(conn, """MATCH (c:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)
                          RETURN c.id AS id, b.npa_nxx AS block, c.numbers AS numbers, c.reports AS reports,
                                 c.states AS states, c.toll_free AS tf, c.subjects AS subjects,
                                 c.first_day AS first, c.last_day AS last
                          ORDER BY reports DESC LIMIT $k""", {"k": top})
    ids = {p["id"] for p in pools}
    sib = rows(conn, "MATCH (a:FtcCampaign)-[s:SIBLING]->(b:FtcCampaign) RETURN a.id AS a, b.id AS b, s.shared AS n")
    net = {r["p"]: r["n"] for r in rows(conn, "MATCH (c:FtcCampaign)-[:IN_NETWORK]->(n:PoolNetwork) "
                                              "RETURN c.id AS p, n.id AS n")}
    nets = rows(conn, "MATCH (n:PoolNetwork) RETURN n.id AS id, n.pools AS pools, n.reports AS reports")
    subjects: set[str] = set()
    for p in pools:
        siblings = [(r["b"] if r["a"] == p["id"] else r["a"], r["n"]) for r in sib if p["id"] in (r["a"], r["b"])]
        subj = [s for s in (p["subjects"] or []) if s]
        subjects.update(subj)
        blk = p["block"]
        body = (f"# {blk[:3]}-{blk[3:]}-xxxx\n\n{p['numbers']} reported numbers in this range, {p['reports']} FTC "
                f"reports from victims in {p['states']} states, {p['first']} → {p['last']}"
                f"{' (toll-free range — shared by many businesses)' if p['tf'] else ''}.\n\n")
        if siblings:
            body += "Shares filing-day, consumer area and category patterns with: " + ", ".join(f"[[Pool/{s}]] ({n} shared area-day-scam slots)"
                                                          for s, n in siblings if s in ids) + ".\n\n"
        body += f"> {CAUTION}\n"
        _note(out / "Pool" / f"{p['id']}.md", "Pool",
              {"reports": p["reports"], "numbers": p["numbers"], "states": p["states"], "toll_free": p["tf"],
               "first_day": p["first"], "last_day": p["last"], "status": "open"},
              {"USES_BLOCK": [f"Block/{blk}"], "ABOUT": [f"Subject/{s}" for s in subj],
               "SIBLING": [f"Pool/{s}" for s, _ in siblings if s in ids and p["id"] < s],
               "IN_NETWORK": [f"Network/{net[p['id']]}"] if p["id"] in net else []},
               body)
        _note(out / "Block" / f"{blk}.md", "Block", {"npa": blk[:3], "nxx": blk[3:]}, {},
              f"NPA-NXX {blk[:3]}-{blk[3:]}: 10,000 numbers. Blocking it is a carrier's decision.")
    for n in nets:
        _note(out / "Network" / f"{n['id']}.md", "Network", {"pools": n["pools"], "reports": n["reports"]}, {},
              "Ranges with matching consumer area codes, complaint filing days and categories; this does not establish a common operator.")
    for s in subjects:
        _note(out / "Subject" / f"{s}.md", "Subject", {"label": SUBJECT_LABEL.get(s, s)}, {}, SUBJECT_LABEL.get(s, s))
    (out / "README.md").write_text(VAULT_README, encoding="utf-8")
    return {"pools": len(pools), "networks": len(nets), "subjects": len(subjects), "path": str(out)}
