"""dropnet-ftc — a Relate command extension: `relate run dropnet-ftc --path <FTC csv dir> -d graph`.

Reads FTC Do Not Call complaint files (.csv / .csv.gz), writes the call graph into the store Relate owns,
then finds the rented number ranges (pools) with Cypher — the same method as the full Dropnet build.
Standard library only: Relate installs this one file and spawns it; the host owns the store (MCP stdio).
"""

import csv
import gzip
import json
import os
import re
import sys

PROTOCOL_VERSION = "2025-06-18"
NAME = "dropnet-ftc"
VERSION = "0.1.0"
TOLL_FREE = {"800", "833", "844", "855", "866", "877", "888"}


class Client:
    def __init__(self):
        self._next_id = 0
        self.caps = {}

    def _send(self, message):
        sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    def request(self, method, params):
        self._next_id += 1
        rid = self._next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            line = sys.stdin.readline()
            if not line:
                raise SystemExit(f"mcp: the host closed the session before answering {method}")
            message = json.loads(line)
            if message.get("id") != rid:
                continue
            if "error" in message:
                raise SystemExit(f"mcp: {method} refused: {json.dumps(message['error'])}")
            return message.get("result", {})

    def start(self):
        line = sys.stdin.readline()
        if not line:
            raise SystemExit("mcp: the host wrote no request envelope")
        envelope = json.loads(line)
        result = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                             "clientInfo": {"name": NAME, "version": VERSION}})
        if result.get("protocolVersion") != PROTOCOL_VERSION:
            raise SystemExit(f"mcp: the host speaks {result.get('protocolVersion')!r}")
        self.caps = result.get("caps", {})  # e.g. maxRowsPerStatement: a bigger UNWIND ends the session
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return envelope

    def call(self, tool, arguments):
        result = self.request("tools/call", {"name": tool, "arguments": arguments})
        for block in result.get("content", []):
            if block.get("type") == "text":
                return json.loads(block["text"])
        raise SystemExit(f"mcp: '{tool}' answered no text content")


def number(raw):
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    return d if len(d) == 10 and d[0] not in "01" else None


def read_reports(path):
    """One dict per FTC report: number, day, victim area code, neighbor-spoofing flag."""
    files = [os.path.join(path, f) for f in sorted(os.listdir(path))] if os.path.isdir(path) else [path]
    for fp in files:
        if not (fp.endswith(".csv") or fp.endswith(".csv.gz")):
            continue
        opener = gzip.open if fp.endswith(".gz") else open
        key = os.path.basename(fp).split(".")[0]
        with opener(fp, "rt", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for i, row in enumerate(reader, 1):
                if len(row) < 8:
                    continue
                n = number(row[0])
                if not n:
                    continue
                vnpa = re.sub(r"\D", "", row[5])[:3]
                yield {"id": f"{key}:{i}", "number": n, "block": n[:6], "day": row[1].strip()[:10],
                       "neighbor": bool(vnpa) and vnpa == n[:3]}


WRITE = """UNWIND $rows AS r
MERGE (b:Block {npa_nxx: r.block})
MERGE (n:Number {number: r.number})
MERGE (n)-[:IN_BLOCK]->(b)
CREATE (x:Report {id: r.id, day: r.day, neighbor: r.neighbor})-[:FROM_NUMBER]->(n)
RETURN count(x) AS written"""

# Same rule as dropnet.ftc.campaigns.pool_campaigns: >= $m distinct numbers from one NPA-NXX block,
# counting only reports that were NOT neighbor-spoofed (caller area code != victim area code).
POOLS = """MATCH (r:Report)-[:FROM_NUMBER]->(n:Number)-[:IN_BLOCK]->(b:Block)
WHERE r.neighbor = false
WITH b, count(DISTINCT n) AS nums, count(r) AS reps WHERE nums >= $m
CREATE (c:FtcCampaign {id: 'POOL-' + b.npa_nxx, kind: 'pool', numbers: nums, reports: reps})-[:USES_BLOCK]->(b)
RETURN count(c) AS pools, sum(reps) AS reports"""


def walk(client, envelope):
    path, m = envelope["path"], int(envelope.get("min_numbers") or 5)
    if not path or not os.path.exists(path):
        raise SystemExit(f"{NAME}: --path must name an FTC .csv/.csv.gz file or a directory of them")
    for stmt in ("CREATE INDEX block_npa_nxx_idx IF NOT EXISTS FOR (n:Block) ON (n.npa_nxx)",
                 "CREATE INDEX number_number_idx IF NOT EXISTS FOR (n:Number) ON (n.number)"):
        client.call("write_cypher", {"statement": stmt})
    size = max(1, min(1000, int(client.caps.get("maxRowsPerStatement") or 1000)))
    batch, total = [], 0
    for r in read_reports(path):
        batch.append(r)
        if len(batch) == size:
            client.call("write_cypher", {"statement": WRITE, "parameters": {"rows": batch}})
            total, batch = total + len(batch), []
    if batch:
        client.call("write_cypher", {"statement": WRITE, "parameters": {"rows": batch}})
        total += len(batch)
    client.call("write_cypher", {"statement": POOLS, "parameters": {"m": m}})
    found = client.call("read_cypher", {"statement": "MATCH (c:FtcCampaign) RETURN count(c) AS pools"})
    row = (found.get("rows") or [{}])[0]
    client.call("report_output", {
        "text": f"{NAME}: {total:,} FTC reports -> {row.get('pools', 0):,} rented number ranges (pools) "
                f">= {m} numbers, spoofed reports excluded",
        "starters": ["MATCH (c:FtcCampaign) RETURN c.id, c.numbers, c.reports ORDER BY c.reports DESC LIMIT 10",
                     "MATCH (c:FtcCampaign)-[:USES_BLOCK]->(b)<-[:IN_BLOCK]-(n:Number) "
                     "RETURN c.id, collect(n.number)[..5] LIMIT 5"]})


def main():
    client = Client()
    walk(client, client.start())


if __name__ == "__main__":
    main()
