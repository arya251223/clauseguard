"use strict";
const $ = (id) => document.getElementById(id);
const state = { report: null, risk: "ALL", cat: "ALL" };
const LABEL = { HIGH_RISK: "High risk", MODERATE_RISK: "Moderate risk", SAFE: "Low risk" };
const SCORE_CLASS = { HIGH_RISK: "HIGH", MODERATE_RISK: "MEDIUM", SAFE: "LOW" };
const WORD = { HIGH: "High risk", MEDIUM: "Medium risk", LOW: "Low risk" };

// Every string from the server or the PDF is inserted with textContent, never innerHTML.
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function show(id, on) { $(id).hidden = !on; }
function fail(msg) { const m = $("msg"); m.textContent = msg; m.hidden = !msg; }

async function health() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("engine").textContent = h.gemini_configured ? `Rules + Gemini (${h.model})` : "Rules engine (offline)";
  } catch { $("engine").textContent = "Server unreachable"; }
}

async function submit(promise) {
  fail(""); show("intro", false); show("busy", true); show("result", false);
  try {
    const res = await promise;
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Something went wrong.");
    state.report = data; state.risk = "ALL"; state.cat = "ALL";
    render();
  } catch (e) {
    show("busy", false); show("intro", true); fail(e.message);
  }
}

function upload(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) return fail("Choose a PDF file.");
  const fd = new FormData();
  fd.append("file", file); fd.append("engine", $("engineSel").value);
  submit(fetch("/api/audit", { method: "POST", body: fd }));
}

function render() {
  const r = state.report;
  show("busy", false); show("result", true);
  const cls = SCORE_CLASS[r.overall.label];
  $("scoreBox").className = "score " + cls;
  $("scoreNum").textContent = r.overall.score;
  $("scoreLabel").textContent = LABEL[r.overall.label];
  $("docName").textContent = r.document_name;
  $("sumText").textContent = r.summary;
  $("meta").textContent = `${r.engine_note ? r.engine_note + " " : ""}Engine: ${r.engine}. ${r.pages} pages. Analysed in ${r.duration_ms} ms.`;
  $("dlMd").href = `/api/audits/${r.id}/report.md`;

  // contract map, sized by clause length
  const map = $("map"); map.replaceChildren();
  const lens = {}; r.findings.forEach((f) => { lens[f.clause_id] = f.text.length; });
  r.clause_map.forEach((c) => {
    const b = el("button", c.risk); b.type = "button";
    b.style.flex = `${Math.max(1, (lens[c.id] || 300) / 100)} 1 0`;
    b.title = `${c.heading} (page ${c.page}): ${c.risk === "NONE" ? "no finding" : c.risk.toLowerCase()}`;
    b.setAttribute("aria-label", b.title); b.setAttribute("role", "listitem");
    b.onclick = () => jump(c.id);
    map.appendChild(b);
  });

  // gaps
  const g = $("gaps"); g.replaceChildren(); show("gapsWrap", r.gaps.length > 0);
  r.gaps.forEach((x) => {
    const d = el("div", "gap " + x.risk);
    d.append(el("strong", "badge", `${WORD[x.risk]}: ${x.category}`), el("p", "", x.explanation), el("p", "", "Suggested fix: " + x.suggested_revision));
    g.appendChild(d);
  });

  // chips + category filter
  const chips = $("chips"); chips.replaceChildren();
  ["ALL", "HIGH", "MEDIUM", "LOW"].forEach((k) => {
    const n = k === "ALL" ? r.findings.length : r.counts[k];
    const b = el("button", "chip", `${k === "ALL" ? "All" : k[0] + k.slice(1).toLowerCase()} (${n})`);
    b.type = "button"; b.setAttribute("aria-pressed", String(k === state.risk));
    b.onclick = () => { state.risk = k; render(); };
    chips.appendChild(b);
  });
  const sel = $("catSel"); sel.replaceChildren(new Option("All categories", "ALL"));
  r.categories.forEach((c) => sel.appendChild(new Option(c, c)));
  sel.value = state.cat; sel.onchange = () => { state.cat = sel.value; renderFindings(); };
  renderFindings();
  window.scrollTo({ top: 0 });
}

function renderFindings() {
  const r = state.report, box = $("findings"); box.replaceChildren();
  const list = r.findings.filter((f) => (state.risk === "ALL" || f.risk === state.risk) && (state.cat === "ALL" || f.category === state.cat));
  $("count").textContent = `(${list.length})`;
  if (!list.length) box.appendChild(el("p", "hint", "No findings match these filters."));
  list.forEach((f) => box.appendChild(card(f)));
}

function highlighted(text, spans) {
  const p = el("p", "clause");
  let at = 0;
  const merged = [];
  spans.slice().sort((a, b) => a[0] - b[0]).forEach(([s, e]) => {
    const last = merged[merged.length - 1];
    if (last && s <= last[1]) last[1] = Math.max(last[1], e); else merged.push([s, e]);
  });
  merged.forEach(([s, e]) => {
    p.append(text.slice(at, s)); p.append(el("mark", "", text.slice(s, e))); at = e;
  });
  p.append(text.slice(at));
  return p;
}

function card(f) {
  const a = el("article", "finding " + f.risk); a.id = "c" + f.clause_id;
  const h = el("header");
  h.append(el("span", "badge", WORD[f.risk]), el("h4", "", `${f.category}: ${f.heading}`), el("span", "pg", `Page ${f.page} | score ${f.score}`));
  const cols = el("div", "cols");
  cols.appendChild(highlighted(f.text, f.highlights));
  const note = el("div", "note");
  note.append(el("h5", "", "Why it was flagged"), el("p", "", f.explanation));
  if (f.triggers.length) {
    const ul = el("ul"); f.triggers.forEach((t) => ul.appendChild(el("li", "", t)));
    note.append(el("h5", "", "Risky wording found"), ul);
  }
  if (f.disagreement) note.appendChild(el("p", "warn", `Gemini rated this ${f.llm_risk}, the rules engine rated it ${f.risk}. Review by hand.`));
  const rev = el("div", "rev", f.suggested_revision);
  const copy = el("button", "copy", "Copy suggested wording"); copy.type = "button";
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(f.suggested_revision); copy.textContent = "Copied"; }
    catch { copy.textContent = "Copy failed"; }
    setTimeout(() => (copy.textContent = "Copy suggested wording"), 1600);
  };
  note.append(el("h5", "", "Safer wording"), rev, copy);
  cols.appendChild(note);
  a.append(h, cols);
  return a;
}

function jump(id) {
  if (state.risk !== "ALL" || state.cat !== "ALL") { state.risk = "ALL"; state.cat = "ALL"; render(); }
  const t = document.getElementById("c" + id);
  if (t) { t.scrollIntoView({ block: "center" }); t.querySelector("h4").setAttribute("tabindex", "-1"); t.querySelector("h4").focus({ preventScroll: true }); }
}

const drop = $("drop");
$("file").onchange = (e) => upload(e.target.files[0]);
drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } };
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files[0]));
$("sampleBtn").onclick = () => submit(fetch("/api/sample?engine=" + encodeURIComponent($("engineSel").value)));
$("again").onclick = () => { show("result", false); show("intro", true); $("file").value = ""; };
$("print").onclick = () => window.print();
$("dlJson").onclick = () => {
  const blob = new Blob([JSON.stringify(state.report, null, 2)], { type: "application/json" });
  const a = el("a"); a.href = URL.createObjectURL(blob); a.download = `clauseguard-${state.report.id.slice(0, 8)}.json`; a.click();
  URL.revokeObjectURL(a.href);
};
health();
