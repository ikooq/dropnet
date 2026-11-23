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
const DATA_V = 15;  // bump with the data files so browsers and the Pages cache fetch fresh copies
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
      least ${rb.rolling_summary.min_lift.toFixed(1)} times as many reports every time, ${rb.rolling_summary.median_lift.toFixed(1)} times typically.` : ""}${ev.early_warning ? ` Replayed day by day, ${fmt(ev.early_warning.numbers_first_seen_after_flag)} numbers
      first appeared in a range that was already flagged, a median of ${ev.early_warning.days_first_complaint_to_flag.median} days after its first complaint.` : ""} The price: a range rule can affect up to
      10,000 numbers; legitimate-call impact is unknown.`;
  }
  $("#spoof-bars").innerHTML = data.profile.filter((p) => p.reports > 1000).sort((a, b) => b.neighbor_share - a.neighbor_share)
    .map((p) => hbar(esc(LABEL[p.subject] || p.label), p.neighbor_share, 1)).join("");
  $("#agent-note").textContent = "A historical agent experiment measured agreement with Dropnet's own labels and advice, not independently verified spoofing or correct blocking decisions.";
  $("#source").textContent = data.caution;
}

// one flagged range on a timeline: numbers appearing for the first time, before and after Dropnet flagged the range
const addDays = (d, k) => new Date(Date.parse(d + "T00:00:00Z") + k * 864e5).toISOString().slice(0, 10);
const daysBetween = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
function renderEarly() {
  const ew = data.eval?.early_warning, ex = ew?.example;
  if (!ex) return;
  const before = ex.numbers - ex.numbers_after_flag;
  $("#early-story").innerHTML = `On <b>${day(ex.first_day)}</b> one number from ${esc(rangeOf(ex.block))} was reported.
    By <b>${day(ex.flag_day)}</b>, ${fmt(before)} different numbers from it had been reported by consumers outside the caller's
    area code, enough for Dropnet to flag the range. Over the next ${daysBetween(ex.flag_day, ex.last_day)} days,
    <b>${fmt(ex.numbers_after_flag)} more numbers</b> from the same range appeared in complaints for the first time.
    No list of numbers could have contained them, because nobody had reported them yet. The range was already flagged.`;
  $("#early-note").textContent = `This is the clearest case, picked as ${ex.selection}. Across all ${fmt(ew.ranges_flagged)} ranges
    flagged in the replay, ${fmt(ew.numbers_first_seen_after_flag)} numbers first appeared after their range was flagged, which took a median
    of ${ew.days_first_complaint_to_flag.median} days from the first complaint. Each day is judged with the previous days' complaints only.`;
  $("#early-cap").textContent = `New numbers from ${rangeOf(ex.block)} per filing day, ${day(ex.window[0])} to ${day(ex.window[1], true)}.
    Grey: before the range was flagged. Red: after.`;
  $("#early").hidden = false;
  const svgW = $("#early-svg").getBoundingClientRect().width || 640;
  const n = daysBetween(ex.window[0], ex.window[1]) + 1, W = Math.round(Math.min(640, Math.max(300, svgW))), H = W < 480 ? 240 : 300, top = 34, base = H - 28, left = 8, right = 8;
  const byDay = new Map(ex.days.map((d) => [d.day, d.new_numbers]));
  const max = Math.max(...ex.days.map((d) => d.new_numbers)), bw = (W - left - right) / n, y = (v) => base - ((base - top) * v) / max;
  const x = (d) => left + daysBetween(ex.window[0], d) * bw;
  let bars = "";
  for (let i = 0; i < n; i++) {
    const d = addDays(ex.window[0], i), v = byDay.get(d) || 0;
    if (!v) continue;
    bars += `<rect class="${d > ex.flag_day ? "after" : "before"}" x="${(x(d) + 1).toFixed(1)}" y="${y(v).toFixed(1)}"
      width="${Math.max(1, bw - 2).toFixed(1)}" height="${(base - y(v)).toFixed(1)}"><title>${day(d)}: ${v} new number${v > 1 ? "s" : ""}</title></rect>`;
  }
  const fx = x(ex.flag_day) + bw, sx = x(ex.first_day) + bw / 2;
  const ticks = [ex.window[0], ex.window[1]].map((d, i) => `<text class="tick" x="${i ? W - right : left}" y="${H - 8}"
    text-anchor="${i ? "end" : "start"}">${day(d)}</text>`).join("");
  $("#early-svg").setAttribute("viewBox", `0 0 ${W} ${H}`);
  $("#early-svg").innerHTML = `<line class="axis" x1="${left}" x2="${W - right}" y1="${base}" y2="${base}"/>${bars}
    <line class="flag" x1="${fx}" x2="${fx}" y1="${top - 22}" y2="${base}"/>
    <text class="flag-label" x="${fx + 6}" y="${top - 10}">Flagged ${day(ex.flag_day)}</text>
    <circle class="first" cx="${sx}" cy="${base + 7}" r="3.5"/><text class="tick" x="${sx}" y="${H - 8}" text-anchor="middle">${x(ex.first_day) - left > 60 ? "first report" : ""}</text>
    <text class="tick" x="${W - right}" y="${top - 10}" text-anchor="end">${max} a day at most</text>${ticks}`;
  $("#early-show").onclick = () => { check(ex.block + "0000", true); $(".hero").scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" }); };
}
let earlyResize;
addEventListener("resize", () => { clearTimeout(earlyResize); earlyResize = setTimeout(() => data && renderEarly(), 200); });

// the pre-registered forward test: frozen lists, fixed test set and pass marks; result shown once it exists
let predRanges;
const loadPredRanges = () => predRanges ??= fetch("prediction/ranges.txt?v=" + DATA_V).then((r) => {
  if (!r.ok) throw new Error(r.status);
  return r.text();
}).then((t) => new Set(t.split(/\r?\n/).map((l) => l.split("\t")[0]).filter(Boolean)));
async function renderPrereg() {
  const get = (u) => fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  const m = await get("prediction/manifest.json?v=" + DATA_V);
  if (!m) return;
  const res = Date.now() >= Date.parse("2026-12-08T00:00:00Z") ? await get("prediction/result-2026-12-08.json") : null;
  const fr = m.frozen, tr = m.training, toll = fr.ranges - fr.geographic_ranges;
  $("#prereg-lede").textContent = `On ${day(m.frozen_on, true)}, Dropnet's rule was run on every FTC file published so far and its
    output was frozen in a public commit, with the test set and the pass marks written down before the complaints it will be
    judged on existed. Nothing is re-learned: the lists are scored exactly as they are.`;
  $("#prereg-facts").innerHTML = [
    ["Frozen", day(m.frozen_on, true)],
    ["Learned from", `${fmt(tr.reports)} complaints in ${tr.files} daily files, ${day(tr.first_file)} to ${day(tr.last_file)}`],
    ["Frozen lists", `${fmt(fr.geographic_ranges)} geographic ranges, ${fmt(toll)} toll-free ranges, ${fmt(fr.numbers)} repeat numbers`],
    ["Test set", `complaints filed after ${day(tr.last_filing_day)}, in files published after ${day(tr.last_file)}`],
    ["Scored", res ? `Dec 8, 2026, on ${fmt(res.filed_after_freeze.complaints)} complaints` : "Dec 8, 2026"],
  ].map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");
  const f = res?.filed_after_freeze, c = res?.called_after_freeze;
  const seen = f && f.never_seen_numbers.complaints ? f.never_seen_numbers.in_a_frozen_geographic_range / f.never_seen_numbers.complaints : null;
  const tests = [
    ["Numbers + geographic ranges match at least 2× the complaints that numbers alone match", f && f.lift_geographic,
      f && `${pct(f.shares.numbers_only)} → ${pct(f.shares.numbers_and_geographic_ranges)}, ${f.lift_geographic}×`, (v) => v >= 2],
    ["The same holds for calls made after the freeze", c && c.lift_geographic,
      c && `${pct(c.shares.numbers_only)} → ${pct(c.shares.numbers_and_geographic_ranges)}, ${c.lift_geographic}×`, (v) => v >= 2],
    ["At least 10% of complaints about never-seen numbers fall in a frozen geographic range", seen,
      seen !== null && pct(seen), (v) => v >= 0.1],
  ];
  $("#prereg-tests").innerHTML = tests.map(([t, v, shown, pass]) => {
    const st = v === null || v === undefined ? ["pending", "Scored Dec 8"] : pass(v) ? ["pass", `Passed: ${shown}`] : ["fail", `Failed: ${shown}`];
    return `<li><span>${esc(t)}</span><b class="status ${st[0]}">${esc(st[1])}</b></li>`;
  }).join("");
  $("#prereg-proof").innerHTML = `SHA-256 of the frozen range list: <code>${fr.ranges_sha256.slice(0, 16)}…</code>
    <a href="https://github.com/ikooq/dropnet/tree/main/docs/prediction" target="_blank" rel="noopener">Lists, hashes and protocol</a>.
    The result is published whatever it is.`;
  $("#prereg").hidden = false;
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
  nums.sort((a, b) => b.r - a.r || a.n.localeCompare(b.n));
  const displayedNums = nums.slice(0, 20);
  const displayedSet = new Set(displayedNums.map((x) => x.n));
  const states = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)-[r:CALLED_INTO]->(s:State)
                    RETURN n.number AS n, s.name AS s, r.reports AS c ORDER BY c DESC`, { id }).filter((x) => displayedSet.has(x.n));
  const subj = q(`MATCH (:Pool {id: $id})-[:USES_BLOCK]->(:Block)<-[:IN_BLOCK]-(n:Number)-[r:ABOUT]->(s:Subject)
                  RETURN n.number AS n, s.code AS s, r.reports AS c`, { id }).filter((x) => displayedSet.has(x.n));
  const topStates = new Set(Object.entries(states.reduce((m, x) => ((m[x.s] = (m[x.s] || 0) + x.c), m), {}))
     .sort((a, b) => b[1] - a[1]).slice(0, 6).map(([s]) => s));
  const topSubjects = new Set(Object.entries(subj.reduce((m, x) => ((m[x.s] = (m[x.s] || 0) + x.c), m), {}))
    .sort((a, b) => b[1] - a[1]).slice(0, 4).map(([s]) => s));
  const C = { Block: css("--c-block"), Number: css("--c-number"), State: css("--c-state"), Subject: css("--c-subject") };
  const nodes = new Map(), edges = [];
  const add = (i, kind, label, w) => nodes.has(i) || nodes.set(i, { data: { id: i, kind, label, color: C[kind], w } });
  for (const x of displayedNums) {
    add("B" + x.b, "Block", rangeOf(x.b), 40);
    add("N" + x.n, "Number", x.n.slice(-4), 8 + Math.min(26, Math.sqrt(x.r) * 2));
    edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "B" + x.b, type: "IN_BLOCK" } });
  }
  for (const x of states) if (topStates.has(x.s)) { add("S" + x.s, "State", x.s, 18); edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "S" + x.s, type: "CALLED_INTO" } }); }
  for (const x of subj) if (topSubjects.has(x.s)) { add("T" + x.s, "Subject", LABEL[x.s] || x.s, 18); edges.push({ data: { id: `e${edges.length}`, source: "N" + x.n, target: "T" + x.s, type: "ABOUT" } }); }
  if (cy) cy.destroy();
  cy = cytoscape({ container: $("#ftc-graph"), elements: [...nodes.values(), ...edges], wheelSensitivity: 0.25,
    style: [{ selector: "node", style: { "background-color": "data(color)", label: "data(label)", width: "data(w)", height: "data(w)",
        "font-size": 9, "font-family": "Archivo, sans-serif", color: css("--ink"), "text-valign": "bottom", "text-margin-y": 3 } },
      { selector: "node[kind = 'Block'], node[kind = 'State'], node[kind = 'Subject']", style: { shape: "round-rectangle", "font-size": 11, "font-weight": 700 } },
      { selector: "node[kind = 'Number'], node[kind = 'State'], node[kind = 'Subject']", style: { label: "" } },
      { selector: "edge", style: { width: 1, "line-color": css("--rule"), "curve-style": "haystack" } },
      { selector: "edge[type = 'IN_BLOCK']", style: { width: 1.5, "line-color": css("--muted") } }],
    layout: { name: "cose", animate: false, nodeRepulsion: 14000, idealEdgeLength: 70, padding: 24 } });
  $("#graph-detail").textContent = "Select a state or category to see its name; select a number to check it.";
  cy.on("tap", "node[kind = 'State'], node[kind = 'Subject']", (e) => {
    const item = e.target.data();
    $("#graph-detail").textContent = `${item.kind === "State" ? "Consumer state" : "Complaint category"}: ${item.label}`;
  });
  cy.on("tap", "node[kind = 'Number']", (e) => { check(e.target.id().slice(1)); $(".hero").scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" }); });
  $("#legend").innerHTML = [["Range", C.Block], ["Reported number (tap to check)", C.Number], ["Consumer state", C.State], ["Complaint category", C.Subject]]
    .map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("");
}

// ---- the hero: one number, and the 10,000-number range it belongs to ----
// docs/data/lookup.txt: every reported number + every pool block (~1 MB gzipped), fetched once.
let lookupPromise = null;
function loadLookup() {
  return lookupPromise ??= fetch("data/lookup.txt?v=" + DATA_V).then((r) => {
    if (!r.ok) throw new Error(`Lookup request failed: ${r.status}`);
    return r.text();
  }).then((text) => {
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
    if (!span || nums.size === 0) throw new Error("Lookup data is empty or invalid");
    return { nums, blocks, byBlock, span };
  }).catch((error) => {
    lookupPromise = null;
    throw error;
  });
}

let dateQualityPromise = null;
function loadDateQuality() {
  return dateQualityPromise ??= fetch("data/date-quality.json?v=" + DATA_V).then((r) => {
    if (!r.ok) throw new Error(`Date quality request failed: ${r.status}`);
    return r.json();
  }).then((d) => {
    if (!d.issues || d.reports !== data.summary.reports || d.first_day !== data.summary.first_day || d.last_day !== data.summary.last_day)
      throw new Error("Date quality data does not match the graph snapshot");
    return d.issues;
  }).catch((e) => { dateQualityPromise = null; throw e; });
}

const grid = { block: null, cells: null, focus: -1, animation: 0 };
function drawGrid(L, block, focus, animate) {
  const cv = $("#grid"), ctx = cv.getContext("2d"), N = 100, s = cv.width / N;
  const rows = L.byBlock.get(block) || [];
  const animation = ++grid.animation;
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
    if (animation !== grid.animation) return;
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
  r: ["pool", "Reported again and again", "This number appears in three or more reports in the loaded window."],
  "1": ["", "Reported once", "One report is weak evidence on its own."],
};
let latestLookup = 0;
async function check(raw, example = false) {
  const request = ++latestLookup;
  const n = String(raw).replace(/\D/g, "").replace(/^1(?=\d{10}$)/, "");
  if (!/^[2-9]\d{9}$/.test(n)) { $("#num-out").innerHTML = `<p>Enter a 10-digit US or Canadian number, like 866-771-6581.</p>`; return; }
  if (!example) { $("#num-in").value = dash(n); history.replaceState(null, "", "?n=" + n + location.hash); }
  let L;
  if (!example) $("#num-out").innerHTML = `<p class="quiet">Loading the complaint lookup…</p>`;
  try { L = await loadLookup(); } catch {
    if (request === latestLookup && !example) $("#num-out").innerHTML = `<p>The list of reported numbers didn't load. Check your connection and try again.</p>`;
    return;
  }
  if (request !== latestLookup) return;
  const hit = L.nums.get(n), block = L.blocks.get(n.slice(0, 6));
  let dateIssues = null;
  if (!example && hit) {
    try { dateIssues = await loadDateQuality(); } catch { /* unavailable is not equivalent to no issues */ }
    if (request !== latestLookup) return;
  }
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
    const otherReported = (L.byBlock.get(n.slice(0, 6)) || []).length;
    html = `<p class="verdict">No reports for this number in the loaded window</p><p class="quiet">Between ${esc(L.span)}. ${otherReported ? `${fmt(otherReported)} other number${otherReported === 1 ? "" : "s"} in this range ${otherReported === 1 ? "was" : "were"} reported, but the range does not meet the pool threshold. ` : "No numbers in this range were reported in the loaded window. "}That doesn't prove the call was safe.</p>`;
  }
  if (hit) {
    if (!dateIssues) html += `<div class="caution">Date-quality check is unavailable. Do not assume the reported dates are consistent.</div>`;
    else {
      const issue = dateIssues[n];
      if (issue?.call_after_filing) html += `<div class="caution">Date warning: ${fmt(issue.call_after_filing)} complaint(s) have a reported call date later than filing. Source values are unchanged; cause unknown.<ul>${issue.examples.map((x) => `<li>Report ${esc(x.report_id)}: filed ${esc(x.filing_date)}, reported call ${esc(x.reported_call_date)}</li>`).join("")}</ul>Showing up to five examples.</div>`;
      if (issue && (issue.missing || issue.invalid)) html += `<div class="caution">Date check unavailable for ${fmt(issue.missing)} missing and ${fmt(issue.invalid)} invalid date pair(s).</div>`;
      if (!issue) html += `<p class="quiet">No date inconsistencies or missing dates were found for this number in the loaded snapshot.</p>`;
    }
  }
  try {
    const frozen = await loadPredRanges();
    if (request !== latestLookup) return;
    if (frozen.has(n.slice(0, 6))) html += `<p class="quiet">This range is on the list Dropnet froze on Nov 23 for its
      <a href="#prereg">pre-registered test</a>.</p>`;
  } catch { /* the frozen list is optional here */ }
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
  data = await (await fetch("data/graph.json?v=" + DATA_V)).json();
  renderStatic();
  renderEarly();
  renderPrereg();
  const shared = new URLSearchParams(location.search).get("n");
  check(shared || "8667716581", !shared);  // the hero works before the graph engine has loaded
  await init();
  db = new RelateDb();
  loadGraph();
  renderList();
  renderNetworkAndWhatIf();
  run();
})().catch((e) => { $("#engine").textContent = "Relate didn't start: " + e.message; console.error(e); });
