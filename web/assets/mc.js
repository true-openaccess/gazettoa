// Gazettoa: a Monte Carlo simulation (an evidence record of the kind mc, B37). The record gives the
// statistics of each metric; its evidence/samples.csv gives the value of each sample. This module
// reads samples.csv, checks it against the SHA-256 of the index and against the statistics the
// record wrote, draws each metric's samples, holds them against the targets of the circuit tested
// (the record writes no yield, so anyone may), and compares the record with the others of its
// reproduction group: sample by sample when they ran the same samples alike, else by statistics.
// The builder gives everything else (views.Model.mc_run); this module knows no field of a manifest
// but the columns of samples.csv, which B37 defines.
import { t, esc, fmtNum, getBytes, decodeText, sha256Hex, rawUrl, st, short, dash } from "./core.js";

const SHOWN = 1000; // lines of samples.csv put into the table

/** samples.csv: its first line `sample,<metric>…`, then one line per sample, a value left empty when
 *  the sample did not give it (B37). Lines that do not keep the format are counted, not read. */
export function parseSamples(text) {
  const lines = text.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const head = (lines.shift() || "").replace(/\r$/, "").split(",");
  const out = { ok: head[0] === "sample", metrics: head.slice(1), rows: [], bad: 0 };
  for (const raw of lines) {
    const cells = raw.replace(/\r$/, "").split(",");
    const k = Number(cells[0]);
    const vals = cells.slice(1).map(x => (x === "" ? null : Number(x)));
    if (cells.length !== head.length || !Number.isInteger(k) || vals.some(x => x !== null && !Number.isFinite(x))) { out.bad++; continue; }
    out.rows.push({ k, vals });
  }
  return out;
}

/** The statistics of one column, as B37 asks the tool to compute them: sigma with n − 1. */
export function statsOf(xs) {
  const v = xs.filter(x => x !== null);
  const n = v.length;
  const r = { n, failed: xs.length - n, mean: null, sigma: null, min: null, max: null };
  if (!n) return r;
  r.mean = v.reduce((a, b) => a + b, 0) / n;
  r.min = Math.min(...v);
  r.max = Math.max(...v);
  if (n >= 2) r.sigma = Math.sqrt(v.reduce((a, b) => a + (b - r.mean) ** 2, 0) / (n - 1));
  return r;
}

const column = (p, metric) => { const i = p.metrics.indexOf(metric); return i < 0 ? null : p.rows.map(r => r.vals[i]); };
const close = (a, b) => (a === null || a === undefined ? b === null || b === undefined : b !== null && b !== undefined && Math.abs(a - b) <= 1e-9 * Math.max(Math.abs(a), Math.abs(b)) + 1e-300);

/** How the record's statistics agree with its samples.csv: the metrics that differ. */
function recordedVsFile(stats, p) {
  const diff = [];
  for (const [metric, s] of Object.entries(stats || {})) {
    const col = column(p, metric);
    if (!col) { diff.push(t("{m}: no column", { m: metric })); continue; }
    const c = statsOf(col);
    for (const k of ["n", "failed", "mean", "sigma", "min", "max"]) {
      if (!close(s[k], c[k])) diff.push(`${metric}: ${k} ${fmtNum(s[k])} ≠ ${fmtNum(c[k])}`);
    }
  }
  return diff;
}

/** Two values of a metric agree within its tolerance (type tb): |a − b| ≤ max(abs, rel × max(|a|, |b|)). */
const tolOf = (tol, a, b) => Math.max(Number((tol || {}).abs) || 0, (Number((tol || {}).rel) || 0) * Math.max(Math.abs(a), Math.abs(b)));
const binary = xs => xs.every(x => x === null || x === 0 || x === 1);

/** Compare two records of one group (B37): sample by sample when the samples are the same ones run
 *  alike (the same simulator, and with lhs the same points), else by statistics. */
export function compare(a, b, pa, pb, defs) {
  const sameRun = a.simulator && a.simulator === b.simulator && (a.sampling !== "lhs" || a.points === b.points);
  // the metrics of either record: those its statistics name, and the columns of its samples.csv
  const metrics = [...new Set([...Object.keys(a.stats || {}), ...Object.keys(b.stats || {}), ...((pa && pa.metrics) || []), ...((pb && pb.metrics) || [])])];
  if (sameRun && pa && pb) {
    const byK = new Map(pb.rows.map(r => [r.k, r]));
    const diffs = [];
    let compared = 0;
    for (const ra of pa.rows) {
      const rb = byK.get(ra.k);
      if (!rb) continue;
      compared++;
      for (const m of metrics) {
        const ia = pa.metrics.indexOf(m), ib = pb.metrics.indexOf(m);
        const x = ia < 0 ? null : ra.vals[ia], y = ib < 0 ? null : rb.vals[ib];
        if (x === null && y === null) continue;
        if (x === null || y === null || Math.abs(x - y) > tolOf((defs[m] || {}).tolerance, x, y) + 1e-300) diffs.push({ k: ra.k, m, x, y });
      }
    }
    return { mode: "samples", compared, diffs, ok: compared > 0 && !diffs.length };
  }
  const rows = [];
  for (const m of metrics) {
    const s1 = (a.stats || {})[m], s2 = (b.stats || {})[m];
    if (!s1 || !s2 || !(s1.n >= 2) || !(s2.n >= 2)) { rows.push({ m, skipped: true }); continue; }
    const ca = pa && column(pa, m), cb = pb && column(pb, m);
    const tol = (defs[m] || {}).tolerance;
    if (ca && cb && binary(ca) && binary(cb)) {
      const p = (s1.n * s1.mean + s2.n * s2.mean) / (s1.n + s2.n);
      const bound = 3 * Math.sqrt(p * (1 - p) * (1 / s1.n + 1 / s2.n));
      rows.push({ m, binary: true, d: Math.abs(s1.mean - s2.mean), bound, ok: Math.abs(s1.mean - s2.mean) <= bound + 1e-300 });
      continue;
    }
    const bm = Math.max(tolOf(tol, s1.mean, s2.mean), 3 * Math.sqrt(s1.sigma ** 2 / s1.n + s2.sigma ** 2 / s2.n));
    const bs = Math.max(tolOf(tol, s1.sigma, s2.sigma), 3 * Math.sqrt(s1.sigma ** 2 / (2 * (s1.n - 1)) + s2.sigma ** 2 / (2 * (s2.n - 1))));
    const okm = Math.abs(s1.mean - s2.mean) <= bm + 1e-300, oks = Math.abs(s1.sigma - s2.sigma) <= bs + 1e-300;
    rows.push({ m, d: Math.abs(s1.mean - s2.mean), bound: bm, ds: Math.abs(s1.sigma - s2.sigma), bounds: bs, ok: okm && oks, okm, oks, binaryUnknown: !(ca && cb) });
  }
  const judged = rows.filter(r => !r.skipped);
  return { mode: "statistics", rows, ok: judged.length > 0 && judged.every(r => r.ok) };
}

/* ------------------------------------------------------------------ drawing */

const meets = (x, v) => v !== null && (x.min === null || x.min === undefined || v >= x.min) && (x.max === null || x.max === undefined || v <= x.max);
const boundText = x => (x.min !== null && x.max !== null ? `${fmtNum(x.min)} – ${fmtNum(x.max)}` : x.min !== null ? `≥ ${fmtNum(x.min)}` : `≤ ${fmtNum(x.max)}`);

/** The samples of one metric: a bar per value when there are few values (a decision of 0 or 1), else
 *  a histogram; the mean and mean ± sigma, and each target, marked. */
function histogram(xs, s, targets, unit) {
  const v = xs.filter(x => x !== null);
  if (!v.length) return `<p class="empty">${esc(t("No sample gave this metric."))}</p>`;
  const W = 360, H = 170, L = 8, R = 8, T = 10, B = 34;
  const distinct = [...new Set(v)].sort((a, b) => a - b);
  let lo = Math.min(...v, ...targets.flatMap(x => [x.min, x.max]).filter(x => x !== null && x !== undefined));
  let hi = Math.max(...v, ...targets.flatMap(x => [x.min, x.max]).filter(x => x !== null && x !== undefined));
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.06;
  lo -= pad; hi += pad;
  const fx = x => L + ((x - lo) / (hi - lo)) * (W - L - R);
  let bins;
  if (distinct.length <= 6) {
    const w = Math.min(28, (W - L - R) / (distinct.length * 2));
    bins = distinct.map(x => ({ x0: x, x1: x, c: v.filter(y => y === x).length, w }));
  } else {
    const nb = Math.max(6, Math.min(30, Math.ceil(Math.sqrt(v.length))));
    const a = Math.min(...v), b = Math.max(...v), step = (b - a) / nb || 1;
    bins = Array.from({ length: nb }, (_, i) => ({ x0: a + i * step, x1: a + (i + 1) * step, c: 0 }));
    for (const x of v) bins[Math.min(nb - 1, Math.floor((x - a) / step))].c++;
  }
  const top = Math.max(...bins.map(b => b.c));
  const fy = c => H - B - (c / top) * (H - T - B);
  const bars = bins.map(b => {
    const x = b.w ? fx(b.x0) - b.w / 2 : fx(b.x0) + 0.5;
    const w = b.w || Math.max(1, fx(b.x1) - fx(b.x0) - 1);
    const tip = b.w ? `${fmtNum(b.x0)}: ${b.c}` : `${fmtNum(b.x0)} – ${fmtNum(b.x1)}: ${b.c}`;
    return `<rect class="mc-bar" x="${x}" y="${fy(b.c)}" width="${w}" height="${H - B - fy(b.c)}"><title>${esc(tip)}</title></rect>`;
  }).join("");
  const marks = [];
  if (s.mean !== null) marks.push(`<line class="mc-mean" x1="${fx(s.mean)}" x2="${fx(s.mean)}" y1="${T}" y2="${H - B}"><title>${esc(t("mean {v}", { v: fmtNum(s.mean) }))}</title></line>`);
  if (s.sigma !== null && distinct.length > 6) for (const x of [s.mean - s.sigma, s.mean + s.sigma]) marks.push(`<line class="mc-sigma" x1="${fx(x)}" x2="${fx(x)}" y1="${T}" y2="${H - B}"/>`);
  for (const x of targets) for (const b of [x.min, x.max]) if (b !== null && b !== undefined) marks.push(`<line class="mc-tgt" x1="${fx(b)}" x2="${fx(b)}" y1="${T}" y2="${H - B}"><title>${esc(t("target {b}", { b: boundText(x) }))}</title></line>`);
  const ticks = distinct.length <= 6 ? distinct : [lo + pad, (lo + hi) / 2, hi - pad];
  // the outer labels of a histogram lean inwards, so that they stay inside the drawing
  const anchor = i => (distinct.length <= 6 ? "middle" : i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle");
  const axis = ticks.map((x, i) => `<text class="sc-tick" x="${fx(x)}" y="${H - B + 14}" text-anchor="${anchor(i)}">${esc(fmtNum(x))}</text>`).join("");
  return `<svg class="mc-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Samples"))}">${bars}${marks.join("")}<line class="sc-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"/>${axis}<text class="sc-label" x="${W / 2}" y="${H - 4}" text-anchor="middle">${esc(unit && unit !== "1" ? unit : "")}</text></svg>`;
}

/* ------------------------------------------------------------------ mounting */

async function readSamples(run) {
  const url = rawUrl(run.raw, run.samples);
  if (!url) throw new Error(t("no place to read it from"));
  const bytes = await getBytes(url);
  const hash = await sha256Hex(bytes);
  const state = hash === null ? "unchecked" : hash === run.samples_sha256 ? "ok" : "bad";
  const text = decodeText(bytes);
  if (text === null) throw new Error(t("not text"));
  return { url, state, parsed: state === "bad" ? null : parseSamples(text) };
}

const checkMark = state => (state === "ok" ? st("multi", t("matches the index"))
  : state === "bad" ? st("disputed", t("differs from the index"), t("This is not the object's file: the place it was read from holds something else."))
  : st("none", t("not checked"), t("This page cannot compute SHA-256 here (it needs https or this machine).")));

function samplesHtml(d, r) {
  const me = d.runs.find(x => x.name === d.self) || {};
  const p = r.parsed;
  if (!p || !p.ok) return `<p class="faint">${esc(t("samples.csv does not keep the format of B37: its first line is not sample followed by the metrics."))}</p>`;
  const diff = recordedVsFile(me.stats, p);
  const head = `<div class="file-head"><b class="mono">${esc(me.samples)}</b><span class="faint">${esc(t("{n} samples", { n: p.rows.length }))}</span>${checkMark(r.state)}`
    + (diff.length ? st("disputed", t("statistics differ from the samples"), diff.slice(0, 6).join("; ")) : st("multi", t("statistics agree with the samples"), t("n, failed, mean, sigma, min and max of every metric, computed from samples.csv, are what the record wrote")))
    + (p.bad ? st("warn", t("{n} lines not read", { n: p.bad })) : "")
    + `<span class="right"><a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">${esc(t("Raw"))} ↗</a></span></div>`;
  const cards = p.metrics.map((m, i) => {
    const xs = p.rows.map(row => row.vals[i]);
    const s = statsOf(xs);
    const def = d.defs[m] || {};
    const tg = d.targets.filter(x => x.metric === m);
    const held = tg.map(x => {
      const k = xs.filter(v => meets(x, v)).length;
      return `<div class="${k === xs.length ? "tgt-ok" : "tgt-miss"}">${esc(t("Target {b}{p}: {k} of {n} samples meet it", { b: boundText(x), p: x.preset ? ` (${x.preset})` : "", k, n: xs.length }))}</div>`;
    }).join("");
    return `<div class="mc-card"><div class="mc-card-head"><b class="mono">${esc(m)}</b> <span class="faint">${esc(t("mean {m}, sigma {s}", { m: fmtNum(s.mean), s: fmtNum(s.sigma) }))}${def.unit && def.unit !== "1" ? ` ${esc(def.unit)}` : ""}</span></div>${histogram(xs, s, tg, def.unit)}${held}</div>`;
  }).join("");
  const legend = `<p class="faint mc-legend"><i class="mc-key-mean"></i>${esc(t("mean"))} <i class="mc-key-sigma"></i>${esc(t("mean ± sigma"))}${d.targets.length ? ` <i class="mc-key-tgt"></i>${esc(t("target of the circuit"))}` : ""}</p>`;
  const rows = p.rows.slice(0, SHOWN).map(row => `<tr><td class="r num">${row.k}</td>${row.vals.map(x => `<td class="r num">${x === null ? dash : esc(fmtNum(x))}</td>`).join("")}</tr>`).join("");
  const tableHtml = `<details class="fold"><summary>${esc(t("Every sample"))} <span class="hint">${esc(t("{n} lines", { n: p.rows.length }))}</span></summary><div class="body"><div class="scroll mc-table"><table><thead><tr><th class="r">${esc(t("Sample"))}</th>${p.metrics.map(m => `<th class="r mono">${esc(m)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>${p.rows.length > SHOWN ? `<p class="faint">${esc(t("The first {n} lines are shown; open the raw file for all of it.", { n: SHOWN }))}</p>` : ""}</div></details>`;
  return head + `<div class="mc-grid">${cards}</div>` + legend + tableHtml;
}

/** Which samples a record ran and how, in words. */
export function runText(x) {
  const last = Number(x.first) + Number(x.points) - 1;
  const how = x.run === "batch" ? t("all in one simulation") : x.run === "each" ? t("each in a simulation of its own") : String(x.run ?? "");
  return t("{samples}, {how}", { samples: t("samples {a} to {b}", { a: x.first, b: Number.isFinite(last) ? last : "?" }), how });
}

function compareHtml(d, me, results) {
  const rows = d.runs.filter(x => x.name !== d.self).map(x => {
    const r = results.get(x.name);
    const link = `<a href="#/${esc(x.name)}" class="mono" title="${esc(x.name)}">${esc(short(x.name))}</a>`;
    let how = "", res = `<span class="faint">${esc(t("Loading {file}…", { file: x.samples || "" }))}</span>`;
    if (r && r.error) res = `<span class="faint">${esc(r.error)}</span>`;
    else if (r && r.mode === "samples") {
      how = esc(t("sample by sample"));
      res = r.ok ? st("multi", t("reproduces"), t("{n} samples in both, every metric within its tolerance", { n: r.compared }))
        : r.compared ? `${st("disputed", t("differs"))} <span class="faint">${esc(t("{d} of {n} samples compared", { d: new Set(r.diffs.map(q => q.k)).size, n: r.compared }))}; ${esc(r.diffs.slice(0, 3).map(q => t("sample {k} {m}: {x} and {y}", { k: q.k, m: q.m, x: fmtNum(q.x), y: fmtNum(q.y) })).join("; "))}</span>`
          : `<span class="faint">${esc(t("no sample in both"))}</span>`;
    } else if (r && r.mode === "statistics") {
      how = esc(t("by statistics"));
      const bad = r.rows.filter(q => !q.skipped && !q.ok).map(q => q.m);
      res = (r.ok ? st("multi", t("statistically consistent"), t("Not a reproduction: other samples, consistent in their statistics (B37)"))
        : r.rows.some(q => !q.skipped) ? st("disputed", t("statistically inconsistent"), bad.join(", ")) : `<span class="faint">${esc(t("no metric with two samples or more in both"))}</span>`)
        + (r.rows.some(q => q.binaryUnknown) ? ` <span class="faint">${esc(t("(samples.csv not read: a metric of 0 and 1 was compared as any other)"))}</span>` : "");
    }
    return [link, esc(runText(x)), esc(x.simulator || "—"), how || dash, res];
  });
  return `<div class="scroll"><table><thead><tr><th>${esc(t("Record"))}</th><th>${esc(t("Samples"))}</th><th>${esc(t("Simulator"))}</th><th>${esc(t("How compared"))}</th><th>${esc(t("Result"))}</th></tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    + `<p class="faint">${esc(t("This record runs {r}.", { r: runText(me) }))} ${esc(t("Records of the same circuit, testbenches, probes and conditions, the statistics but which samples and how, are compared sample by sample when they ran the same samples alike (the same simulator, and with lhs the same number), each metric within its tolerance; else by their statistics, which says they are consistent, not that one reproduces the other (B37)."))}</p>`;
}

/** Fill a record's samples panel and, when its group has other records, its comparison panel. */
export function mountMc(box, d) {
  const me = d.runs.find(x => x.name === d.self);
  const samplesBox = box.querySelector("[data-mc=samples]");
  const cmpBox = box.querySelector("[data-mc=compare]");
  if (!me || !me.samples) { if (samplesBox) samplesBox.innerHTML = `<p class="faint">${esc(t("This record has no evidence/samples.csv."))}</p>`; return; }
  const results = new Map();
  const paintCmp = () => { if (cmpBox) cmpBox.innerHTML = compareHtml(d, me, results); };
  paintCmp();
  const mine = readSamples(me);
  mine.then(r => { if (samplesBox) samplesBox.innerHTML = samplesHtml(d, r); })
    .catch(e => { if (samplesBox) samplesBox.innerHTML = `<p class="faint">${esc(t("Could not fetch {file} from its library ({e}).", { file: me.samples, e: e.message }))}</p>`; });
  for (const x of d.runs.filter(y => y.name !== d.self)) {
    Promise.all([mine.catch(() => null), x.samples ? readSamples(x).catch(() => null) : null]).then(([a, b]) => {
      results.set(x.name, compare(me, x, a && a.parsed, b && b.parsed, d.defs));
      paintCmp();
    }).catch(e => { results.set(x.name, { error: e.message }); paintCmp(); });
  }
}
