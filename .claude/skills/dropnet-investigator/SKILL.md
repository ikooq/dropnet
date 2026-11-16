---
name: dropnet-investigator
description: Investigate fraud campaigns in the Dropnet Relate graph — who is behind a complaint, how complaints connect, where the money went, and what to freeze. Use when the user asks about a complaint (CMP-xxxx), a campaign (CAMP-xxxx), a card, phone, domain or alias in this repo.
---

# Dropnet investigator

The graph lives in `data/dropnet.rl` (a single-file Relate store). Query it through the `dropnet` MCP
server (tools below). All data is **synthetic**.

## Tools (MCP server `dropnet`)

| tool | use it for |
|---|---|
| `find_campaign(complaint_id)` | which campaign a complaint belongs to |
| `explain_link(a, b)` | the evidence path between two complaints + victims' quotes |
| `top_mules(campaign_id)` | cash-out and mule accounts to freeze |
| `similar_scripts(text)` | complaints that retell the same scam script |
| `build_case(campaign_id)` | a complete markdown case file |
| `read_cypher(statement)` | anything else, read-only |
| `get_schema()` | labels, relationship types and counts |

## Graph model

```
(Complaint)-[:CONTACTED_BY]->(Phone)          (Complaint)-[:PAID_TO]->(Card|Account)
(Card)-[:FORWARDED_TO {amount_kzt}]->(Card)   (Complaint)-[:VISITED]->(Url)-[:ON_DOMAIN]->(Domain)
(Complaint)-[:MENTIONS_PERSONA]->(Persona)    (Complaint)-[:USED_TACTIC]->(Tactic)
(Complaint)-[:SIMILAR_SCRIPT {score}]->(Complaint)   (Complaint)-[:PART_OF]->(Campaign)
(Extraction)-[:FROM]->(Complaint), (Extraction)-[:FOUND]->(entity)   // quote + character span
```
Keys: `Complaint.id`, `Phone.e164`, `Card.pan_masked`, `Account.iban`, `Domain.name`, `Persona.name`, `Campaign.id`.
`hub = true` marks legitimate shared numbers (e.g. marketplace support) — never use them as evidence.
`Card.role_hint` is `mule` (paid by 2+ victims) or `cashout` (end of a FORWARDED_TO chain).

## Recipes

```cypher
// 1. Where does the money of a campaign end up?
MATCH (c:Complaint)-[:PART_OF]->(:Campaign {id: $camp})
MATCH (c)-[:PAID_TO]->()-[:FORWARDED_TO*0..3]->(sink) WHERE NOT (sink)-[:FORWARDED_TO]->()
RETURN coalesce(sink.pan_masked, sink.iban) AS sink, count(DISTINCT c) AS victims ORDER BY victims DESC

// 2. Phones used against victims in 3+ regions
MATCH (c:Complaint)-[:CONTACTED_BY]->(p:Phone) WHERE NOT coalesce(p.hub, false)
WITH p, collect(DISTINCT c.region) AS regions WHERE size(regions) >= 3 RETURN p.e164, regions

// 3. The quote behind one link
MATCH (x:Extraction {complaint_id: $cmp})-[:FOUND]->(e) RETURN x.kind, x.value, x.quote

// 4. Complaints not yet linked but with a near-identical script
MATCH (a:Complaint)-[s:SIMILAR_SCRIPT]-(b:Complaint)-[:PART_OF]->(k:Campaign)
WHERE NOT (a)-[:PART_OF]->() AND s.score > 0.85 RETURN a.id, k.id, s.score ORDER BY s.score DESC

// 5. Cross-region campaigns
MATCH (c:Complaint)-[:PART_OF]->(k:Campaign) WITH k, count(DISTINCT c.region) AS r WHERE r >= 3 RETURN k.id, r

// 6. Vector search for a script
CALL db.index.vector.queryNodes('complaint_script', 5, $vector) YIELD node, score RETURN node.id, score
```

## Rules for answers

1. Every claim cites **node ids**, a **path** (from `explain_link` or a Cypher path) and at least one **victim
   quote** (from `Extraction.quote`).
2. Say how strong the link is: shared identifier / money trail (strong) vs. script similarity (weak).
3. Never present synthetic data as real; never print full card numbers (they are stored masked).
