// Dropnet live demo: real FTC reports in an in-memory Relate database (WebAssembly), no server.
import init, { RelateDb } from "https://cdn.jsdelivr.net/npm/@relate/relate-wasm@1.0.1/relate.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => `${(100 * x).toFixed(1)}%`;
const fmt = (x) => Number(x || 0).toLocaleString("en-US");
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const day = (d, year = false) => (d ? `${MON[+d.slice(5, 7) - 1]} ${+d.slice(8, 10)}${year ? ", " + d.slice(0, 4) : ""}` : "");
const dash = (n) => n.replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3");
const rangeOf = (b) => `${b.slice(0, 3)}-${b.slice(3, 6)}-xxxx`;
const LABEL = { DEBT: "Debt relief", IMPOSTER_GOV: "Impersonation", MEDICAL: "Medical", OTHER: "Other", DROPPED: "Dropped call",
  NONE: "No subject", WARRANTY: "Warranty", HOME: "Home improvement", TRAVEL: "Travel", PRIZES: "Prizes", ENERGY: "Energy",
  TECH: "Tech support", WORK: "Work from home" };
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
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
  $("#lede").innerHTML = `People reported <b>${fmt(s.reports)}</b> unwanted calls to the FTC between ${day(s.first_day)} and
    ${day(s.last_day, true)}. <b>${pct(s.single_report_numbers_share)}</b> of the numbers were reported only once. Dropnet groups complaints by number range to help analysts investigate patterns.`;
  if (ev) {
    const max = Math.max(ev.dropnet.coverage, ev.blocklist_all_seen.coverage);
    $("#eval-caption").innerHTML = `Rules learned from the ${fmt(ev.train_reports)} reports before ${day(ev.split_day)}, then
      tested on the ${fmt(ev.test_reports)} that came after.`;
    $("#eval-bars").innerHTML = hbar(`Block every number ever reported`, ev.blocklist_all_seen.coverage, max)
      + hbar(`Block numbers with 2+ reports`, ev.baseline.coverage, max)
      + (ev.dropnet_geographic ? hbar(`Dropnet: also block ${fmt(ev.dropnet_geographic.block_rules)} local ranges`, ev.dropnet_geographic.coverage, max, true) : "")
      + hbar(`Dropnet: plus toll-free ranges`, ev.dropnet.coverage, max, true);
    const rb = ev.robustness;
    $("#eval-note").innerHTML = `${fmt(ev.dropnet.new_numbers_caught)} later reports matched numbers not previously reported.${rb ? ` We repeated the test from ${rb.rolling_summary.splits} different start days: Dropnet matched at
      least ${rb.rolling_summary.min_lift.toFixed(1)} times as many reports every time, ${rb.rolling_summary.median_lift.toFixed(1)} times typically.` : ""} The price: a range rule can affect up to
      10,000 numbers; legitimate-call impact is unknown.`;
  }
  $("#spoof-bars").innerHTML = data.profile.filter((p) => p.reports > 1000).sort((a, b) => b.neighbor_share - a.neighbor_share)
    .map((p) => hbar(esc(LABEL[p.subject] || p.label), p.neighbor_share, 1)).join("");
  $("#agent-note").textContent = "A historical agent experiment measured agreement with Dropnet's own labels and advice, not independently verified spoofing or correct blocking decisions.";
  $("#source").textContent = data.caution;
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
  const nodes = q("MATCH (n) RETURN count(n) AS nodes")[0].nodes;
  const rels = q("MATCH ()-[r]->() RETURN count(r) AS rels")[0].rels;
  const ms = Math.round(performance.now() - t0);
  $("#engine").textContent = `Relate running in your browser: ${fmt(nodes)} nodes and ${fmt(rels)} relationships${ms ? `, loaded in ${fmt(ms)} ms` : ""}`;
}

function renderNetworkAndWhatIf() {
  const n = (data.networks || [])[0];
  if (n) {
    const el = $("#net-panel");
    el.hidden = false;
    el.innerHTML = `<h2>${n.pools} ranges with related complaint patterns</h2>
      <p class="quiet">Reports for these ranges share consumer area codes, filing days and complaint categories: ${fmt(n.reports)} reports
      in all. The links do not prove a common operator. Open one to see its numbers.</p>
      <ul class="chips">${n.members.map((m) => `<li><button data-id="${esc(m.id)}"><b>${esc(rangeOf(m.id.replace("POOL-", "")))}</b> ${fmt(m.reports)} reports</button></li>`).join("")}</ul>`;
    el.querySelectorAll("button[data-id]").forEach((b) => b.addEventListener("click", () => { openPool(b.dataset.id); $(".pools").scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" }); }));
  }
  const top = q("MATCH (c:Pool) RETURN c.id AS id, c.reports AS r ORDER BY r DESC LIMIT 12");
  $("#whatif").innerHTML = `<h2>What if a carrier had blocked these ranges?</h2>
    <p class="quiet">Pick ranges and count reports whose caller IDs match them. These are filing dates, not necessarily call dates. The count runs as Cypher on this page.</p>
    <ul class="chips">${top.map((c, i) => `<li><label><input type="checkbox" value="${esc(c.id)}" ${i < 3 ? "checked" : ""}> <b>${esc(rangeOf(c.id.replace("POOL-", "")))}</b></label></li>`).join("")}</ul>
    <button class="go small" id="wi-go">Count matching reports</button><div id="wi-out"></div>`;
  $("#wi-go").addEventListener("click", () => {
    const ids = [...document.querySelectorAll("#whatif input:checked")].map((x) => x.value);
    const r = q(`MATCH (c:Pool) WHERE c.id IN $ids
                 RETURN count(c) AS rules, sum(c.reports) AS reports, sum(c.numbers) AS numbers`, { ids })[0];
    $("#wi-out").innerHTML = r.rules ? `<p><b>${fmt(r.reports)}</b> eligible reports from <b>${fmt(r.numbers)}</b> different numbers
      matched ${r.rules} rule${r.rules === 1 ? "" : "s"}. A rule could affect up to ${fmt(r.rules * 10000)} numbers,
      some belonging to legitimate callers. Pool totals exclude area-code matches; this is not an estimate of all affected traffic.</p>`
      : `<p class="quiet">Pick at least one range.</p>`;
  });
}

function renderList() {
  const pools = q("MATCH (c:Pool) RETURN c.id AS id, c.numbers AS numbers, c.reports AS reports, c.states AS states, c.toll_free AS tf ORDER BY reports DESC LIMIT 40");
  $("#list").innerHTML = pools.map((c) => `<li><button class="camp-card" data-id="${esc(c.id)}"><div class="id">${esc(rangeOf(c.id.replace("POOL-", "")))}</div>
    <div class="meta">${fmt(c.reports)} reports from ${c.numbers} numbers, ${c.states} states${c.tf ? ", toll-free" : ""}</div></button></li>`).join("");
  $("#list").querySelectorAll(".camp-card").forEach((b) => b.addEventListener("click", () => openPool(b.dataset.id)));
  if (pools.length) openPool(pools[0].id);
}

function openPool(id) {
  document.querySelectorAll("#list .camp-card").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const c = q("MATCH (c:Pool {id: $id}) RETURN c.numbers AS numbers, c.reports AS reports, c.states AS states, c.first_day AS f, c.last_day AS l", { id })[0];
  const blk = id.replace("POOL-", "");
  $("#head").innerHTML = `<h3>${esc(rangeOf(blk))}</h3><span>${fmt(c.reports)} reports</span><span>${c.numbers} numbers</span>
    <span>${c.states} states</span><span>${day(c.f)} to ${day(c.l)}</span>`;
  const nums = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(b:Block)<-[:IN_BLOCK]-(n:Number) RETURN b.npa_nxx AS b, n.number AS n, n.reports AS r`, { id });
  const states = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)-[r:CALLED_INTO]->(s:State)
                    RETURN n.number AS n, s.name AS s, r.reports AS c ORDER BY c DESC`, { id });
  const subj = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)-[r:ABOUT]->(s:Subject)
                  RETURN n.number AS n, s.code AS s, r.reports AS c`, { id });
  const topStates = new Set(Object.entries(states.reduce((m, x) => ((m[x.s] = (m[x.s] || 0) + x.c), m), {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 12).map(([s]) => s));
  const C = { Block: css("--c-block"), Number: css("--c-number"), State: css("--c-state"), Subject: css("--c-subject") };
  const nodes = new Map(), edges = [];
  const add = (i, kind, label, w) => nodes.has(i) || nodes.set(i, { data: { id: i, kind, label, color: C[kind], w } });
  for (const x of nums) {
    add("B" + x.b, "Block", rangeOf(x.b), 40);
    add("N" + x.n, "Number", x.n.slice(-4), 8 + Math.min(26, Math.sqrt(x.r) * 2));
    edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "B" + x.b, type: "IN_BLOCK" } });
  }
  for (const x of states) if (topStates.has(x.s)) { add("S" + x.s, "State", x.s, 18); edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "S" + x.s, type: "CALLED_INTO" } }); }
  for (const x of subj) { add("T" + x.s, "Subject", LABEL[x.s] || x.s, 18); edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "T" + x.s, type: "ABOUT" } }); }
  if (cy) cy.destroy();
  cy = cytoscape({ container: $("#ftc-graph"), elements: [...nodes.values(), ...edges], wheelSensitivity: 0.25,
    style: [{ selector: "node", style: { "background-color": "data(color)", label: "data(label)", width: "data(w)", height: "data(w)",
        "font-size": 9, "font-family": "Archivo, sans-serif", color: css("--ink"), "text-valign": "bottom", "text-margin-y": 3 } },
      { selector: "node[kind = 'Block'], node[kind = 'State'], node[kind = 'Subject']", style: { shape: "round-rectangle", "font-size": 11, "font-weight": 700 } },
      { selector: "node[kind = 'Number']", style: { label: "" } },
      { selector: "edge", style: { width: 1, "line-color": css("--rule"), "curve-style": "haystack" } },
      { selector: "edge[type = 'IN_BLOCK']", style: { width: 1.5, "line-color": css("--muted") } }],
    layout: { name: "cose", animate: false, nodeRepulsion: 14000, idealEdgeLength: 70, padding: 24 } });
  cy.on("tap", "node[kind = 'Number']", (e) => { check(e.target.id().slice(1)); $(".hero").scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" }); });
  $("#legend").innerHTML = [["Range", C.Block], ["Reported number (tap to check)", C.Number], ["State called", C.State], ["Scam type", C.Subject]]
    .map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("");
}

// ---- the hero: one number, and the 10,000-number range it belongs to ----
// docs/data/lookup.txt: every reported number + every pool block (~1 MB gzipped), fetched once.
let lookupPromise = null;
function loadLookup() {
  return lookupPromise ??= fetch("data/lookup.txt").then((r) => r.text()).then((text) => {
    const nums = new Map(), blocks = new Map(), byBlock = new Map();
    let span = "";
    for (const line of text.split(/\r?\n/)) {
      if (!line) continue;
      if (line[0] === "#") { const [a, b] = line.split(" ").slice(4, 6); span = `${day(a)} and ${day(b, true)}`; continue; }
      const p = line.split(" ");
      if (p[0] === "B") { blocks.set(p[1], { numbers: +p[2], reports: +p[3] }); continue; }
      const rec = { reports: +p[1], code: p[2] };
      nums.set(p[0], rec);
      const b = p[0].slice(0, 6);
      if (!byBlock.has(b)) byBlock.set(b, []);
      byBlock.get(b).push([+p[0].slice(6), rec]);
    }
    return { nums, blocks, byBlock, span };
  });
}

const grid = { block: null, cells: null, focus: -1 };
function drawGrid(L, block, focus, animate) {
  const cv = $("#grid"), ctx = cv.getContext("2d"), N = 100, s = cv.width / N;
  const rows = L.byBlock.get(block) || [];
  grid.block = block; grid.focus = focus;
  grid.cells = new Map(rows.map(([i, r]) => [i, r]));
  const col = { rep: css("--signal"), spoof: css("--clear"), dim: css("--dim"), paper: css("--paper"), ink: css("--ink") };
  const paintBase = () => {
    ctx.fillStyle = col.paper; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = col.dim;
    for (let i = 0; i < N * N; i++) ctx.fillRect((i % N) * s, Math.floor(i / N) * s, s - 1, s - 1);
  };
  const paint = (upto) => {
    for (let k = 0; k < upto; k++) {
      const [i, r] = rows[k];
      ctx.fillStyle = r.code === "s" ? col.spoof : col.rep;
      ctx.fillRect((i % N) * s, Math.floor(i / N) * s, s - 1, s - 1);
    }
  };
  const ring = () => {
    if (focus < 0) return;
    ctx.strokeStyle = col.ink; ctx.lineWidth = 2;
    ctx.strokeRect((focus % N) * s - 3, Math.floor(focus / N) * s - 3, s + 5, s + 5);
  };
  paintBase();
  if (!animate || reducedMotion || !rows.length) { paint(rows.length); ring(); return; }
  // the one moment of motion on the page: the reported numbers of this range light up
  rows.sort(() => Math.random() - 0.5);
  const t0 = performance.now(), dur = 650;
  (function step(t) {
    const k = Math.min(rows.length, Math.ceil(rows.length * Math.min(1, (t - t0) / dur)));
    paintBase(); paint(k);
    if (k < rows.length) requestAnimationFrame(step); else ring();
  })(t0);
}

function caption(L, block) {
  const rows = L.byBlock.get(block) || [], b = L.blocks.get(block);
  const reported = rows.length, spoof = rows.filter(([, r]) => r.code === "s").length;
  const reports = rows.reduce((a, [, r]) => a + r.reports, 0);
  $("#grid-cap").innerHTML = reported
    ? `<b>${esc(rangeOf(block))}</b>: ${reported === 1 ? "1 of its 10,000 numbers was" : `${fmt(reported)} of its 10,000 numbers were`}
       reported, ${reports === 1 ? "once" : `${fmt(reports)} times in all`}.
       ${b ? "This range meets the complaint concentration threshold." : spoof === reported ? "Each reported number has an area-code match; this is not proof of spoofing." : "Too few numbers meet the threshold for a concentration."}`
    : `<b>${esc(rangeOf(block))}</b>: none of its 10,000 numbers were reported.`;
}

const VERDICT = {
  s: ["likely_spoofed", "Area-code match in reports", "The caller and consumer area codes match in each report. This may indicate spoofing, but it does not prove it or identify the caller."],
  p: ["pool", "In a range with concentrated complaints", "Several numbers in this range appear in complaints. This does not establish who made the calls or a common operator."],
  r: ["pool", "Reported again and again", "People in other area codes reported this one number many times."],
  "1": ["", "Reported once", "One report is weak evidence on its own."],
};
async function check(raw, example = false) {
  const n = String(raw).replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "");
  if (n.length !== 10) { $("#num-out").innerHTML = `<p>Enter a 10-digit US number, like 866-771-6581.</p>`; return; }
  if (!example) { $("#num-in").value = dash(n); history.replaceState(null, "", "?n=" + n + location.hash); }
  let L;
  if (!example) $("#num-out").innerHTML = `<p class="quiet">Loading the complaint lookup…</p>`;
  try { L = await loadLookup(); } catch { $("#num-out").innerHTML = `<p>The list of reported numbers didn't load. Check your connection and try again.</p>`; return; }
  const hit = L.nums.get(n), block = L.blocks.get(n.slice(0, 6));
  drawGrid(L, n.slice(0, 6), example ? -1 : +n.slice(6), true);
  caption(L, n.slice(0, 6));
  if (example) return;
  let html;
  if (hit) {
    const [cls, title, why] = VERDICT[hit.code] || VERDICT["1"];
    html = `<p class="verdict ${cls}">${title}</p><p>Reported ${fmt(hit.reports)} time${hit.reports > 1 ? "s" : ""} to the FTC between ${esc(L.span)}. ${why}</p>`;
  } else if (block) {
    html = `<p class="verdict pool">Not reported in this window, but its range has concentrated complaints</p><p>${fmt(block.numbers)} numbers from
      ${esc(rangeOf(n.slice(0, 6)))} were reported ${fmt(block.reports)} times.${data.eval ? ` In our test, ${fmt(data.eval.dropnet.new_numbers_caught)} later complaints involved numbers absent from the training reports.` : ""}</p>`;
  } else {
    html = `<p class="verdict">No reports for this number or its range</p><p class="quiet">Between ${esc(L.span)}. That doesn't prove the call was safe.</p>`;
  }
  $("#num-out").innerHTML = html + `<p class="links"><a href="?n=${n}">Link to this result</a>, or
    <a href="https://reportfraud.ftc.gov/" target="_blank" rel="noopener">report the call to the FTC</a>.</p>`
    + `<div class="caution">${esc(data.caution)}</div>`;
}
$("#num-form").addEventListener("submit", (e) => { e.preventDefault(); check($("#num-in").value); });

// hover and click on the range: every cell is a phone number
const tip = $("#grid-tip");
$("#grid").addEventListener("mousemove", (e) => {
  if (!grid.block) return;
  const r = e.target.getBoundingClientRect(), x = Math.floor(((e.clientX - r.left) / r.width) * 100), y = Math.floor(((e.clientY - r.top) / r.height) * 100);
  const i = y * 100 + x, rec = grid.cells.get(i), num = `${grid.block.slice(0, 3)}-${grid.block.slice(3)}-${String(i).padStart(4, "0")}`;
  tip.hidden = false;
  tip.style.left = `${e.clientX - r.left}px`; tip.style.top = `${e.clientY - r.top}px`;
  tip.textContent = rec ? `${num}: ${fmt(rec.reports)} report${rec.reports > 1 ? "s" : ""}${rec.code === "s" ? ", area-code match" : ""}` : `${num}: not reported`;
});
$("#grid").addEventListener("mouseleave", () => { tip.hidden = true; });
$("#grid").addEventListener("click", (e) => {
  if (!grid.block) return;
  const r = e.target.getBoundingClientRect(), x = Math.floor(((e.clientX - r.left) / r.width) * 100), y = Math.floor(((e.clientY - r.top) / r.height) * 100);
  check(grid.block + String(y * 100 + x).padStart(4, "0"));
});

const QUERIES = [
  ["Biggest ranges", "MATCH (c:Pool)-[:USES_BLOCK]->(b:Block)\nRETURN b.npa_nxx AS block, c.numbers AS numbers, c.reports AS reports\nORDER BY reports DESC LIMIT 10"],
  ["Ranges reaching the most states", "MATCH (c:Pool)-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(:Number)-[:CALLED_INTO]->(s:State)\nRETURN c.id AS pool, count(DISTINCT s) AS states ORDER BY states DESC LIMIT 10"],
  ["Scam types in these ranges", "MATCH (:Number)-[r:ABOUT]->(s:Subject)\nRETURN s.code AS scam_type, sum(r.reports) AS reports ORDER BY reports DESC"],
  ["Toll-free or local", "MATCH (c:Pool)\nRETURN c.toll_free AS toll_free, count(c) AS pools, sum(c.reports) AS reports"],
];
$("#q-samples").innerHTML = QUERIES.map(([l], i) => `<button data-i="${i}">${esc(l)}</button>`).join("");
$("#q-samples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("#q-text").value = QUERIES[b.dataset.i][1]; run(); }));
$("#q-text").value = QUERIES[0][1];
function run() {
  const t0 = performance.now();
  try {
    if (/\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP)\b/i.test($("#q-text").value)) throw new Error("This console only reads. Remove CREATE, MERGE, SET, DELETE, REMOVE or DROP and run it again.");
    const rows = q($("#q-text").value);
    const cols = rows.length ? Object.keys(rows[0]) : [];
    $("#q-meta").textContent = `${rows.length} rows in ${(performance.now() - t0).toFixed(1)} ms`;
    $("#q-out").innerHTML = rows.length ? `<table class="grid"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>`
      + rows.map((r) => `<tr>${cols.map((c) => `<td>${esc(typeof r[c] === "object" ? JSON.stringify(r[c]) : r[c])}</td>`).join("")}</tr>`).join("")
      + "</tbody></table>" : `<p class="quiet">The query returned no rows.</p>`;
  } catch (e) { $("#q-meta").textContent = ""; $("#q-out").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
$("#q-go").addEventListener("click", run);

(async function boot() {
  data = await (await fetch("data/graph.json")).json();
  renderStatic();
  const shared = new URLSearchParams(location.search).get("n");
  check(shared || "8667716581", !shared);  // the hero works before the graph engine has loaded
  await init();
  db = new RelateDb();
  loadGraph();
  renderList();
  renderNetworkAndWhatIf();
  run();
})().catch((e) => { $("#engine").textContent = "Relate didn't start: " + e.message; console.error(e); });
