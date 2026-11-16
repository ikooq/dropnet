---
type: Vault
name: README
---

# Dropnet case vault

One note per number pool, block, pool network and scam type, built from real FTC Do Not Call reports.
Open it as a graph:

    relate --snapshot-format markdown --markdown-body-properties text --database data/vault
    relate --database data/vault query "MATCH (p:Pool)-[:IN_NETWORK]->(n:Network) RETURN n.name, collect(p.name)"

Edit a note (add a finding, a status) and the change is in the graph at the next open — the analyst's notebook
and the database are the same files.

Caution: Caller ID is easily faked. A number reported once, from the victim's own area code, is most likely spoofed — its real owner may be innocent. Treat this as evidence about a call, not about a person.
