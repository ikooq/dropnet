"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(body?.detail || body || r.statusText);
  return body;
}
const post = (path, data) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(data) });

/* ---------------------------------------------------------------- tabs */
function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  if (name === "real" && ftcCy) setTimeout(() => ftcCy.resize() && ftcCy.fit(undefined, 24), 0);
  history.replaceState(null, "", `#${name}`);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

/* ---------------------------------------------------------------- query */
const QUERIES = [
  ["Largest complaint ranges", `MATCH (p:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)
RETURN b.npa_nxx AS range, p.reports AS reports, p.numbers AS distinct_numbers
ORDER BY reports DESC, range LIMIT 15`],
  ["Operators by flagged ranges", `MATCH (:FtcCampaign {kind: 'pool'})-[:USES_BLOCK]->(b:Block)-[:HELD_BY]->(c:Carrier)
RETURN c.ocn AS ocn, c.name AS holder, count(DISTINCT b) AS flagged_ranges
ORDER BY flagged_ranges DESC, ocn LIMIT 15`],
  ["Ranges sharing the 217-834 holder", `MATCH (:Block {npa_nxx: '217834'})-[:HELD_BY]->(c:Carrier)<-[:HELD_BY]-(b:Block)
MATCH (b)<-[:USES_BLOCK]-(p:FtcCampaign {kind: 'pool'})
WHERE b.npa_nxx <> '217834'
OPTIONAL MATCH (b)-[:IN_RATE_CENTER]->(rc:RateCenter)
RETURN b.npa_nxx AS related_range, c.ocn AS ocn, c.name AS holder, rc.name AS rate_center, p.reports AS reports
ORDER BY reports DESC, related_range LIMIT 15`],
  ["Assignments within a range", `MATCH (b:Block {npa_nxx: '201201'})<-[:PART_OF]-(s:SubBlock)-[:ASSIGNED_TO]->(c:Carrier)
RETURN s.id AS thousands_block, c.ocn AS ocn, c.name AS assignee ORDER BY thousands_block`],
];
$("#q-samples").innerHTML = QUERIES.map(([l], i) => `<button data-i="${i}">${esc(l)}</button>`).join("");
$("#q-samples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("#q-text").value = QUERIES[b.dataset.i][1]; runQuery(); }));
$("#q-text").value = QUERIES[0][1];
async function runQuery() {
  const t0 = performance.now();
  try {
    const r = await post("api/ftc/cypher", { statement: $("#q-text").value });
    $("#q-meta").textContent = `${r.rows.length} rows · ${Math.round(performance.now() - t0)} ms round-trip${r.truncated ? " · truncated" : ""}`;
    $("#q-out").innerHTML = r.rows.length ? `<table class="grid"><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>` +
      r.rows.map((row) => `<tr>${r.columns.map((c) => `<td class="mono">${esc(typeof row[c] === "object" ? JSON.stringify(row[c]) : row[c])}</td>`).join("")}</tr>`).join("") +
      "</tbody></table>" : `<p class="muted">No rows.</p>`;
  } catch (e) { $("#q-meta").textContent = ""; $("#q-out").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
}
$("#q-go").addEventListener("click", runQuery);

/* ------------------------------------------------------- real FTC data */
let ftcCy = null, ftcCampaigns = [], ftcSplit = null;
const pct = (x) => `${(100 * x).toFixed(1)}%`;
const fmtNum = (n) => String(n).replace(/(\d{3})(\d{3})(\d{4})/, "$1-$2-$3");
function hbar(label, value, max, ours) {
  return `<div class="hbar ${ours ? "ours" : ""}"><span>${label}</span><div class="track"><div class="fill"
    style="width:${Math.max(1, (100 * value) / max)}%"></div></div><span class="v">${pct(value)}</span></div>`;
}

const carrierCount = new Intl.NumberFormat("en-US");
const carrierRate = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const carrierTotals = ["flagged", "ranges_held", "reports", "numbers", "ocns", "states"];

function showCarrierCaution(caution) {
  const note = $("#carrier-caution");
  note.textContent = caution;
  note.hidden = false;
}

async function loadCarriers() {
  const status = $("#carrier-status");
  try {
    const { carriers, caution } = await api("api/ftc/carriers?limit=15");
    showCarrierCaution(caution);
    if (!carriers.length) {
      status.textContent = "No carrier assignments are available in this snapshot.";
      return;
    }
    $("#carrier-ranking tbody").innerHTML = carriers.map((c) => `<tr class="clickable">
      <th scope="row"><button type="button" data-carrier="${esc(c.carrier)}" aria-controls="carrier-detail">${esc(c.carrier)}</button></th>
      <td class="num carrier-rate">${c.flagged_per_100_ranges == null ? "—" : carrierRate.format(c.flagged_per_100_ranges)}</td>
      ${carrierTotals.map((key) => `<td class="num">${carrierCount.format(c[key])}</td>`).join("")}
    </tr>`).join("");
    $("#carrier-ranking").hidden = false;
    status.hidden = true;
  } catch {
    status.textContent = "Carrier assignments could not be loaded.";
  }
}

let carrierRequest = 0;
$("#carrier-ranking tbody").addEventListener("click", async (event) => {
  const button = event.target.closest("tr")?.querySelector("button[data-carrier]");
  if (!button) return;
  const request = ++carrierRequest;
  const output = $("#carrier-detail");
  const name = button.dataset.carrier;
  $("#carrier-ranking [aria-current]")?.removeAttribute("aria-current");
  button.setAttribute("aria-current", "true");
  output.textContent = `Loading ${name}…`;
  try {
    const { carrier, ranges, subjects, caution } = await api(`api/ftc/carriers/${encodeURIComponent(name)}`);
    if (request !== carrierRequest) return;
    showCarrierCaution(caution);
    const subjectList = subjects.length
      ? `<ul>${subjects.map((s) => `<li>${esc(s.subject)} · ${carrierCount.format(s.reports)} reports</li>`).join("")}</ul>`
      : '<p class="muted">No complaint subjects in the listed ranges.</p>';
    const rangeList = ranges.length
      ? `<div class="carrier-scroll" role="region" aria-label="Flagged carrier ranges" tabindex="0">
        <table class="grid carrier-ranges"><thead><tr>
          <th scope="col">Range</th><th scope="col">Rate center</th><th scope="col">State</th>
          <th scope="col" class="num">Reports</th><th scope="col" class="num">Reported numbers</th><th scope="col">OCN</th>
        </tr></thead><tbody>${ranges.map((r) => `<tr>
          <th scope="row">${esc(r.block.slice(0, 3))}-${esc(r.block.slice(3))}</th>
          <td>${esc(r.rate_center || "—")}</td><td>${esc(r.state || "—")}</td>
          <td class="num">${carrierCount.format(r.reports)}</td><td class="num">${carrierCount.format(r.numbers)}</td>
          <td>${esc(r.ocn)}</td>
        </tr>`).join("")}</tbody></table></div>`
      : '<p class="muted">No flagged ranges for this holder.</p>';
    output.innerHTML = `<h3>${esc(carrier)}</h3><h4>Top complaint subjects in these ranges</h4>${subjectList}
      <h4>Flagged ranges</h4>${rangeList}`;
  } catch {
    if (request !== carrierRequest) return;
    output.textContent = `The flagged ranges for ${name} could not be loaded.`;
  }
  output.focus();
});

async function loadReal() {
  let s;
  try { s = await api("api/ftc/summary"); } catch (e) {
    $("#real-lede").innerHTML = `Real FTC data is not built yet — run <code>python -m dropnet ftc-build</code>.`; return false;
  }
  const stats = [["FTC reports", s.reports], ["reported numbers", s.numbers], ["number pools", s.campaigns.pool || 0]];
  $("#stats").innerHTML = stats.map(([label, count]) => `<div class="stat"><b>${count.toLocaleString()}</b><span>${label}</span></div>`).join("");
  $("#real-lede").innerHTML = `<b>${s.reports.toLocaleString()}</b> real complaints about unwanted calls, filed with the US
    Federal Trade Commission between ${esc(s.first_day)} and ${esc(s.last_day)}, live in one Relate file. Most reported numbers appeared only once; ranges offer another way to explore patterns.`;
  $("#real-kpis").innerHTML = [[s.reports.toLocaleString(), "reports"], [s.numbers.toLocaleString(), "reported numbers"],
    [pct(s.single_report_numbers_share), "numbers reported only once"], [pct(s.neighbor_share), "area codes match"],
    [(s.campaigns.pool || 0).toLocaleString(), "number pools found"]].map(([v, l]) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join("");
  const ev = s.eval;
  if (ev) {
    ftcSplit = ev.split_day;
    const max = Math.max(ev.dropnet.coverage, ev.blocklist_all_seen.coverage);
    $("#eval-caption").innerHTML = `Rules learned from reports before ${esc(ev.split_day)} (${ev.train_reports.toLocaleString()}),
      scored on the ${ev.test_reports.toLocaleString()} reports that came after. Share of later-filed reports matching each rule set (not necessarily calls after the split):`;
    $("#eval-bars").innerHTML = hbar(`Block every number ever reported (${ev.blocklist_all_seen.rules.toLocaleString()} rules)`, ev.blocklist_all_seen.coverage, max)
      + hbar(`Blocklist: numbers with ≥2 reports (${ev.baseline.rules.toLocaleString()})`, ev.baseline.coverage, max)
      + (ev.dropnet_geographic ? hbar(`<b>Dropnet</b>, geographic pool blocks only (+${ev.dropnet_geographic.block_rules.toLocaleString()})`, ev.dropnet_geographic.coverage, max, true) : "")
      + (ev.naive_geographic ? hbar(`Naive: same number of geographic ranges`, ev.naive_geographic.coverage, max) : "")
      + hbar(`<b>Dropnet</b>, all pool blocks incl. toll-free (+${ev.dropnet.block_rules.toLocaleString()})`, ev.dropnet.coverage, max, true)
      + `<p class="muted">${ev.dropnet.new_numbers_caught.toLocaleString()} matching reports involved numbers absent from training. The price: a
        block rule can affect up to 10,000 possible numbers in its range (${(ev.dropnet.numbers_blocked / 1e6).toFixed(1)} M numbers vs
        ${ev.baseline.numbers_blocked.toLocaleString()} for the blocklist), and toll-free ranges are shared by many businesses — legitimate-call impact is unknown.</p>`;
    if (ev.naive_geographic) {
      $("#eval-bars").innerHTML += `<p class="muted">At the same geographic prefix budget, matches per million possible numbers were
        <b>${ev.dropnet_geographic.matches_per_million_numbers.toFixed(1)}</b> for Dropnet and
        <b>${ev.naive_geographic.matches_per_million_numbers.toFixed(1)}</b> for the naive ranking.</p>`;
    }
  }
  const prof = s.profile.filter((p) => p.reports > 1000).sort((a, b) => b.neighbor_share - a.neighbor_share);
  $("#spoof-bars").innerHTML = prof.map((p) => hbar(esc(p.label), p.neighbor_share, 1)).join("");
  const nets = await api("api/ftc/networks");
  if (nets.length) {
    const n = nets[0];
    $("#net-panel").style.display = "";
    $("#net-panel").innerHTML = `<h2>${n.pools} ranges with related complaint patterns</h2>
      <p class="muted">Reports share consumer area codes, filing days and categories at least 10 times per pair. This does not prove a common operator. Read straight off the graph: Pool → Block → Number → Report → AreaCode ← Report ← … ← Pool.</p>
      <p><b>${n.reports.toLocaleString()}</b> reports · <b>${(n.numbers || 0).toLocaleString()}</b> reported numbers</p>
      <div class="whatif-pick">${n.members.map((m) => `<label data-id="${esc(m.id)}" style="cursor:pointer">${esc(m.id.replace("POOL-", ""))} · ${m.reports.toLocaleString()}</label>`).join("")}</div>`;
    $("#net-panel").querySelectorAll("label[data-id]").forEach((l) => l.addEventListener("click", () => openFtc(l.dataset.id)));
  }
  ftcCampaigns = await api("api/ftc/campaigns?limit=40&kind=pool");
  $("#ftc-list").innerHTML = ftcCampaigns.map((c) => `<button class="camp-card" data-id="${esc(c.id)}">
    <div class="id">${esc(c.id.replace("POOL-", "Pool "))}</div>
    <div class="meta">${c.numbers} numbers · ${c.reports.toLocaleString()} reports · ${c.states} states</div>
    <div class="meta">${esc((c.subjects || []).join(", "))}${c.toll_free ? " · toll-free" : ""}</div></button>`).join("");
  $("#ftc-list").querySelectorAll(".camp-card").forEach((b) => b.addEventListener("click", () => openFtc(b.dataset.id)));
  const initial = ftcCampaigns.find((c) => !c.toll_free) || ftcCampaigns[0];
  if (initial) await openFtc(initial.id);
  return true;
}
async function openFtc(id) {
  document.querySelectorAll("#ftc-list .camp-card").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const g = await api(`api/ftc/campaigns/${id}/graph`);
  const k = g.campaign, blk = id.replace("POOL-", "");
  $("#ftc-head").innerHTML = `<h2>${esc(blk.slice(0, 3))}-${esc(blk.slice(3))}-xxxx</h2>
    <span class="badge">${k.numbers} numbers</span><span class="badge">${k.reports.toLocaleString()} reports</span>
    <span class="badge">${k.states} states</span><span class="badge">${esc(k.first_day || "")} → ${esc(k.last_day || "")}</span>
    <span class="spacer"></span><a href="api/ftc/campaigns/${esc(id)}/export"><button>Download case (.rl)</button></a>`;
  const C = { Block: css("--c-cashout"), Number: css("--c-card"), State: css("--c-phone"), Subject: css("--c-persona"),
    Carrier: "#11726a", RateCenter: "#836736", RelatedBlock: "#42679c" };
  // Readability: only the busiest numbers carry a label; state / scam-type labels are short and sit on a backdrop.
  const topNums = new Set(g.nodes.filter((n) => n.kind === "Number").sort((a, b) => (b.reports || 0) - (a.reports || 0)).slice(0, 8).map((n) => n.id));
  const short = (n) => n.kind === "Subject" ? (n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label)
    : n.kind === "Number" ? (topNums.has(n.id) ? n.label : "") : n.label;
  const els = [...g.nodes.map((n) => ({ data: { id: n.id, label: short(n), kind: n.kind, color: C[n.kind], w: n.kind === "Number" ? 8 + Math.min(22, Math.sqrt(n.reports || 1) * 1.6) : 16, raw: n } })),
    ...g.edges.map((e, i) => ({ data: { id: `f${i}`, source: e.source, target: e.target, type: e.type } }))];
  if (ftcCy) ftcCy.destroy();
  ftcCy = cytoscape({ container: $("#ftc-graph"), elements: els, wheelSensitivity: 0.25,
    style: [{ selector: "node", style: { "background-color": "data(color)", label: "data(label)", width: "data(w)", height: "data(w)", "font-size": 8, color: css("--ink"), "text-valign": "bottom", "text-margin-y": 2 } },
      { selector: "node[kind = 'Block']", style: { shape: "round-rectangle", width: 40, height: 40, "font-weight": 700, "font-size": 11 } },
      { selector: "node[kind = 'State'], node[kind = 'Subject'], node[kind = 'Carrier'], node[kind = 'RateCenter'], node[kind = 'RelatedBlock']", style: { shape: "round-rectangle", "font-size": 8,
        "text-background-color": css("--panel"), "text-background-opacity": 0.85, "text-background-padding": 2 } },
      { selector: "edge", style: { width: 0.6, "line-color": css("--line"), "curve-style": "haystack", opacity: 0.6 } },
      { selector: "edge[type = 'IN_BLOCK']", style: { width: 1.6, "line-color": C.Block, opacity: 0.8 } },
      { selector: "edge[type = 'HELD_BY'], edge[type = 'IN_RATE_CENTER']", style: { width: 1.6, "line-color": C.Carrier, opacity: 0.8 } }],
    layout: { name: "cose", animate: false, nodeRepulsion: 40000, idealEdgeLength: 110, nodeOverlap: 20, padding: 30 } });
  ftcCy.on("tap", "node[kind = 'Number']", (e) => assess(e.target.data("raw").number));
  ftcCy.on("tap", "node[kind = 'RelatedBlock']", (e) => openFtc(e.target.data("raw").campaign));
  const legend = [["Block (NPA-NXX)", C.Block], ["Reported number", C.Number], ["Victim state", C.State], ["Complaint category", C.Subject]];
  if (g.numbering?.ocn) legend.push(["Code holder", C.Carrier]);
  if (g.numbering?.rate_center) legend.push(["Rate center", C.RateCenter]);
  if (g.numbering?.related.length) legend.push(["Shared OCN (select to open range)", C.RelatedBlock]);
  $("#ftc-legend").innerHTML = legend
    .map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("") + "<span>node size = reports</span>";
  $("#ftc-numbering").hidden = !g.numbering;
  $("#ftc-numbering").textContent = g.numbering ? [
    g.numbering.ocn && `Code holder: ${g.numbering.holder} (OCN ${g.numbering.ocn}).`,
    g.numbering.rate_center && `Rate center: ${g.numbering.rate_center}.`,
    "Shared OCN describes a numbering assignment. It does not establish who placed a call."
  ].filter(Boolean).join(" ") : "";
  const picks = [k, ...ftcCampaigns.filter((c) => c.id !== id).slice(0, 11)];
  $("#ftc-whatif").innerHTML = `<b>How many later-filed reports match these ranges?</b>
    <div class="whatif-pick">${picks.map((c) => `<label><input type="checkbox" value="${esc(c.id.replace("POOL-", ""))}" ${c.id === id ? "checked" : ""}> ${esc(c.id.replace("POOL-", ""))}</label>`).join("")}</div>
    <button class="primary" id="whatif-go">Run what-if</button> <span class="muted">Runs inside a Relate transaction, then rolls back — nothing is written.</span>
    <div id="whatif-out"></div>`;
  $("#whatif-go").addEventListener("click", async () => {
    const blocks = [...document.querySelectorAll(".whatif-pick input:checked")].map((x) => x.value);
    try {
      const r = await post("api/ftc/whatif", { blocks, since_day: ftcSplit });
      $("#whatif-out").innerHTML = `<p>Reports filed from ${esc(ftcSplit || "the first day")}: <b>${r.reports_stopped.toLocaleString()}</b> from
        <b>${r.numbers_with_reports_in_period.toLocaleString()}</b> reported numbers matched ${r.applied_rules} block rule${r.rules > 1 ? "s" : ""}
        (each block covers 10,000 numbers); ${r.campaigns_touched.length} campaigns touched.
        ${r.spoofed_reports_in_scope ? `<br><span class="muted">${r.spoofed_reports_in_scope.toLocaleString()} matching reports had matching area codes; this does not prove spoofing.</span>` : ""}</p>`;
    } catch (e) { $("#whatif-out").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  });
}
let latestAssessment = 0;
async function assess(number) {
  const request = ++latestAssessment;
  $("#num-in").value = fmtNum(number);
  $("#num-out").textContent = "Checking the loaded FTC reports…";
  let a;
  try {
    if (!String(number).trim()) throw new Error("Enter a 10-digit US or Canadian number.");
    a = await api(`api/ftc/number/${encodeURIComponent(number)}`);
  } catch (e) {
    if (request === latestAssessment) $("#num-out").innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }
  if (request !== latestAssessment) return;
  const label = { likely_spoofed: "Area-code match", pool: "Part of a number pool", repeat: "Repeatedly reported", single: "Reported", unknown: "Not in the reports" }[a.verdict];
  $("#num-out").innerHTML = `<p class="verdict ${a.verdict}">${label}</p>` + (a.reports ? `<p>${a.reports.toLocaleString()} reports ·
    ${a.states} states · ${esc((a.subjects || []).join(", "))} · ${pct(a.neighbor_share)} area-code match · block ${esc(a.block)} has
    ${a.block_numbers} reported numbers meeting pool criteria · ${esc(a.first_day)} → ${esc(a.last_day)}</p>` +
    (a.repeated_number_signal ? `<p>This number appears in at least 3 complaints. Repeated reports are a lead for review, not proof of wrongdoing or independent callers.</p>` : "") +
    (a.date_quality?.call_after_filing ? `<div class="caution">Date warning: ${a.date_quality.call_after_filing} complaint(s) report a call date later than the filing date. Source values are unchanged; the cause is unknown.<ul>${a.date_quality.examples.map(x => `<li>Report ${esc(x.report_id)}: filed ${esc(x.filing_date)}, reported call ${esc(x.reported_call_date)}</li>`).join("")}</ul>Showing up to five examples.</div>` : "") +
    (a.date_quality && (a.date_quality.missing || a.date_quality.invalid) ? `<div class="caution">Date check unavailable for ${a.date_quality.missing} missing and ${a.date_quality.invalid} invalid date pair(s).</div>` : "") :
    a.in_pool_range ? `<p>No reports for this number in the loaded window; its range contains ${a.block_numbers} reported numbers meeting the pool criteria. This does not establish who called.</p>` : "") + `<div class="caution">${esc(a.caution)}</div>`;
  document.querySelector(".lookup").scrollIntoView({ behavior: "smooth", block: "center" });
}
$("#num-go").addEventListener("click", () => assess($("#num-in").value));
$("#num-in").addEventListener("keydown", (e) => { if (e.key === "Enter") assess($("#num-in").value); });

/* ----------------------------------------------------------------- boot */
(async function boot() {
  showTab(location.hash === "#query" ? "query" : "real");
  await Promise.all([loadReal(), loadCarriers()]);
})();
