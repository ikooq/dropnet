"""Case files: one campaign, everything an investigator needs, every claim backed by a path and a quote."""
from __future__ import annotations

import html as _html
from dataclasses import dataclass, field

import relate

from . import tools
from .config import TACTICS
from .store import rows


@dataclass
class CaseFile:
    campaign: dict
    tactics: list[tuple[str, int]]
    accounts: list[dict]
    evidence: list[dict]            # {path, quotes}
    phones: list[dict]
    domains: list[dict]
    personas: list[dict]
    members: list[dict] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def _evidence_pairs(members: list[dict], want: int = 5) -> list[tuple[str, str]]:
    """Pairs that span different regions first: they show what a single regional office cannot see."""
    if len(members) < 2:
        return []
    first = members[0]
    pairs, used_regions = [], {first["region"]}
    for m in members[1:]:
        if m["region"] not in used_regions:
            pairs.append((first["id"], m["id"]))
            used_regions.add(m["region"])
        if len(pairs) >= want:
            break
    for m in members[1:]:
        if len(pairs) >= want:
            break
        if (first["id"], m["id"]) not in pairs:
            pairs.append((first["id"], m["id"]))
    return pairs[:want]


def build_case(conn: relate.Connection, campaign_id: str) -> CaseFile:
    camp = tools._campaign_props(conn, campaign_id)
    if camp is None:
        raise KeyError(campaign_id)
    members = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id})
        RETURN c.id AS id, c.region AS region, toString(c.filed_at) AS filed_at, c.amount_kzt AS amount_kzt,
               c.text_en AS text_en ORDER BY id""", {"id": campaign_id})
    tactic_rows = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id}) MATCH (c)-[:USED_TACTIC]->(t:Tactic)
        RETURN t.code AS code, count(c) AS n ORDER BY n DESC""", {"id": campaign_id})
    evidence = []
    for a, b in _evidence_pairs(members):
        link = tools.explain_link(conn, a, b)
        if link["found"]:
            evidence.append({"path": tools.render_path(link), "quotes": link["quotes"][:2]})
    phones = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id}) MATCH (c)-[:CONTACTED_BY]->(p:Phone)
        WHERE coalesce(p.hub, false) = false
        RETURN p.e164 AS phone, count(DISTINCT c) AS victims ORDER BY victims DESC, phone LIMIT 10""",
                  {"id": campaign_id})
    domains = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id}) MATCH (c)-[:VISITED]->(:Url)-[:ON_DOMAIN]->(d:Domain)
        RETURN d.name AS domain, count(DISTINCT c) AS victims ORDER BY victims DESC""", {"id": campaign_id})
    personas = rows(conn, """
        MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $id}) MATCH (c)-[:MENTIONS_PERSONA]->(p:Persona)
        RETURN p.name AS alias, count(DISTINCT c) AS victims ORDER BY victims DESC""", {"id": campaign_id})
    accounts = tools.top_mules(conn, campaign_id, n=5)
    case = CaseFile(camp, [(r["code"], r["n"]) for r in tactic_rows], accounts, evidence,
                    phones, domains, personas, [tools.jsonable(m) for m in members])
    case.actions = _actions(case)
    return case


def _actions(c: CaseFile) -> list[str]:
    acts = []
    for a in c.accounts:
        if a["role"] in ("cashout", "mule") and a["victims"] > 1:
            acts.append(f"Freeze {a['kind'].lower()} {a['account']} ({a['role']}, {a['bank']}) — "
                        f"linked to {a['victims']} victims.")
    shared = [p for p in c.phones if p["victims"] > 1]
    if shared:
        acts.append("Request subscriber and cell-site data for " + ", ".join(p["phone"] for p in shared[:5]) + ".")
    for d in c.domains:
        acts.append(f"Request takedown of phishing domain {d['domain']} ({d['victims']} victims).")
    for p in c.personas:
        acts.append(f"Search other reports for the alias '{p['alias']}' used in {p['victims']} complaints.")
    regions = c.campaign.get("regions", [])
    if len(regions) > 1:
        acts.append("Consolidate the regional cases into one investigation: " + ", ".join(regions) + ".")
    if not acts:
        acts.append("Compare new complaints against this script; no shared identifiers yet.")
    return acts


def _kzt(v) -> str:
    return f"{int(v):,} KZT"


def to_markdown(c: CaseFile) -> str:
    k = c.campaign
    out = [f"# Case file — {k['id']}", "",
           "> Synthetic data — generated for the Relate hackathon demo. No real people, cards or numbers.", "",
           "## Summary", "",
           f"- **Complaints:** {k['size']}",
           f"- **Regions:** {', '.join(k['regions'])} ({len(k['regions'])})",
           f"- **Reported damage:** {_kzt(k['damage_kzt'])}",
           f"- **Period:** {k['first_seen']} → {k['last_seen']}",
           f"- **Link confidence:** {k['confidence']} (1.0 = every member shares an identifier or money trail;"
           f" 0.5 = linked by script similarity)", "",
           "## Tactics", ""]
    out += [f"- {TACTICS.get(code, (code, code))[1]} (`{code}`): {n} complaints" for code, n in c.tactics] or ["- —"]
    out += ["", "## Mule & cash-out accounts", "", "| account | type | role | bank | victims |", "|---|---|---|---|---:|"]
    out += [f"| `{a['account']}` | {a['kind']} | {a['role']} | {a['bank']} | {a['victims']} |" for a in c.accounts]
    if not c.accounts:
        out.append("| — | | | | |")
    out += ["", "## Evidence paths", ""]
    if not c.evidence:
        out.append("- No path found.")
    for e in c.evidence:
        out.append(f"- `{e['path']}`")
        for q in e["quotes"]:
            out.append(f"  > {q['complaint']}: «{q['quote']}»")
    out += ["", "## Phones, domains & aliases", ""]
    out += [f"- Phone `{p['phone']}` — {p['victims']} victims" for p in c.phones]
    out += [f"- Domain `{d['domain']}` — {d['victims']} victims" for d in c.domains]
    out += [f"- Alias **{p['alias']}** — {p['victims']} victims" for p in c.personas]
    if not (c.phones or c.domains or c.personas):
        out.append("- None shared.")
    out += ["", "## Recommended actions", ""] + [f"{i}. {a}" for i, a in enumerate(c.actions, 1)]
    out += ["", "## Complaints", "", "| id | filed | region | amount | summary |", "|---|---|---|---:|---|"]
    out += [f"| {m['id']} | {m['filed_at']} | {m['region']} | {_kzt(m['amount_kzt'])} | {m['text_en'][:90]}… |"
            for m in c.members]
    out += ["", "_Generated by Dropnet from an embedded Relate graph (single-file store)._", ""]
    return "\n".join(out)


_CSS = """body{font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:920px;margin:24px auto;
padding:0 16px;color:#1b1f24;background:#fff}h1{font-size:24px}h2{font-size:18px;margin-top:28px;border-bottom:1px solid
#e3e6ea;padding-bottom:4px}code{background:#f2f4f7;padding:1px 5px;border-radius:4px;font-size:13px}
.banner{background:#fff6e0;border:1px solid #f0d58c;padding:8px 12px;border-radius:6px}table{border-collapse:collapse;
width:100%;font-size:13px}td,th{border-bottom:1px solid #eceff2;padding:6px;text-align:left}blockquote{margin:4px 0 8px
18px;color:#55606e;border-left:3px solid #d5dae0;padding-left:10px}.path{font-family:ui-monospace,Consolas,monospace;
font-size:13px;background:#f6f8fa;padding:6px 8px;border-radius:6px;overflow-x:auto;white-space:nowrap}"""


def to_html(c: CaseFile) -> str:
    e = _html.escape
    k = c.campaign
    parts = [f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
             f"content=\"width=device-width, initial-scale=1\"><title>Case {e(k['id'])}</title><style>{_CSS}</style>"
             f"</head><body><h1>Case file — {e(k['id'])}</h1>",
             "<p class=\"banner\">Synthetic data — generated for the Relate hackathon demo.</p>",
             "<h2>Summary</h2><ul>",
             f"<li><b>Complaints:</b> {k['size']}</li><li><b>Regions:</b> {e(', '.join(k['regions']))}</li>",
             f"<li><b>Reported damage:</b> {_kzt(k['damage_kzt'])}</li>",
             f"<li><b>Period:</b> {e(k['first_seen'])} → {e(k['last_seen'])}</li>",
             f"<li><b>Link confidence:</b> {k['confidence']}</li></ul><h2>Tactics</h2><ul>"]
    parts += [f"<li>{e(TACTICS.get(code, (code, code))[1])} — {n}</li>" for code, n in c.tactics]
    parts += ["</ul><h2>Mule &amp; cash-out accounts</h2><table><tr><th>account</th><th>type</th><th>role</th>"
              "<th>bank</th><th>victims</th></tr>"]
    parts += [f"<tr><td><code>{e(a['account'])}</code></td><td>{e(a['kind'])}</td><td>{e(a['role'])}</td>"
              f"<td>{e(str(a['bank']))}</td><td>{a['victims']}</td></tr>" for a in c.accounts]
    parts += ["</table><h2>Evidence paths</h2>"]
    for ev in c.evidence:
        parts.append(f"<div class=\"path\">{e(ev['path'])}</div>")
        parts += [f"<blockquote>{e(q['complaint'])}: «{e(q['quote'])}»</blockquote>" for q in ev["quotes"]]
    parts += ["<h2>Phones, domains &amp; aliases</h2><ul>"]
    parts += [f"<li>Phone <code>{e(p['phone'])}</code> — {p['victims']} victims</li>" for p in c.phones]
    parts += [f"<li>Domain <code>{e(d['domain'])}</code> — {d['victims']} victims</li>" for d in c.domains]
    parts += [f"<li>Alias <b>{e(p['alias'])}</b> — {p['victims']} victims</li>" for p in c.personas]
    parts += ["</ul><h2>Recommended actions</h2><ol>"] + [f"<li>{e(a)}</li>" for a in c.actions]
    parts += ["</ol><h2>Complaints</h2><table><tr><th>id</th><th>filed</th><th>region</th><th>amount</th>"
              "<th>summary</th></tr>"]
    parts += [f"<tr><td>{e(m['id'])}</td><td>{e(m['filed_at'])}</td><td>{e(m['region'])}</td>"
              f"<td>{_kzt(m['amount_kzt'])}</td><td>{e(m['text_en'])}</td></tr>" for m in c.members]
    parts += ["</table><p><small>Generated by Dropnet from an embedded Relate graph.</small></p></body></html>"]
    return "".join(parts)
