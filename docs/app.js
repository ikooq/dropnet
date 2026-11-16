// Dropnet live demo: real FTC reports in an in-memory Relate database (WebAssembly), no server.
import init, { RelateDb } from "https://cdn.jsdelivr.net/npm/@relate/relate-wasm@1.0.1/relate.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => `${(100 * x).toFixed(1)}%`;
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const LABEL = { DEBT: "Debt relief", IMPOSTER_GOV: "Impersonation", MEDICAL: "Medical", OTHER: "Other", DROPPED: "Dropped call",
  NONE: "No subject", WARRANTY: "Warranty", HOME: "Home improvement", TRAVEL: "Travel", PRIZES: "Prizes", ENERGY: "Energy",
  TECH: "Tech support", WORK: "Work from home" };
let db, data, cy;

function q(cypher, params) {
  const r = JSON.parse(db.execute(cypher, params ? JSON.stringify(params) : null));
  if (r.error) throw new Error(r.error);
  return r.rows;
}
function hbar(label, value, max, ours) {
  return `<div class="hbar ${ours ? "ours" : ""}"><span>${label}</span><div class="track"><div class="fill"
    style="width:${Math.max(1, (100 * value) / max)}%"></div></div><span class="v">${pct(value)}</span></div>`;
}

function renderStatic() {
  const s = data.summary, ev = data.eval;
  $("#lede").innerHTML = `<b>${s.reports.toLocaleString()}</b> real complaints about unwanted calls (FTC, ${esc(s.first_day)} →
    ${esc(s.last_day)}). <b>${pct(s.single_report_numbers_share)}</b> of the numbers behind them were reported only once — a
    blocklist of numbers is always one step behind. Dropnet links numbers into the pools they come from.`;
  $("#kpis").innerHTML = [[s.reports.toLocaleString(), "reports"], [s.numbers.toLocaleString(), "reported numbers"],
    [pct(s.single_report_numbers_share), "numbers reported only once"], [pct(s.neighbor_share), "spoofed to look local"],
    [(s.campaigns.pool || 0).toLocaleString(), "number pools found"]].map(([v, l]) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join("");
  if (ev) {
    const max = Math.max(ev.dropnet.coverage, ev.blocklist_all_seen.coverage);
    $("#eval-caption").innerHTML = `Rules learned from reports before ${esc(ev.split_day)} (${ev.train_reports.toLocaleString()}), scored
      on the ${ev.test_reports.toLocaleString()} reports that came after:`;
    $("#eval-bars").innerHTML = hbar(`Every number ever reported (${ev.blocklist_all_seen.rules.toLocaleString()} rules)`, ev.blocklist_all_seen.coverage, max)
      + hbar(`Blocklist, ≥2 reports (${ev.baseline.rules.toLocaleString()})`, ev.baseline.coverage, max)
      + (ev.dropnet_geographic ? hbar(`<b>Dropnet</b>, geographic pools only (+${ev.dropnet_geographic.block_rules.toLocaleString()})`, ev.dropnet_geographic.coverage, max, true) : "")
      + hbar(`<b>Dropnet</b>, all pools incl. toll-free (+${ev.dropnet.block_rules.toLocaleString()})`, ev.dropnet.coverage, max, true)
      + `<p class="muted">${ev.dropnet.new_numbers_caught.toLocaleString()} catches came from numbers nobody had reported before. The price:
        a block rule silences all 10,000 numbers of its range, and toll-free ranges are shared by many businesses.</p>`;
  }
  $("#spoof-bars").innerHTML = data.profile.filter((p) => p.reports > 1000).sort((a, b) => b.neighbor_share - a.neighbor_share)
    .map((p) => hbar(esc(p.label), p.neighbor_share, 1)).join("");
  $("#source").textContent = `${data.source}. ${data.caution}`;
}

function loadGraph() {
  const t0 = performance.now();
  // Matching a node by property per row costs ~0.5 ms in WASM (11 s for 26k edges). Instead every node gets an
  // index, the nodes are collected into lists once, and edges pick their endpoints with xs[i] — ~1 s in total.
  const states = [], subjects = [], si = {}, ti = {}, eS = [], eT = [];
  let k = 0;
  const pools = data.pools.map(({ subjects: _s, nums, ...p }) => ({ ...p, nums: nums.map((n) => {
    const i = k++;
    for (const [s, c] of Object.entries(n.states)) { if (!(s in si)) { si[s] = states.length; states.push(s); } eS.push([i, si[s], c]); }
    for (const [s, c] of Object.entries(n.subjects)) { if (!(s in ti)) { ti[s] = subjects.length; subjects.push(s); } eT.push([i, ti[s], c]); }
    return { number: n.number, reports: n.reports, verdict: n.verdict, i };
  }) }));
  q(`UNWIND range(0, size($s) - 1) AS i CREATE (:State {name: $s[i], idx: i})`, { s: states });
  q(`UNWIND range(0, size($s) - 1) AS i CREATE (:Subject {code: $s[i], idx: i})`, { s: subjects });
  q(`UNWIND $pools AS p
     CREATE (b:Block {npa_nxx: p.block})
     CREATE (c:Pool {id: p.id, numbers: p.numbers, reports: p.reports, states: p.states, toll_free: p.toll_free,
                     first_day: p.first_day, last_day: p.last_day})-[:USES_BLOCK]->(b)
     WITH b, p UNWIND p.nums AS n
     CREATE (:Number {number: n.number, reports: n.reports, verdict: n.verdict, idx: n.i})-[:IN_BLOCK]->(b)`, { pools });
  for (const [label, rel, edges] of [["State", "CALLED_INTO", eS], ["Subject", "ABOUT", eT]]) {
    q(`MATCH (x:Number) WITH x ORDER BY x.idx WITH collect(x) AS xs
       MATCH (s:${label}) WITH xs, s ORDER BY s.idx WITH xs, collect(s) AS ss
       UNWIND $e AS e WITH xs[e[0]] AS x, ss[e[1]] AS s, e[2] AS c CREATE (x)-[:${rel} {reports: c}]->(s)`, { e: edges });
  }
  const counts = q("MATCH (n) RETURN count(n) AS nodes")[0].nodes;
  const rels = q("MATCH ()-[r]->() RETURN count(r) AS rels")[0].rels;
  $("#engine").textContent = `Relate WASM · ${counts.toLocaleString()} nodes · ${rels.toLocaleString()} relationships · loaded in ${Math.round(performance.now() - t0)} ms`;
}

function renderNetworkAndWhatIf() {
  const n = (data.networks || [])[0];
  if (n) {
    $("#net-panel").style.display = "";
    $("#net-panel").innerHTML = `<h2>One operation, ${n.pools} number ranges</h2>
      <p class="muted">Ranges that hit the same victims' area codes, on the same days, with the same scam type — linked by
      multi-hop paths in the graph. <b>${n.reports.toLocaleString()}</b> reports.</p>
      <div class="whatif-pick">${n.members.map((m) => `<label data-id="${esc(m.id)}" style="cursor:pointer">${esc(m.id.replace("POOL-", ""))} · ${m.reports.toLocaleString()}</label>`).join("")}</div>`;
    $("#net-panel").querySelectorAll("label[data-id]").forEach((l) => l.addEventListener("click", () => openPool(l.dataset.id)));
  }
  const top = q("MATCH (c:Pool) RETURN c.id AS id, c.reports AS r ORDER BY r DESC LIMIT 12");
  $("#whatif").innerHTML = `<h2>What if a carrier blocked these ranges?</h2>
    <div class="whatif-pick">${top.map((c, i) => `<label><input type="checkbox" value="${esc(c.id)}" ${i < 3 ? "checked" : ""}> ${esc(c.id.replace("POOL-", ""))}</label>`).join("")}</div>
    <button class="primary" id="wi-go">Run in the browser</button> <span class="muted">Cypher on the in-browser Relate graph.</span><div id="wi-out"></div>`;
  $("#wi-go").addEventListener("click", () => {
    const ids = [...document.querySelectorAll("#whatif input:checked")].map((x) => x.value);
    const r = q(`MATCH (c:Pool) WHERE c.id IN $ids
                 RETURN count(c) AS rules, sum(c.reports) AS reports, sum(c.numbers) AS numbers, sum(c.states) AS st`, { ids })[0];
    $("#wi-out").innerHTML = `<p><b>${(r.reports || 0).toLocaleString()}</b> reports from <b>${(r.numbers || 0).toLocaleString()}</b>
      reported numbers would have been stopped by ${r.rules} block rule${r.rules === 1 ? "" : "s"} — at the price of
      ${(r.rules * 10000).toLocaleString()} numbers silenced (each block = 10,000 numbers). A carrier's call, not ours.</p>`;
  });
}

function renderList() {
  const pools = q("MATCH (c:Pool) RETURN c.id AS id, c.numbers AS numbers, c.reports AS reports, c.states AS states, c.toll_free AS tf ORDER BY reports DESC LIMIT 40");
  $("#list").innerHTML = pools.map((c) => `<button class="camp-card" data-id="${esc(c.id)}"><div class="id">${esc(c.id.replace("POOL-", "Pool "))}</div>
    <div class="meta">${c.numbers} numbers · ${c.reports.toLocaleString()} reports · ${c.states} states${c.tf ? " · toll-free" : ""}</div></button>`).join("");
  $("#list").querySelectorAll(".camp-card").forEach((b) => b.addEventListener("click", () => openPool(b.dataset.id)));
  if (pools.length) openPool(pools[0].id);
}

function openPool(id) {
  document.querySelectorAll("#list .camp-card").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const c = q("MATCH (c:Pool {id: $id}) RETURN c.numbers AS numbers, c.reports AS reports, c.states AS states, c.first_day AS f, c.last_day AS l", { id })[0];
  const blk = id.replace("POOL-", "");
  $("#head").innerHTML = `<h2>${esc(blk.slice(0, 3))}-${esc(blk.slice(3))}-xxxx</h2><span class="badge">${c.numbers} numbers</span>
    <span class="badge">${c.reports.toLocaleString()} reports</span><span class="badge">${c.states} states</span>
    <span class="badge">${esc(c.f || "")} → ${esc(c.l || "")}</span>`;
  const nums = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(b:Block)<-[:IN_BLOCK]-(n:Number) RETURN b.npa_nxx AS b, n.number AS n, n.reports AS r`, { id });
  const states = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)-[r:CALLED_INTO]->(s:State)
                    RETURN n.number AS n, s.name AS s, r.reports AS c ORDER BY c DESC`, { id });
  const subj = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)-[r:ABOUT]->(s:Subject)
                  RETURN n.number AS n, s.code AS s, r.reports AS c`, { id });
  const topStates = new Set(Object.entries(states.reduce((m, x) => ((m[x.s] = (m[x.s] || 0) + x.c), m), {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 12).map(([s]) => s));
  const C = { Block: css("--c-cashout"), Number: css("--c-card"), State: css("--c-phone"), Subject: css("--c-persona") };
  const nodes = new Map(), edges = [];
  const add = (i, kind, label, w) => nodes.has(i) || nodes.set(i, { data: { id: i, kind, label, color: C[kind], w } });
  for (const x of nums) {
    add("B" + x.b, "Block", `${x.b.slice(0, 3)}-${x.b.slice(3)}`, 40);
    add("N" + x.n, "Number", x.n.slice(-4), 8 + Math.min(26, Math.sqrt(x.r) * 2));
    edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "B" + x.b, type: "IN_BLOCK" } });
  }
  for (const x of states) if (topStates.has(x.s)) { add("S" + x.s, "State", x.s, 18); edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "S" + x.s, type: "CALLED_INTO" } }); }
  for (const x of subj) { add("T" + x.s, "Subject", LABEL[x.s] || x.s, 18); edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "T" + x.s, type: "ABOUT" } }); }
  if (cy) cy.destroy();
  cy = cytoscape({ container: $("#ftc-graph"), elements: [...nodes.values(), ...edges], wheelSensitivity: 0.25,
    style: [{ selector: "node", style: { "background-color": "data(color)", label: "data(label)", width: "data(w)", height: "data(w)", "font-size": 9, color: css("--ink") } },
      { selector: "node[kind = 'Block'], node[kind = 'State'], node[kind = 'Subject']", style: { shape: "round-rectangle" } },
      { selector: "edge", style: { width: 1, "line-color": css("--line"), "curve-style": "haystack" } },
      { selector: "edge[type = 'IN_BLOCK']", style: { width: 2, "line-color": C.Block } }],
    layout: { name: "cose", animate: false, nodeRepulsion: 12000, idealEdgeLength: 60, padding: 24 } });
  cy.on("tap", "node[kind = 'Number']", (e) => check(e.target.id().slice(1)));
  $("#legend").innerHTML = [["Block (NPA-NXX)", C.Block], ["Reported number", C.Number], ["Victim state", C.State], ["Scam type", C.Subject]]
    .map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("") + "<span>node size = reports</span>";
}

// Every reported number + every pool block (docs/data/lookup.txt, ~1 MB gzipped), fetched on the first check only.
let lookup = null;
async function loadLookup() {
  if (lookup) return lookup;
  const text = await (await fetch("data/lookup.txt")).text();
  const nums = new Map(), blocks = new Map();
  let span = "";
  for (const line of text.split(/\r?\n/)) {
    if (!line) continue;
    if (line[0] === "#") { span = line.split(" ").slice(4, 6).join(" to "); continue; }
    const p = line.split(" ");
    if (p[0] === "B") blocks.set(p[1], { numbers: +p[2], reports: +p[3] });
    else nums.set(p[0], { reports: +p[1], code: p[2] });
  }
  return (lookup = { nums, blocks, span });
}
const VERDICT = {
  s: ["likely_spoofed", "Likely spoofed", "Reported only from the victim's own area code: the caller faked this number to look local. Its real owner is probably innocent — don't blame them, and don't call back."],
  p: ["pool", "Part of a rented number pool", "This number sits in a range that scammers rotate through. Blocking the whole range stops numbers that haven't been reported yet."],
  r: ["pool", "Reported again and again", "One number reported many times from other area codes."],
  "1": ["", "Reported once", "One report is weak evidence on its own."],
};
async function check(raw) {
  const n = String(raw).replace(/\D/g, "").slice(-10);
  if (n.length !== 10) { $("#num-out").innerHTML = `<p class="muted">Enter a 10-digit US number.</p>`; return; }
  $("#num-in").value = n.replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3");
  history.replaceState(null, "", "?n=" + n + location.hash);
  $("#num-out").innerHTML = `<p class="muted">Checking ${data.summary.numbers.toLocaleString()} reported numbers…</p>`;
  let L;
  try { L = await loadLookup(); } catch (e) { $("#num-out").innerHTML = `<p class="muted">Could not load the lookup file.</p>`; return; }
  const hit = L.nums.get(n), block = L.blocks.get(n.slice(0, 6));
  const range = n.replace(/(\d{3})(\d{3})\d{4}/, "$1-$2-xxxx");
  let html;
  if (hit) {
    const [cls, title, why] = VERDICT[hit.code] || VERDICT["1"];
    html = `<p class="verdict ${cls}">${title}</p><p>${hit.reports.toLocaleString()} report${hit.reports > 1 ? "s" : ""} to the FTC (${esc(L.span)}). ${why}</p>`;
    if (block && hit.code !== "s") html += `<p>Range ${range}: ${block.numbers.toLocaleString()} numbers, ${block.reports.toLocaleString()} reports.</p>`;
  } else if (block) {
    html = `<p class="verdict pool">Never reported — but its range is a rented pool</p><p>${range} has ${block.numbers.toLocaleString()} reported numbers and
      ${block.reports.toLocaleString()} reports.${data.eval && data.eval.dropnet ? ` In our hold-out test, ${data.eval.dropnet.new_numbers_caught.toLocaleString()} later
      complaints came from numbers like this: never reported before, but inside a known pool.` : ""}</p>`;
  } else {
    html = `<p class="verdict">No FTC reports for this number or its range</p><p class="muted">${esc(L.span)}. That is not proof it is safe.</p>`;
  }
  $("#num-out").innerHTML = html + `<p class="muted"><a href="?n=${n}">Link to this result</a> · <a href="https://reportfraud.ftc.gov/" target="_blank" rel="noopener">Report a call to the FTC</a></p><div class="caution">${esc(data.caution)}</div>`;
}
$("#num-go").addEventListener("click", () => check($("#num-in").value));
$("#num-in").addEventListener("keydown", (e) => { if (e.key === "Enter") check($("#num-in").value); });

const QUERIES = [
  ["Biggest pools", "MATCH (c:Pool)-[:USES_BLOCK]->(b:Block)\nRETURN b.npa_nxx AS block, c.numbers AS numbers, c.reports AS reports\nORDER BY reports DESC LIMIT 10"],
  ["Pools hitting most states", "MATCH (c:Pool)-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(:Number)-[:CALLED_INTO]->(s:State)\nRETURN c.id AS pool, count(DISTINCT s) AS states ORDER BY states DESC LIMIT 10"],
  ["Scam types by pool reports", "MATCH (:Number)-[r:ABOUT]->(s:Subject)\nRETURN s.code AS scam_type, sum(r.reports) AS reports ORDER BY reports DESC"],
  ["Toll-free vs local pools", "MATCH (c:Pool)\nRETURN c.toll_free AS toll_free, count(c) AS pools, sum(c.reports) AS reports"],
];
$("#q-samples").innerHTML = QUERIES.map(([l], i) => `<button data-i="${i}">${esc(l)}</button>`).join("");
$("#q-samples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("#q-text").value = QUERIES[b.dataset.i][1]; run(); }));
$("#q-text").value = QUERIES[0][1];
function run() {
  const t0 = performance.now();
  try {
    if (/\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP)\b/i.test($("#q-text").value)) throw new Error("This demo console is read-only.");
    const rows = q($("#q-text").value);
    const cols = rows.length ? Object.keys(rows[0]) : [];
    $("#q-meta").textContent = `${rows.length} rows · ${(performance.now() - t0).toFixed(1)} ms in your browser`;
    $("#q-out").innerHTML = rows.length ? `<table class="grid"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>`
      + rows.map((r) => `<tr>${cols.map((c) => `<td class="mono">${esc(typeof r[c] === "object" ? JSON.stringify(r[c]) : r[c])}</td>`).join("")}</tr>`).join("")
      + "</tbody></table>" : `<p class="muted">No rows.</p>`;
  } catch (e) { $("#q-meta").textContent = ""; $("#q-out").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
$("#q-go").addEventListener("click", run);

(async function boot() {
  data = await (await fetch("data/graph.json")).json();
  renderStatic();
  await init();
  db = new RelateDb();
  loadGraph();
  renderList();
  renderNetworkAndWhatIf();
  run();
  const shared = new URLSearchParams(location.search).get("n");
  if (shared) { $(".lookup").scrollIntoView({ block: "center" }); check(shared); }
})().catch((e) => { $("#engine").textContent = "Error: " + e.message; console.error(e); });
