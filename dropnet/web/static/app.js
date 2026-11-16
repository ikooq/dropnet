"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const kzt = (v) => `${Number(v || 0).toLocaleString("en-US")} KZT`;
const TACTIC = { BANK_SECURITY: "Fake bank security", SAFE_ACCOUNT: "'Safe account'", LOAN_STATUS_SMS: "Loan-status SMS",
  MARKETPLACE_PREPAY: "Marketplace prepay", POLICE_THREAT: "Fake police", INVESTMENT: "Fake investment",
  ATM_DROP_HELP: "ATM mule request" };
const REGIONS = ["Astana", "Almaty", "Shymkent", "Pavlodar", "Karaganda", "Aktobe", "Atyrau", "Kostanay", "Oskemen",
  "Semey", "Taraz", "Kyzylorda", "Aktau", "Petropavl", "Oral", "Turkistan", "Taldykorgan"];
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
  if (name === "campaigns" && cy) setTimeout(() => cy.resize() && cy.fit(undefined, 30), 0);
  if (name === "real" && ftcCy) setTimeout(() => ftcCy.resize() && ftcCy.fit(undefined, 24), 0);
  history.replaceState(null, "", `#${name}`);
}
document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));

async function refreshStats() {
  const h = await api("api/health");
  $("#stats").innerHTML = [["complaints", h.complaints], ["campaigns", h.campaigns], ["linked damage", kzt(h.damage_kzt)]]
    .map(([k, v]) => `<div class="stat"><b>${esc(v)}</b><span>${k}</span></div>`).join("");
}

/* ---------------------------------------------------------- path view */
function hopsHtml(ev) {
  if (!ev || !ev.found) return "";
  if (ev.similarity != null) {
    return `<div class="path"><span class="hop">${esc(ev.hops[0].key)}</span><span class="rel">≈ same script ${ev.similarity} ≈</span>
      <span class="hop">${esc(ev.hops[1].key)}</span></div>`;
  }
  let html = `<div class="path"><span class="hop Complaint">${esc(ev.hops[0].key)}</span>`;
  ev.rels.forEach((rel, i) => {
    const h = ev.hops[i + 1];
    html += `<span class="rel">${ev.forward[i] ? `—${rel}→` : `←${rel}—`}</span>`;
    html += `<span class="hop ${esc(h.label)} ${esc(h.role || "")}" title="${esc(h.label)}${h.role ? " · " + esc(h.role) : ""}">${esc(h.key)}</span>`;
  });
  return html + "</div>";
}
const quotesHtml = (qs) => (qs || []).map((q) => `<blockquote><b>${esc(q.complaint)}</b>: «${esc(q.quote)}»</blockquote>`).join("");

/* -------------------------------------------------------- new complaint */
const regionSel = $("#ing-region");
regionSel.innerHTML = REGIONS.map((r) => `<option ${r === "Pavlodar" ? "selected" : ""}>${r}</option>`).join("");

async function loadSamples() {
  const samples = await api("api/samples");
  $("#samples").innerHTML = samples.map((s, i) => `<button data-i="${i}" title="Expected: ${esc(s.expect)}">${esc(s.label)}</button>`).join("");
  $("#samples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    $("#ing-text").value = samples[b.dataset.i].text;
    $("#ing-text").focus();
  }));
}

$("#ing-go").addEventListener("click", async () => {
  const btn = $("#ing-go"), out = $("#ing-result");
  btn.disabled = true;
  try {
    const r = await post("api/ingest", { text: $("#ing-text").value, region: regionSel.value });
    out.innerHTML = await renderIngest(r);
    out.querySelectorAll("[data-open]").forEach((a) => a.addEventListener("click", (e) => {
      e.preventDefault(); openCampaign(a.dataset.open);
    }));
    refreshStats(); loadCampaignList(); inboxPage = 0; loadInbox();
  } catch (e) {
    out.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  } finally { btn.disabled = false; }
});

async function renderIngest(r) {
  const label = { attached: "Linked", bridge: "Bridge between campaigns", new_campaign: "New campaign", unlinked: "Not linked yet" }[r.status];
  let html = `<span class="status ${r.status}">${label}</span>`;
  if (r.campaign_id) {
    const g = await api(`api/campaigns/${r.campaign_id}/graph`);
    const k = g.campaign;
    html += `<div class="headline">${esc(r.complaint_id)} is part of <a href="#" data-open="${esc(k.id)}">${esc(k.id)}</a></div>
      <div class="facts">${k.size} complaints · ${k.regions.length} regions (${esc(k.regions.join(", "))}) · ${kzt(k.damage_kzt)}
      · linked by ${r.via === "script" ? "the same scam script" : "a shared identifier or money trail"}</div>`;
    if (r.bridge_to.length) html += `<div class="facts">Also connects to <b>${r.bridge_to.map(esc).join(", ")}</b> — two campaigns may be one gang.</div>`;
    html += `<h3>Evidence path</h3>${hopsHtml(r.evidence)}${quotesHtml(r.evidence?.quotes)}`;
    html += `<div class="row"><button data-open="${esc(k.id)}">Open campaign graph</button>
      <a href="api/campaigns/${esc(k.id)}/case.html" target="_blank"><button>Case file</button></a></div>`;
  } else {
    html += `<div class="headline">${esc(r.complaint_id)} saved — no shared identifier yet</div>
      <div class="facts">Closest scripts in the graph (the analyst decides):</div><ul class="cands">` +
      r.candidates.map((c) => `<li><span class="mono">${esc(c.id)}</span> · score ${c.score}${c.campaign ? ` · <span class="pill">${esc(c.campaign)}</span>` : ""}<br><span class="muted">${esc(c.text_en)}</span></li>`).join("") + "</ul>";
  }
  html += `<p class="muted"><b>Extracted:</b> ${esc(r.summary_en)}</p>`;
  return html;
}

/* ------------------------------------------------------------ campaigns */
let cy = null, campaigns = [], currentCampaign = null;
const COLORS = () => ({ Complaint: css("--c-complaint"), Card: css("--c-card"), mule: css("--c-mule"), cashout: css("--c-cashout"),
  Phone: css("--c-phone"), Account: css("--c-account"), Url: css("--c-url"), Domain: css("--c-domain"), Persona: css("--c-persona") });

async function loadCampaignList() {
  campaigns = await api("api/campaigns");
  const max = Math.max(...campaigns.map((c) => c.size), 1);
  $("#camp-list").innerHTML = campaigns.map((c) => `<button class="camp-card ${c.id === currentCampaign ? "active" : ""}" data-id="${esc(c.id)}">
      <div class="id">${esc(c.id)}</div>
      <div class="meta">${c.size} complaints · ${c.regions.length} regions · ${kzt(c.damage_kzt)}</div>
      <div class="meta">${esc((c.tactics || []).map((t) => TACTICS_LABEL(t)).join(", "))} · confidence ${c.confidence}</div>
      <div class="bar"><i style="width:${(100 * c.size) / max}%"></i></div></button>`).join("");
  $("#camp-list").querySelectorAll(".camp-card").forEach((b) => b.addEventListener("click", () => openCampaign(b.dataset.id)));
  const f = $("#inbox-filter"), keep = f.value;
  f.innerHTML = `<option value="">All complaints</option>` + campaigns.map((c) => `<option value="${esc(c.id)}">${esc(c.id)} (${c.size})</option>`).join("");
  f.value = keep;
}
const TACTICS_LABEL = (t) => TACTIC[t] || t;

async function openCampaign(id) {
  currentCampaign = id;
  showTab("campaigns");
  document.querySelectorAll(".camp-card").forEach((b) => b.classList.toggle("active", b.dataset.id === id));
  const g = await api(`api/campaigns/${id}/graph`);
  const k = g.campaign;
  $("#camp-head").innerHTML = `<h2>${esc(k.id)}</h2><span class="badge">${k.size} complaints</span>
    <span class="badge">${esc(k.regions.join(", "))}</span><span class="badge">${kzt(k.damage_kzt)}</span>
    <span class="badge">${esc(k.first_seen)} → ${esc(k.last_seen)}</span><span class="spacer"></span>
    <a href="api/campaigns/${esc(k.id)}/case.html" target="_blank"><button class="primary">Case file</button></a>
    <a href="api/campaigns/${esc(k.id)}/case.md" download="${esc(k.id)}.md"><button>Download .md</button></a>`;
  drawGraph(g);
  $("#detail").innerHTML = `<span class="muted">Click a node or a connection to see the evidence behind it.</span>`;
}

function drawGraph(g) {
  const C = COLORS();
  const elements = [
    ...g.nodes.map((n) => ({ data: { id: n.id, label: n.label === "Complaint" ? n.key : shortKey(n), kind: n.label,
      role: n.role || "", color: C[n.role] || C[n.label] || "#888", raw: n } })),
    ...g.edges.map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target, type: e.type, raw: e } })),
  ];
  const ink = css("--ink"), muted = css("--muted"), line = css("--line");
  if (cy) cy.destroy();
  cy = cytoscape({
    container: $("#graph"), elements, wheelSensitivity: 0.25,
    style: [
      { selector: "node", style: { "background-color": "data(color)", label: "data(label)", "font-size": 9, color: ink,
        "text-valign": "bottom", "text-margin-y": 3, width: 14, height: 14, "font-family": "ui-monospace, Consolas, monospace" } },
      { selector: "node[kind = 'Complaint']", style: { width: 10, height: 10, "font-size": 7, color: muted } },
      { selector: "node[kind != 'Complaint']", style: { shape: "round-rectangle", width: 22, height: 22, "font-size": 9.5, "font-weight": 700 } },
      { selector: "node[role = 'cashout']", style: { width: 30, height: 30, "border-width": 3, "border-color": C.cashout } },
      { selector: "edge", style: { width: 1.2, "line-color": line, "curve-style": "bezier", "target-arrow-shape": "triangle",
        "target-arrow-color": line, "arrow-scale": 0.6 } },
      { selector: "edge[type = 'FORWARDED_TO']", style: { width: 2.6, "line-color": C.cashout, "target-arrow-color": C.cashout } },
      { selector: ":selected", style: { "border-width": 3, "border-color": css("--accent"), "line-color": css("--accent"), "target-arrow-color": css("--accent") } },
    ],
    layout: { name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 55, padding: 30, randomize: false },
  });
  cy.on("tap", "node", (e) => showNode(e.target.data("raw")));
  cy.on("tap", "edge", (e) => showEdge(e.target.data("raw")));
  $("#legend").innerHTML = [["Complaint", C.Complaint], ["Card", C.Card], ["Mule card", C.mule], ["Cash-out", C.cashout],
    ["Phone", C.Phone], ["Account", C.Account], ["Link / domain", C.Url], ["Alias", C.Persona]]
    .map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("") + `<span>red edge = money moved</span>`;
}
const shortKey = (n) => n.label === "Card" ? `•${String(n.key).slice(-4)}` : n.label === "Phone" ? `…${String(n.key).slice(-4)}`
  : n.label === "Account" ? `${String(n.key).slice(0, 4)}…${String(n.key).slice(-4)}` : n.label === "Url" ? "link" : String(n.key);

function highlight(text, exs) {
  const spans = (exs || []).filter((x) => x.kind !== "tactic").sort((a, b) => a.start - b.start);
  let out = "", pos = 0;
  for (const s of spans) {
    if (s.start < pos) continue;
    out += esc(text.slice(pos, s.start)) + `<mark title="${esc(s.kind)}">${esc(text.slice(s.start, s.end))}</mark>`;
    pos = s.end;
  }
  return out + esc(text.slice(pos));
}

async function showNode(n) {
  if (n.label === "Complaint") {
    const c = await api(`api/complaints/${n.key}`);
    $("#detail").innerHTML = `<b class="mono">${esc(c.id)}</b> · ${esc(c.region)} · ${esc(c.filed_at)} · ${kzt(c.amount_kzt)}
      <p class="ru">${highlight(c.text, c.extractions)}</p><p class="muted">${esc(c.text_en)}</p>`;
  } else {
    $("#detail").innerHTML = `<b>${esc(n.label)}</b> <span class="mono">${esc(n.key)}</span>${n.role ? ` · <span class="pill">${esc(n.role)}</span>` : ""}
      <p class="muted">${n.role === "cashout" ? "Money from several victims ends up here — freezing it stops the whole chain."
        : n.role === "mule" ? "Received money directly from two or more victims." : "Shared by complaints in this campaign."}</p>`;
  }
}
function showEdge(e) {
  $("#detail").innerHTML = `<span class="mono">${esc(e.source)} —${esc(e.type)}→ ${esc(e.target)}</span>
    ${e.amount_kzt ? `<p>Bank transfer of <b>${kzt(e.amount_kzt)}</b>.</p>` : ""}
    ${e.quote ? `<blockquote>«${esc(e.quote)}»</blockquote><p class="muted">Victim's own words — extracted by rules, stored as an Extraction node in Relate.</p>` : ""}`;
}

/* ---------------------------------------------------------------- inbox */
let inboxPage = 0;
const PAGE = 25;
async function loadInbox() {
  const camp = $("#inbox-filter").value;
  const r = await api(`api/complaints?limit=${PAGE}&offset=${inboxPage * PAGE}${camp ? `&campaign=${encodeURIComponent(camp)}` : ""}`);
  $("#inbox-count").textContent = `${r.total} complaints · page ${inboxPage + 1} of ${Math.max(1, Math.ceil(r.total / PAGE))}`;
  $("#inbox-prev").disabled = inboxPage === 0;
  $("#inbox-next").disabled = (inboxPage + 1) * PAGE >= r.total;
  $("#inbox tbody").innerHTML = r.items.map((c) => `<tr class="clickable" data-id="${esc(c.id)}">
    <td class="mono">${esc(c.id)}</td><td>${esc(c.filed_at)}</td><td>${esc(c.region)}</td>
    <td class="tactic">${esc((c.tactics || []).map(TACTICS_LABEL).join(", ") || "—")}</td>
    <td class="num">${kzt(c.amount_kzt)}</td><td>${c.campaign ? `<span class="pill">${esc(c.campaign)}</span>` : `<span class="muted">—</span>`}</td>
    <td>${esc(c.text_en)}</td></tr>`).join("");
  $("#inbox tbody").querySelectorAll("tr.clickable").forEach((tr) => tr.addEventListener("click", () => toggleRow(tr)));
}
async function toggleRow(tr) {
  const next = tr.nextElementSibling;
  if (next && next.classList.contains("expanded")) { next.remove(); return; }
  const c = await api(`api/complaints/${tr.dataset.id}`);
  const row = document.createElement("tr");
  row.className = "expanded";
  row.innerHTML = `<td colspan="7"><p class="ru">${highlight(c.text, c.extractions)}</p>
    ${c.campaign ? `<button data-open="${esc(c.campaign)}">Open ${esc(c.campaign)}</button>` : ""}</td>`;
  tr.after(row);
  row.querySelector("[data-open]")?.addEventListener("click", () => openCampaign(c.campaign));
}
$("#inbox-filter").addEventListener("change", () => { inboxPage = 0; loadInbox(); });
$("#inbox-prev").addEventListener("click", () => { inboxPage--; loadInbox(); });
$("#inbox-next").addEventListener("click", () => { inboxPage++; loadInbox(); });

/* ---------------------------------------------------------------- query */
const QUERIES = [
  ["Campaigns by damage", "MATCH (k:Campaign)\nRETURN k.id AS campaign, k.size AS complaints, k.damage_kzt AS damage_kzt, k.regions AS regions\nORDER BY damage_kzt DESC"],
  ["Where the money ends up", "MATCH (c:Complaint)-[:PAID_TO]->(first)-[:FORWARDED_TO*1..3]->(sink:Card {role_hint: 'cashout'})\nRETURN sink.pan_masked AS cashout, count(DISTINCT c) AS victims, sum(c.amount_kzt) AS kzt\nORDER BY victims DESC"],
  ["Phones used against many victims", "MATCH (c:Complaint)-[:CONTACTED_BY]->(p:Phone)\nWITH p, count(c) AS victims, collect(DISTINCT c.region) AS regions\nWHERE victims > 1\nRETURN p.e164 AS phone, victims, regions, coalesce(p.hub, false) AS hub\nORDER BY victims DESC LIMIT 15"],
  ["Hub trap (legit numbers)", "MATCH (p:Phone {hub: true})<-[:CONTACTED_BY]-(c:Complaint)-[:USED_TACTIC]->(t:Tactic)\nRETURN p.e164 AS phone, count(DISTINCT c) AS complaints, collect(DISTINCT t.code) AS tactics"],
  ["Cross-region gangs", "MATCH (c:Complaint)-[:PART_OF]->(k:Campaign)\nWITH k, count(DISTINCT c.region) AS regions\nWHERE regions >= 3\nRETURN k.id AS campaign, regions ORDER BY regions DESC"],
];
$("#q-samples").innerHTML = QUERIES.map(([l], i) => `<button data-i="${i}">${esc(l)}</button>`).join("");
$("#q-samples").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { $("#q-text").value = QUERIES[b.dataset.i][1]; runQuery(); }));
$("#q-text").value = QUERIES[0][1];
async function runQuery() {
  const t0 = performance.now();
  try {
    const r = await post("api/cypher", { statement: $("#q-text").value });
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
async function loadReal() {
  let s;
  try { s = await api("api/ftc/summary"); } catch (e) {
    $("#real-lede").innerHTML = `Real FTC data is not built yet — run <code>python -m dropnet ftc-build</code>.`; return false;
  }
  $("#real-lede").innerHTML = `<b>${s.reports.toLocaleString()}</b> real complaints about unwanted calls, filed with the US
    Federal Trade Commission between ${esc(s.first_day)} and ${esc(s.last_day)}, live in one Relate file. Most of the numbers
    behind them were reported only once — so a blocklist of numbers is always one step behind.`;
  $("#real-kpis").innerHTML = [[s.reports.toLocaleString(), "reports"], [s.numbers.toLocaleString(), "reported numbers"],
    [pct(s.single_report_numbers_share), "numbers reported only once"], [pct(s.neighbor_share), "spoofed to look local"],
    [(s.campaigns.pool || 0).toLocaleString(), "number pools found"]].map(([v, l]) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join("");
  const ev = s.eval;
  if (ev) {
    ftcSplit = ev.split_day;
    const max = Math.max(ev.dropnet.coverage, ev.blocklist_all_seen.coverage);
    $("#eval-caption").innerHTML = `Rules learned from reports before ${esc(ev.split_day)} (${ev.train_reports.toLocaleString()}),
      scored on the ${ev.test_reports.toLocaleString()} reports that came after. Share of later reports each rule set would have caught:`;
    $("#eval-bars").innerHTML = hbar(`Block every number ever reported (${ev.blocklist_all_seen.rules.toLocaleString()} rules)`, ev.blocklist_all_seen.coverage, max)
      + hbar(`Blocklist: numbers with ≥2 reports (${ev.baseline.rules.toLocaleString()})`, ev.baseline.coverage, max)
      + (ev.dropnet_geographic ? hbar(`<b>Dropnet</b>, geographic pool blocks only (+${ev.dropnet_geographic.block_rules.toLocaleString()})`, ev.dropnet_geographic.coverage, max, true) : "")
      + hbar(`<b>Dropnet</b>, all pool blocks incl. toll-free (+${ev.dropnet.block_rules.toLocaleString()})`, ev.dropnet.coverage, max, true)
      + `<p class="muted">${ev.dropnet.new_numbers_caught.toLocaleString()} catches came from numbers nobody had reported before. The price: a
        block rule silences all 10,000 numbers of its range (${(ev.dropnet.numbers_blocked / 1e6).toFixed(1)} M numbers vs
        ${ev.baseline.numbers_blocked.toLocaleString()} for the blocklist), and toll-free ranges are shared by many businesses — blocking is a carrier's call.</p>`;
  }
  const prof = s.profile.filter((p) => p.reports > 1000).sort((a, b) => b.neighbor_share - a.neighbor_share);
  $("#spoof-bars").innerHTML = prof.map((p) => hbar(esc(p.label), p.neighbor_share, 1)).join("");
  ftcCampaigns = await api("api/ftc/campaigns?limit=40&kind=pool");
  $("#ftc-list").innerHTML = ftcCampaigns.map((c) => `<button class="camp-card" data-id="${esc(c.id)}">
    <div class="id">${esc(c.id.replace("POOL-", "Pool "))}</div>
    <div class="meta">${c.numbers} numbers · ${c.reports.toLocaleString()} reports · ${c.states} states</div>
    <div class="meta">${esc((c.subjects || []).join(", "))}${c.toll_free ? " · toll-free" : ""}</div></button>`).join("");
  $("#ftc-list").querySelectorAll(".camp-card").forEach((b) => b.addEventListener("click", () => openFtc(b.dataset.id)));
  if (ftcCampaigns.length) openFtc(ftcCampaigns[0].id);
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
  const C = { Block: css("--c-cashout"), Number: css("--c-card"), State: css("--c-phone"), Subject: css("--c-persona") };
  const els = [...g.nodes.map((n) => ({ data: { id: n.id, label: n.label, kind: n.kind, color: C[n.kind], w: n.kind === "Number" ? 8 + Math.min(26, Math.sqrt(n.reports || 1) * 2) : 18, raw: n } })),
    ...g.edges.map((e, i) => ({ data: { id: `f${i}`, source: e.source, target: e.target, type: e.type } }))];
  if (ftcCy) ftcCy.destroy();
  ftcCy = cytoscape({ container: $("#ftc-graph"), elements: els, wheelSensitivity: 0.25,
    style: [{ selector: "node", style: { "background-color": "data(color)", label: "data(label)", width: "data(w)", height: "data(w)", "font-size": 9, color: css("--ink") } },
      { selector: "node[kind = 'Block']", style: { shape: "round-rectangle", width: 40, height: 40, "font-weight": 700 } },
      { selector: "node[kind = 'State'], node[kind = 'Subject']", style: { shape: "round-rectangle", "font-size": 10 } },
      { selector: "edge", style: { width: 1, "line-color": css("--line"), "curve-style": "haystack" } },
      { selector: "edge[type = 'IN_BLOCK']", style: { width: 2, "line-color": C.Block } }],
    layout: { name: "cose", animate: false, nodeRepulsion: 12000, idealEdgeLength: 60, padding: 24 } });
  ftcCy.on("tap", "node[kind = 'Number']", (e) => assess(e.target.data("raw").number));
  $("#ftc-legend").innerHTML = [["Block (NPA-NXX)", C.Block], ["Reported number", C.Number], ["Victim state", C.State], ["Scam type", C.Subject]]
    .map(([l, c]) => `<span><i style="background:${c}"></i>${l}</span>`).join("") + "<span>node size = reports</span>";
  const picks = ftcCampaigns.slice(0, 12);
  $("#ftc-whatif").innerHTML = `<b>What if we had blocked these pools on day one?</b>
    <div class="whatif-pick">${picks.map((c) => `<label><input type="checkbox" value="${esc(c.id.replace("POOL-", ""))}" ${c.id === id ? "checked" : ""}> ${esc(c.id.replace("POOL-", ""))}</label>`).join("")}</div>
    <button class="primary" id="whatif-go">Run what-if</button> <span class="muted">Runs inside a Relate transaction, then rolls back — nothing is written.</span>
    <div id="whatif-out"></div>`;
  $("#whatif-go").addEventListener("click", async () => {
    const blocks = [...document.querySelectorAll(".whatif-pick input:checked")].map((x) => x.value);
    try {
      const r = await post("api/ftc/whatif", { blocks, since_day: ftcSplit });
      $("#whatif-out").innerHTML = `<p>Reports filed from ${esc(ftcSplit || "the first day")}: <b>${r.reports_stopped.toLocaleString()}</b> from
        <b>${r.numbers_covered.toLocaleString()}</b> numbers would have been stopped by ${r.rules} block rule${r.rules > 1 ? "s" : ""}
        (each block covers 10,000 numbers); ${r.campaigns_touched.length} campaigns touched.
        ${r.spoofed_reports_in_scope ? `<br><span class="muted">${r.spoofed_reports_in_scope.toLocaleString()} of them were spoofed-local calls — a block would also hit those numbers' real owners.</span>` : ""}</p>`;
    } catch (e) { $("#whatif-out").innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  });
}
async function assess(number) {
  $("#num-in").value = fmtNum(number);
  const a = await api(`api/ftc/number/${encodeURIComponent(number)}`);
  const label = { likely_spoofed: "Likely spoofed", pool: "Part of a number pool", repeat: "Repeatedly reported", single: "Reported once", unknown: "Not in the reports" }[a.verdict];
  $("#num-out").innerHTML = `<p class="verdict ${a.verdict}">${label}</p>` + (a.reports ? `<p>${a.reports.toLocaleString()} reports ·
    ${a.states} states · ${esc((a.subjects || []).join(", "))} · ${pct(a.neighbor_share)} spoofed-local · block ${esc(a.block)} has
    ${a.block_numbers} reported numbers · ${esc(a.first_day)} → ${esc(a.last_day)}</p>` : "") + `<div class="caution">${esc(a.caution)}</div>`;
  document.querySelector(".lookup").scrollIntoView({ behavior: "smooth", block: "center" });
}
$("#num-go").addEventListener("click", () => assess($("#num-in").value));
$("#num-in").addEventListener("keydown", (e) => { if (e.key === "Enter") assess($("#num-in").value); });

/* ----------------------------------------------------------------- boot */
(async function boot() {
  await Promise.all([refreshStats(), loadSamples(), loadCampaignList(), loadInbox()]);
  const tab = location.hash.slice(1);
  if (campaigns.length) await openCampaign(campaigns[0].id);
  const hasReal = await loadReal();
  showTab(["real", "ingest", "campaigns", "inbox", "query"].includes(tab) ? tab : hasReal ? "real" : "ingest");
})();
