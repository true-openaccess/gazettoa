// The table of the circuits of an interface (the tab "Implementations"), with its scatter plot.
//
// The builder says what the table holds (builder/gaze/selection.py): the columns, each with its
// kind (text, number, date, latest, libraries, metric), one row per circuit, and the metrics of
// each circuit per set of conditions. This file only draws what it is given, so it names no field
// of a manifest. What the reader chooses (conditions, columns, filters, sort, earlier
// generations, plot) is kept per interface while the page is open.
import { t, esc, fmtNum, fmtDate, st, nameLink, libLinks, latestMark } from "./core.js";

const STATE = new Map();
const PALETTE = 6; // .sc-c0 … .sc-c5 in styles.css

const numeric = c => c.kind === "number" || c.kind === "metric";
const num = v => (typeof v === "number" && Number.isFinite(v) ? v : null);
const listy = c => c.kind === "latest" || c.kind === "libraries";
const empty = v => v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length);

function stateOf(ifc, sel) {
  if (!STATE.has(ifc)) {
    const nums = sel.columns.filter(numeric);
    const metrics = sel.columns.filter(c => c.kind === "metric");
    const axes = metrics.length >= 2 ? metrics : nums;
    STATE.set(ifc, {
      cond: sel.conds.length ? sel.conds[0].id : "", old: false,
      hidden: new Set(sel.columns.filter(c => c.hidden).map(c => c.key)),
      q: "", f: {}, sort: "", desc: false, filters: false, picker: false, plot: false,
      x: axes[0] ? axes[0].key : "", y: axes[1] ? axes[1].key : (axes[0] ? axes[0].key : ""),
      color: (sel.columns.find(c => c.kind === "text") || {}).key || "", logX: false, logY: false,
    });
  }
  return STATE.get(ifc);
}

/** A cell's value: a metric under the conditions chosen, any other column as the row has it. */
const valueOf = (s, r, c) => (c.kind === "metric" ? ((r.conds[s.cond] || {}).values || {})[c.key] : r.values[c.key]);
const marksOf = (s, r, c) => ((r.conds[s.cond] || {}).marks || {})[c.key] || {};
const label = c => (c.kind === "metric" ? c.label : t(c.label));
const plain = c => (c.kind === "metric" ? `${c.group ? c.group + "." : ""}${c.label}${c.unit ? ` (${c.unit})` : ""}` : t(c.label));
const display = (r, names) => (names[r.ckt] ? names[r.ckt][0] : r.ckt);

/* ------------------------------------------------------------------ filtering and sorting */

const baseRows = (s, sel) => sel.rows.filter(r => s.old || r.head);

function filtering(s) {
  return !!s.q.trim() || Object.values(s.f).some(x => (x && typeof x === "object" ? (x.min ?? "") !== "" || (x.max ?? "") !== "" : !!x));
}

function visibleRows(s, sel, names) {
  const q = s.q.trim().toLowerCase();
  let rows = baseRows(s, sel).filter(r => {
    if (q) {
      const hay = [display(r, names), r.ckt, r.summary || "", ...sel.columns.filter(c => c.kind === "text").map(c => r.values[c.key] || "")].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    for (const c of sel.columns) {
      const f = s.f[c.key];
      if (!f) continue;
      const v = valueOf(s, r, c);
      if (numeric(c)) {
        const lo = f.min === "" || f.min == null ? null : Number(f.min);
        const hi = f.max === "" || f.max == null ? null : Number(f.max);
        const hasLo = lo !== null && Number.isFinite(lo), hasHi = hi !== null && Number.isFinite(hi);
        if (!hasLo && !hasHi) continue;
        const x = num(v);
        if (x === null || (hasLo && x < lo) || (hasHi && x > hi)) return false;
      } else if (listy(c)) {
        const list = Array.isArray(v) ? v : [];
        if (f === "#any" ? !list.length : f === "#none" ? list.length : !list.includes(f)) return false;
      } else if (f === "#none" ? !empty(v) : String(v ?? "") !== f) return false;
    }
    return true;
  });
  if (s.sort) {
    const col = sel.columns.find(c => c.key === s.sort);
    const val = r => (s.sort === "#ckt" ? display(r, names) : !col ? null : listy(col) ? (valueOf(s, r, col) || []).join(", ") : valueOf(s, r, col));
    rows = rows.slice().sort((a, b) => {
      const x = val(a), y = val(b);
      if (empty(x)) return empty(y) ? 0 : 1;
      if (empty(y)) return -1;
      const d = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return s.desc ? -d : d;
    });
  }
  return rows;
}

/* ------------------------------------------------------------------ the parts of the table */

function toolbarHtml(s, sel) {
  const metrics = sel.columns.filter(c => c.kind === "metric").length;
  const shown = sel.columns.filter(c => !s.hidden.has(c.key)).length;
  let conds = "";
  if (sel.conds.length > 1) {
    conds = `<label>${esc(t("Conditions"))} <select data-s="cond">${sel.conds.map(c => `<option value="${esc(c.id)}"${s.cond === c.id ? " selected" : ""}>${esc(c.text || t("default"))} (${esc(t("{n} circuits", { n: c.circuits }))})</option>`).join("")}</select></label>`;
  } else if (sel.conds.length === 1) {
    conds = `<span class="faint">${esc(t("Conditions"))}: <span class="mono">${esc(sel.conds[0].text || t("default"))}</span></span>`;
  }
  const old = sel.rows.some(r => !r.head) ? `<label class="chk"><input type="checkbox" data-s="old"${s.old ? " checked" : ""}> ${esc(t("Show earlier generations"))}</label>` : "";
  return `<div class="sel-bar">${conds}${old}
    <span class="right">
      <button type="button" class="btn sm${s.filters ? " on" : ""}" data-act="filters" aria-expanded="${s.filters}">${esc(t("Filter"))}</button>
      <button type="button" class="btn sm${s.picker ? " on" : ""}" data-act="picker" aria-expanded="${s.picker}">${esc(t("Columns"))} <span class="faint">${shown}/${sel.columns.length}</span></button>
      ${metrics ? `<button type="button" class="btn sm${s.plot ? " on" : ""}" data-act="plot" aria-expanded="${s.plot}">${esc(t("Scatter plot"))}</button>` : ""}
    </span>
  </div>`;
}

function pickerHtml(s, sel) {
  const groups = new Map();
  for (const c of sel.columns) {
    const g = c.kind === "metric" ? c.group || "" : "#fixed";
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(c);
  }
  const item = c => `<div class="sel-item"><label><input type="checkbox" data-col="${esc(c.key)}"${s.hidden.has(c.key) ? "" : " checked"}> ${esc(label(c))}${c.unit ? ` <span class="faint">${esc(c.unit)}</span>` : ""}</label></div>`;
  return `<div class="sel-picker">${[...groups].map(([g, cs]) => `<div class="sel-grp"><div class="sel-grp-hd"><b>${g === "#fixed" ? esc(t("Circuit")) : `<span class="mono">${esc(g)}</span>`}</b>
      <button type="button" class="linkish" data-grp="${esc(g)}" data-on="1">${esc(t("all"))}</button> <button type="button" class="linkish" data-grp="${esc(g)}" data-on="0">${esc(t("none"))}</button></div>
      ${cs.map(item).join("")}</div>`).join("")}</div>`;
}

function statusHtml(s, sel, rows) {
  const clear = filtering(s) ? ` <button type="button" class="linkish" data-act="clear">${esc(t("Clear the filters"))}</button>` : "";
  return `<p class="faint sel-count">${esc(t("{n} of {m} circuits", { n: rows.length, m: baseRows(s, sel).length }))}${clear}</p>`;
}

function cellHtml(s, c, r) {
  const v = valueOf(s, r, c);
  if (c.kind === "latest") {
    if (!empty(v)) return { html: latestMark(v) };
    return r.head && r.unmarked ? { html: `<span class="faint" title="${esc(t("No library of this instance marks a generation of this series latest; the newest is shown"))}">${esc(t("no mark"))}</span>` } : { html: `<span class="faint">—</span>` };
  }
  if (empty(v)) return { html: `<span class="faint">—</span>`, cls: numeric(c) ? "r" : "" };
  if (c.kind === "libraries") return { html: libLinks(v) };
  if (c.kind === "date") return { html: esc(fmtDate(v)), cls: "nw" };
  if (c.kind === "text") return { html: esc(v) };
  if (c.kind === "number") return { html: esc(fmtNum(v)), cls: "r num" };
  const m = marksOf(s, r, c);
  const tags = [
    m.n >= 2 ? `<span class="faint" title="${esc(t("median of {n} values", { n: m.n }))}">×${m.n}</span>` : "",
    m.multi ? st("multi", t("multi-party"), t("Multi-party verified")) : "",
    m.disagree ? st("disputed", t("disagree"), t("Two values differ by more than the tolerance")) : "",
  ].filter(Boolean).join(" ");
  return { html: `<span class="num">${esc(fmtNum(v))}</span>${tags ? ` <span class="sel-tags">${tags}</span>` : ""}`, cls: "r nw" };
}

function nameCell(s, r, names) {
  const marks = [r.newer ? st("info", t("newer version"), t("A library of this instance marks a later generation of its series latest")) : "",
    r.valid ? "" : st("disputed", t("does not pass"))].filter(Boolean).join(" ");
  const others = !s.old && r.others ? ` <button type="button" class="linkish faint" data-act="old">${esc(t("{n} other generations", { n: r.others }))}</button>` : "";
  return `${nameLink(r.ckt, names, { withShort: true })}${marks ? " " + marks : ""}${r.summary ? `<span class="sub">${esc(r.summary)}</span>` : ""}${others}`;
}

function rowsHtml(s, sel, rows, names) {
  const cols = sel.columns.filter(c => !s.hidden.has(c.key));
  if (!rows.length) return `<tr><td colspan="${cols.length + 1}" class="empty">${esc(t("No circuit is left by these filters."))}</td></tr>`;
  return rows.map(r => `<tr><td>${nameCell(s, r, names)}</td>${cols.map(c => { const x = cellHtml(s, c, r); return `<td${x.cls ? ` class="${x.cls}"` : ""}>${x.html}</td>`; }).join("")}</tr>`).join("");
}

function filterCell(s, sel, c) {
  const f = s.f[c.key];
  if (numeric(c)) {
    const rg = f || {};
    return `<th><span class="sel-range"><input type="number" step="any" data-range="${esc(c.key)}" data-end="min" value="${esc(rg.min ?? "")}" placeholder="${esc(t("min"))}" aria-label="${esc(plain(c))} ${esc(t("min"))}"><input type="number" step="any" data-range="${esc(c.key)}" data-end="max" value="${esc(rg.max ?? "")}" placeholder="${esc(t("max"))}" aria-label="${esc(plain(c))} ${esc(t("max"))}"></span></th>`;
  }
  if (c.kind === "date") return "<th></th>";
  const opt = (v, text) => `<option value="${esc(v)}"${(f || "") === v ? " selected" : ""}>${esc(text)}</option>`;
  let opts;
  if (listy(c)) {
    const libs = [...new Set(sel.rows.flatMap(r => r.values[c.key] || []))].sort();
    opts = [opt("", t("all")), ...(c.kind === "latest" ? [opt("#any", t("marked by any library"))] : []), ...libs.map(x => opt(x, x)), ...(c.kind === "latest" ? [opt("#none", t("no mark"))] : [])];
  } else {
    const vals = [...new Set(sel.rows.map(r => r.values[c.key]).filter(x => !empty(x)).map(String))].sort();
    opts = [opt("", t("all")), ...vals.map(x => opt(x, x)), ...(sel.rows.some(r => empty(r.values[c.key])) ? [opt("#none", "—")] : [])];
  }
  return `<th><select data-f="${esc(c.key)}" aria-label="${esc(plain(c))}">${opts.join("")}</select></th>`;
}

function tableHtml(s, sel, rows, names) {
  const cols = sel.columns.filter(c => !s.hidden.has(c.key));
  const arrow = k => (s.sort === k ? (s.desc ? " ▼" : " ▲") : "");
  const th = (k, inner, cls = "", sub = "") => `<th class="${cls}"><button type="button" class="sel-sort" data-sort="${esc(k)}">${inner}${arrow(k)}${sub}</button></th>`;
  // over the metrics, the testbench each comes from
  let groups = "";
  if (cols.some(c => c.kind === "metric")) {
    const spans = [];
    for (const c of cols) {
      const g = c.kind === "metric" ? c.group || "" : null;
      const last = spans[spans.length - 1];
      if (last && last.g === g) last.n++; else spans.push({ g, n: 1 });
    }
    groups = `<tr class="sel-groups"><th></th>${spans.map(x => `<th colspan="${x.n}"${x.g === null ? "" : ` class="grp mono"`}>${x.g === null ? "" : esc(x.g)}</th>`).join("")}</tr>`;
  }
  const head = [
    th("#ckt", esc(t("Circuit"))),
    ...cols.map(c => {
      const better = c.better === "lower" ? ` <span class="faint" title="${esc(t("lower is better"))}">↓</span>` : c.better === "higher" ? ` <span class="faint" title="${esc(t("higher is better"))}">↑</span>` : "";
      return th(c.key, `${esc(label(c))}${better}`, numeric(c) ? "r" : "", c.unit ? `<span class="sub mono">${esc(c.unit)}</span>` : "");
    }),
  ];
  const filters = s.filters ? `<tr class="sel-filters"><th><input type="search" data-s="q" value="${esc(s.q)}" placeholder="${esc(t("Name or text"))}" aria-label="${esc(t("Filter rows"))}"></th>${cols.map(c => filterCell(s, sel, c)).join("")}</tr>` : "";
  return `<div class="scroll"><table class="sel-table"><thead>${groups}<tr>${head.join("")}</tr>${filters}</thead><tbody data-part="rows">${rowsHtml(s, sel, rows, names)}</tbody></table></div>`;
}

/* ------------------------------------------------------------------ the scatter plot */

function ticks(lo, hi, log) {
  if (log) {
    const out = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) for (const m of [1, 2, 5]) {
      const v = m * 10 ** e;
      if (v >= lo * 0.999 && v <= hi * 1.001) out.push(v);
    }
    return out.length >= 2 ? out : [lo, hi];
  }
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / 5;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map(k => k * mag).find(k => k >= raw) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

/** The rows no other row beats on both axes, each axis in the direction its metric is better. */
function pareto(pts, bx, by) {
  const sx = bx === "lower" ? 1 : -1, sy = by === "lower" ? 1 : -1;
  const beats = (a, b) => sx * a.x <= sx * b.x && sy * a.y <= sy * b.y && (a.x !== b.x || a.y !== b.y);
  return pts.filter(p => !pts.some(q => beats(q, p))).sort((a, b) => a.x - b.x);
}

function plotHtml(s, sel, rows, names) {
  const nums = sel.columns.filter(numeric);
  const texts = sel.columns.filter(c => c.kind === "text");
  if (nums.length < 1) return `<div class="sel-plot"><p class="empty">${esc(t("No numeric column to plot."))}</p></div>`;
  const cx = sel.columns.find(c => c.key === s.x) || nums[0];
  const cy = sel.columns.find(c => c.key === s.y) || nums[0];
  const opt = (cur, list) => list.map(c => `<option value="${esc(c.key)}"${c.key === cur ? " selected" : ""}>${esc(plain(c))}</option>`).join("");
  const controls = `<div class="sel-bar">
    <label>X <select data-s="x">${opt(cx.key, nums)}</select></label><label class="chk"><input type="checkbox" data-s="logX"${s.logX ? " checked" : ""}> ${esc(t("log"))}</label>
    <label>Y <select data-s="y">${opt(cy.key, nums)}</select></label><label class="chk"><input type="checkbox" data-s="logY"${s.logY ? " checked" : ""}> ${esc(t("log"))}</label>
    ${texts.length ? `<label>${esc(t("Colour by"))} <select data-s="color"><option value="">—</option>${opt(s.color, texts)}</select></label>` : ""}</div>`;
  const pts = rows.map(r => ({ r, x: num(valueOf(s, r, cx)), y: num(valueOf(s, r, cy)) })).filter(p => p.x !== null && p.y !== null);
  const logX = s.logX && pts.every(p => p.x > 0), logY = s.logY && pts.every(p => p.y > 0);
  if (!pts.length) return `<div class="sel-plot">${controls}<p class="empty">${esc(t("No row has both values."))}</p></div>`;
  const W = 640, H = 380, L = 70, R = 16, T = 14, B = 48;
  const ext = (vs, log) => {
    let lo = Math.min(...vs), hi = Math.max(...vs);
    if (log) { lo /= 1.25; hi *= 1.25; } else { const pad = (hi - lo || Math.abs(hi) || 1) * 0.08; lo -= pad; hi += pad; }
    return [lo, hi];
  };
  const [x0, x1] = ext(pts.map(p => p.x), logX), [y0, y1] = ext(pts.map(p => p.y), logY);
  const fx = v => L + (logX ? Math.log10(v / x0) / Math.log10(x1 / x0) : (v - x0) / (x1 - x0)) * (W - L - R);
  const fy = v => H - B - (logY ? Math.log10(v / y0) / Math.log10(y1 / y0) : (v - y0) / (y1 - y0)) * (H - T - B);
  const colour = p => (s.color ? String(p.r.values[s.color] ?? "—") : "");
  const cats = [...new Set(pts.map(colour))];
  const ci = p => cats.indexOf(colour(p)) % PALETTE;
  const grid = [
    ...ticks(x0, x1, logX).map(v => `<line class="sc-grid" x1="${fx(v)}" x2="${fx(v)}" y1="${T}" y2="${H - B}"/><text class="sc-tick" x="${fx(v)}" y="${H - B + 16}" text-anchor="middle">${esc(fmtNum(v))}</text>`),
    ...ticks(y0, y1, logY).map(v => `<line class="sc-grid" x1="${L}" x2="${W - R}" y1="${fy(v)}" y2="${fy(v)}"/><text class="sc-tick" x="${L - 6}" y="${fy(v) + 4}" text-anchor="end">${esc(fmtNum(v))}</text>`),
  ].join("");
  let front = "";
  if ((cx.better === "lower" || cx.better === "higher") && (cy.better === "lower" || cy.better === "higher") && cx.key !== cy.key) {
    const pf = pareto(pts, cx.better, cy.better);
    if (pf.length >= 2) front = `<polyline class="sc-front" points="${pf.map(p => `${fx(p.x)},${fy(p.y)}`).join(" ")}"/>`;
  }
  const dots = pts.map(p => {
    const tip = `${display(p.r, names)}: ${plain(cx)} ${fmtNum(p.x)}, ${plain(cy)} ${fmtNum(p.y)}`;
    return `<a href="#/${esc(p.r.ckt)}"><circle class="sc-dot sc-c${ci(p)}" cx="${fx(p.x)}" cy="${fy(p.y)}" r="6"><title>${esc(tip)}</title></circle></a>`;
  }).join("");
  const svg = `<svg class="sc-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Scatter plot"))}: ${esc(plain(cx))}, ${esc(plain(cy))}">
    ${grid}<line class="sc-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/><line class="sc-axis" x1="${L}" x2="${L}" y1="${T}" y2="${H - B}"/>
    <text class="sc-label" x="${(L + W - R) / 2}" y="${H - 8}" text-anchor="middle">${esc(plain(cx))}${logX ? " (log)" : ""}</text>
    <text class="sc-label" transform="translate(16 ${(T + H - B) / 2}) rotate(-90)" text-anchor="middle">${esc(plain(cy))}${logY ? " (log)" : ""}</text>
    ${front}${dots}</svg>`;
  const legend = s.color ? `<div class="sc-legend">${cats.map((c, i) => `<span><i class="sc-c${i % PALETTE}"></i>${esc(c || "—")}</span>`).join("")}</div>` : "";
  const note = front ? `<p class="faint">${esc(t("The line joins the rows no other row beats on both axes, each in the direction its metric is better."))}</p>` : "";
  return `<div class="sel-plot">${controls}${svg}${legend}${note}</div>`;
}

/* ------------------------------------------------------------------ mounting */

export function mountSelection(box, data) {
  const { ifc, sel, names } = data;
  const s = stateOf(ifc, sel);
  const part = k => box.querySelector(`[data-part=${k}]`);
  // typing in a filter changes the rows only, so the field keeps the focus
  const paintRows = () => {
    const rows = visibleRows(s, sel, names);
    part("rows").innerHTML = rowsHtml(s, sel, rows, names);
    part("status").innerHTML = statusHtml(s, sel, rows);
    part("plot").innerHTML = s.plot ? plotHtml(s, sel, rows, names) : "";
  };
  const paintAll = () => {
    const rows = visibleRows(s, sel, names);
    box.innerHTML = `<div data-part="bar">${toolbarHtml(s, sel)}</div><div data-part="picker">${s.picker ? pickerHtml(s, sel) : ""}</div>`
      + `<div data-part="plot">${s.plot ? plotHtml(s, sel, rows, names) : ""}</div><div data-part="status">${statusHtml(s, sel, rows)}</div>`
      + `<div data-part="table">${tableHtml(s, sel, rows, names)}</div>`;
  };
  box.addEventListener("input", e => {
    const el = e.target;
    if (el.dataset.s === "q") { s.q = el.value; paintRows(); return; }
    if (el.dataset.range) {
      const rg = s.f[el.dataset.range] || (s.f[el.dataset.range] = {});
      rg[el.dataset.end] = el.value;
      paintRows();
    }
  });
  box.addEventListener("change", e => {
    const el = e.target;
    const k = el.dataset.s;
    if (k === "cond") { s.cond = el.value; paintAll(); return; }
    if (k === "x" || k === "y" || k === "color") { s[k] = el.value; paintRows(); return; }
    if (k === "logX" || k === "logY") { s[k] = el.checked; paintRows(); return; }
    if (k === "old") { s.old = el.checked; paintAll(); return; }
    if (el.dataset.f !== undefined) { s.f[el.dataset.f] = el.value; paintRows(); return; }
    if (el.dataset.col) {
      if (el.checked) s.hidden.delete(el.dataset.col); else s.hidden.add(el.dataset.col);
      part("bar").innerHTML = toolbarHtml(s, sel);
      part("table").innerHTML = tableHtml(s, sel, visibleRows(s, sel, names), names);
    }
  });
  box.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b || !box.contains(b)) return;
    const act = b.dataset.act;
    if (act === "filters" || act === "picker" || act === "plot") { s[act] = !s[act]; paintAll(); return; }
    if (act === "old") { s.old = true; paintAll(); return; }
    if (act === "clear") { s.q = ""; s.f = {}; paintAll(); return; }
    if (b.dataset.grp !== undefined) {
      for (const c of sel.columns) {
        const g = c.kind === "metric" ? c.group || "" : "#fixed";
        if (g !== b.dataset.grp) continue;
        if (b.dataset.on === "1") s.hidden.delete(c.key); else s.hidden.add(c.key);
      }
      paintAll();
      return;
    }
    if (b.dataset.sort !== undefined) {
      if (s.sort === b.dataset.sort) s.desc = !s.desc; else { s.sort = b.dataset.sort; s.desc = false; }
      part("table").innerHTML = tableHtml(s, sel, visibleRows(s, sel, names), names);
    }
  });
  paintAll();
}
