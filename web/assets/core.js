// Gazettoa: shared state, translation, data loading and small pieces of markup.
// Everything shown from a library is text of others: it is escaped, never run, never followed.

export const S = {
  site: null,          // data/site.json
  lang: "en",
  langs: [],           // i18n/languages.json
  catalog: {},         // English text -> translation, for S.lang
};

const JSON_CACHE = new Map();
const TEXT_CACHE = new Map();
// a file is read whole up to RAW_MAX, to check it against the index and to draw it; its text is
// shown up to SHOW_MAX
const RAW_MAX = 8 << 20;
export const SHOW_MAX = 1 << 20;

/* ---------- translation: t('English text', {vars}); catalogs keyed by the English ---------- */
export function t(text, vars = {}) {
  const key = String(text).replace(/\s+/g, " ");
  let s = S.lang !== "en" && S.catalog[key] ? S.catalog[key] : text;
  for (const [k, v] of Object.entries(vars)) s = s.split("{" + k + "}").join(String(v));
  return s;
}

/* ---------- data ---------- */
function bust(url) {
  const b = S.site && S.site.built ? S.site.built : "";
  return b ? url + (url.includes("?") ? "&" : "?") + "b=" + encodeURIComponent(b) : url;
}

export function getJSON(url, { fresh = false } = {}) {
  if (!fresh && JSON_CACHE.has(url)) return JSON_CACHE.get(url);
  const p = fetch(fresh ? url : bust(url), fresh ? { cache: "no-cache" } : {}).then(r => {
    if (!r.ok) throw Object.assign(new Error(`${r.status} ${url}`), { status: r.status });
    return r.json();
  });
  JSON_CACHE.set(url, p);
  p.catch(() => JSON_CACHE.delete(url));
  return p;
}

/** The bytes of a file of an object: from the copy in the site, a library's host at the commit
 * read, or a checkout on this machine. At most RAW_MAX bytes. */
export function getBytes(url) {
  if (TEXT_CACHE.has(url)) return TEXT_CACHE.get(url);
  const p = fetch(url).then(async r => {
    if (!r.ok) throw new Error(`${r.status}`);
    const len = Number(r.headers.get("content-length") || 0);
    if (len > RAW_MAX) throw Object.assign(new Error(t("too large to show ({n} bytes)", { n: len })), { large: true });
    const b = new Uint8Array(await r.arrayBuffer());
    if (b.length > RAW_MAX) throw Object.assign(new Error(t("too large to show ({n} bytes)", { n: b.length })), { large: true });
    return b;
  });
  TEXT_CACHE.set(url, p);
  p.catch(() => TEXT_CACHE.delete(url));
  return p;
}

/** Text of a file, or null when it is not UTF-8 text. */
export function decodeText(bytes) {
  if (bytes.includes(0)) return null;
  try { return new TextDecoder("utf-8", { fatal: true }).decode(bytes); } catch (e) { return null; }
}

export async function getText(url) {
  const text = decodeText(await getBytes(url));
  if (text === null) throw new Error(t("not text"));
  return text;
}

/** The SHA-256 of bytes in hexadecimal, or null where the page cannot compute it (not a secure context). */
export async function sha256Hex(bytes) {
  if (!globalThis.crypto || !crypto.subtle) return null;
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return [...d].map(x => x.toString(16).padStart(2, "0")).join("");
}

/** What a page leaves for the code that fills it after it is shown (app.js), by an id in its markup. */
export const REG = new Map();
let regSeq = 0;
export function register(value) {
  const id = "r" + (++regSeq);
  REG.set(id, value);
  return id;
}

export const shardOf = n => {
  const h = String(n).split("_")[1] || "";
  return h.length >= 2 ? h.slice(0, 2) : "__";
};
export const objUrl = n => `data/obj/${shardOf(n)}/${n}.json`;
export const ifcUrl = n => `data/ifc/${shardOf(n)}/${n}.json`;
export const libUrl = k => `data/lib/${k}.json`;
export const rawUrl = (prefix, path) => (prefix ? prefix.replace(/\/+$/, "") + "/" + String(path).split("/").map(encodeURIComponent).join("/") : null);

/* ---------- text ---------- */
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const NAME_RE = /^[a-z][a-z0-9]*_[0-9a-f]{40}$/;
/** The kind of an object (ifc, ckt, tb, evd, doc, lib), from the prefix of its name through the type table
 *  the build writes into site.json (the type names of TOA are kept in builder/gaze/fields.py). */
export const prefixOf = n => {
  const p = String(n).split("_")[0];
  const types = (S.site && S.site.types) || {};
  return Object.keys(types).find(k => types[k] === p) || p;
};
export const short = n => String(n).slice(0, 12) + "…";
/** The day of a date, in UTC like the dates of the builds: a commit's date carries its committer's
 * offset, and cut as written it could fall a day after the build that saw it. */
export function fmtDate(s) {
  if (!s) return "—";
  const str = String(s);
  if (/T\d\d:\d\d/.test(str)) {
    const d = new Date(str);
    if (!Number.isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  }
  return str.slice(0, 10);
}
export const fmtCommit = c => (c ? String(c).slice(0, 10) : "—");

export function fmtNum(v) {
  if (v && typeof v === "object" && "float" in v) return String(v.float);
  const n = Number(v);
  if (typeof v === "boolean" || v === null || v === undefined || !Number.isFinite(n)) return String(v ?? "—");
  if (n !== 0 && (Math.abs(n) >= 1e5 || Math.abs(n) < 1e-3)) return n.toExponential(3).replace(/\.?0+e/, "e");
  return String(Math.round(n * 1e6) / 1e6);
}

/** A value of a manifest as YAML-like text: special floats as `.inf`, mappings and lists indented. */
export function yamlish(v, ind = "") {
  const scalar = x => {
    if (x === null) return "null";
    if (typeof x === "string") return /^[\w.@/+-][\w .@/+:-]*$/.test(x) && !/^(true|false|null|~|[\d.+-]+)$/i.test(x) && !/:\s|\s$/.test(x) ? x : JSON.stringify(x);
    if (typeof x === "object" && x && Object.keys(x).length === 1 && "float" in x) return String(x.float);
    return String(x);
  };
  const isLeaf = x => x === null || typeof x !== "object" || (Object.keys(x).length === 1 && "float" in x);
  if (isLeaf(v)) return scalar(v);
  const out = [];
  if (Array.isArray(v)) {
    if (!v.length) return "[]";
    for (const x of v) {
      if (isLeaf(x)) out.push(`${ind}- ${scalar(x)}`);
      else out.push(`${ind}- ${yamlish(x, ind + "  ").replace(/^\s+/, "")}`);
    }
  } else {
    const ks = Object.keys(v);
    if (!ks.length) return "{}";
    for (const k of ks) {
      const x = v[k];
      if (isLeaf(x) || (Array.isArray(x) && !x.length) || (!Array.isArray(x) && !Object.keys(x).length)) out.push(`${ind}${k}: ${isLeaf(x) ? scalar(x) : Array.isArray(x) ? "[]" : "{}"}`);
      else out.push(`${ind}${k}:\n${yamlish(x, ind + "  ")}`);
    }
  }
  return out.join("\n");
}

/** Markdown of others, the safe part only: headings, paragraphs, lists, code. No links, images or HTML. */
export function renderMd(raw) {
  const lines = String(raw ?? "").replace(/\r\n/g, "\n").replace(/^---\n[\s\S]*?\n---\n/, "").trim().split("\n");
  const inline = s => esc(s).replace(/`([^`\n]+)`/g, (_, c) => NAME_RE.test(c) ? `<a href="#/${c}"><code>${c}</code></a>` : `<code>${c}</code>`).replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  const out = [];
  let code = null, list = false, para = [];
  const flush = () => { if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; } };
  const close = () => { if (list) { out.push("</ul>"); list = false; } };
  for (const line of lines) {
    const s = line.trim();
    if (s.startsWith("```")) {
      flush(); close();
      if (code === null) code = [];
      else { out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`); code = null; }
      continue;
    }
    if (code !== null) { code.push(line); continue; }
    if (!s) { flush(); close(); continue; }
    const h = /^(#{1,4})\s+(.*)$/.exec(s);
    if (h) { flush(); close(); const l = Math.min(3, h[1].length); out.push(`<h${l}>${inline(h[2])}</h${l}>`); continue; }
    const li = /^(?:[-*]|\d+\.)\s+(.*)$/.exec(s);
    if (li) { flush(); if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(li[1])}</li>`); continue; }
    if (list && /^\s{2,}/.test(line)) { out[out.length - 1] = out[out.length - 1].replace(/<\/li>$/, " " + inline(s) + "</li>"); continue; }
    close();
    para.push(s);
  }
  if (code !== null) out.push(`<pre><code>${esc(code.join("\n"))}</code></pre>`);
  flush(); close();
  return `<div class="md-body">${out.join("")}</div>`;
}

export function firstHeading(md) {
  const m = /^#\s+(.+)$/m.exec(String(md || ""));
  return m ? m[1].trim() : "";
}

/* ---------- names and links ---------- */
const TYPE_NAMES = { ifc: "Interface", ckt: "Circuit", tb: "Testbench", evd: "Evidence record", doc: "Document", lib: "Frozen library" };
export const typeName = p => t(TYPE_NAMES[p] || "Object");
export const TYPE_PLURAL = { ifc: "Interfaces", ckt: "Circuits", tb: "Testbenches", evd: "Evidence records", doc: "Documents", lib: "Frozen libraries" };
/** The order types are listed in. */
export const TYPE_ORDER = ["ifc", "ckt", "tb", "evd", "doc", "lib"];

/** A link showing the readable name; the object name is in the title and in a quiet short form. */
export function nameLink(n, names, { withShort = false } = {}) {
  if (!n) return `<span class="faint">—</span>`;
  const e = names && names[n];
  const d = e ? e[0] : short(n);
  const absent = e && !e[2];
  const link = `<a href="#/${esc(n)}" title="${esc(n)}"${absent ? ' class="faint"' : ""}>${esc(d)}</a>`;
  return withShort ? `${link} <span class="oname-short" title="${esc(n)}">${esc(short(n))}</span>` : link;
}

const COPY_ICON = '<svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true"><rect x="5" y="5" width="9" height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
/** The object name, shortened, as a button that copies the full name. */
export const nameChip = n => `<button type="button" class="name-chip" data-copy="${esc(n)}" title="${esc(t("Copy the object name"))}: ${esc(n)}">${esc(short(n))}${COPY_ICON}</button>`;
export const linkChip = () => `<button type="button" class="name-chip" data-copy-link="1" title="${esc(t("Copy the address of this page"))}">${esc(t("link"))}${COPY_ICON}</button>`;
/** A link to an Atom feed of the site, when the build wrote feeds (it needs the site's address). */
export const feedLink = (rel, label = "") => (S.site && S.site.feeds ? `<a class="feed-link" href="${esc(rel)}" title="${esc(t("Atom feed"))}">${esc(label || t("Atom feed"))}</a>` : "");
export const libLink = k => `<a href="#/lib/${esc(k)}">${esc(k)}</a>`;
export const libLinks = ks => (ks && ks.length ? ks.map(libLink).join(", ") : `<span class="faint">—</span>`);
export const st = (cls, txt, tip = "") => `<span class="st ${cls}"${tip ? ` title="${esc(tip)}"` : ""}>${esc(txt)}</span>`;
export const tag = (txt, cls = "") => `<span class="tag ${cls}">${esc(txt)}</span>`;
export const helpBtn = html => `<button type="button" class="qmark" data-help="${esc(html)}" aria-label="${esc(t("Help"))}" aria-expanded="false">?</button>`;
export const dash = `<span class="faint">—</span>`;

/** Which libraries mark an object latest (TOA 5.2): each library's own word, shown as it is. */
export const LATEST_HELP = () => t("The libraries whose list marks it latest: each recommends it in place of the earlier generations of its series. A mark is the library's word, not the object's; libraries may differ (TOA 5.2).");
export function latestMark(libs) {
  if (!libs || !libs.length) return "";
  // the libraries are links: the text is translated around a mark, then the links are put in
  const by = esc(t("marked by {libs}", { libs: "\u0001" })).replace("\u0001", `</span>${libLinks(libs)}<span class="faint">`);
  return `${st("info", t("latest"), LATEST_HELP())} <span class="faint">${by}</span>`;
}

export function validMark(v) {
  if (!v.present) return st("none", t("not in this instance"));
  return v.valid ? st("multi", t("verified by toa"), t("The index of toa checked this object from its files")) : st("disputed", t("does not pass"));
}

/* ---------- layout pieces ---------- */
export const panel = (title, body, { sub = "", right = "", cls = "", id = "" } = {}) =>
  `<section class="panel ${cls}"${id ? ` id="${esc(id)}"` : ""}><header><h2>${title}</h2>${sub ? `<span class="sub">${sub}</span>` : ""}${right ? `<div class="right">${right}</div>` : ""}</header>${body}</section>`;
export const bodyDiv = html => `<div class="body">${html}</div>`;
export const emptyBody = txt => `<div class="body empty">${esc(txt)}</div>`;
export function table(head, rows, { cls = "" } = {}) {
  if (!rows.length) return "";
  return `<div class="scroll"><table class="${cls}"><thead><tr>${head.map(h => (typeof h === "string" ? `<th>${h}</th>` : `<th class="${h.cls || ""}">${h.html}</th>`)).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td${c && c.cls ? ` class="${c.cls}"` : ""}>${c && typeof c === "object" && "html" in c ? c.html : c ?? ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
export function kv(pairs) {
  const rows = pairs.filter(p => p && p[1] !== undefined && p[1] !== null && p[1] !== "");
  if (!rows.length) return "";
  return `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
}
export const fold = (title, body, { hint = "", open = false } = {}) =>
  `<details class="fold"${open ? " open" : ""}><summary>${title}${hint ? ` <span class="hint">${hint}</span>` : ""}</summary><div class="body">${body}</div></details>`;
export const pre = text => `<pre>${esc(text)}</pre>`;

export function toast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 2600);
}

/* ---------- the text of a netlist for the RNL viewer ---------- */
// The netlist goes to the RNL viewer as text, by postMessage: a viewer on another origin cannot
// be relied on to fetch files from this site's libraries (a page on this machine, a host
// without CORS). Text has no sibling files, so the page puts them into it: the files a netlist
// includes from its own object, and the symbol package of each interface that draws one of its
// blocks (type ifc: chosen by references, not by the package's name). Pure: tests/viewer_text.test.mjs.
// A record starts with the comment character in column 1, one space and @RNL (RNL 0.4).
export const RNL_RECORD = /^(\*|\/\/) @RNL\b/m;
const HEADER = /^(\*|\/\/) @RNL\s*\(\s*type\s*=\s*"header"\s*\)/;

/** The lines of the first record that starts with `re`, as [first, last] indexes, braces balanced. */
function recordSpan(lines, re) {
  const i = lines.findIndex(l => re.test(l));
  if (i < 0) return null;
  let depth = 0, seen = false;
  for (let j = i; j < lines.length; j++) {
    for (const c of lines[j]) { if (c === "{") { depth++; seen = true; } else if (c === "}") depth--; }
    if (seen && depth <= 0) return [i, j];
  }
  return [i, i];
}

const PKG_NAME = /@PACKAGE\s*\(\s*name\s*=\s*"([^"]+)"/;
const USE_PACKAGE = /@USE-PACKAGE\s*\(([^)]*)\)/g;
const MARK = /^(\*|\/\/) ?/;
const argOf = (args, key) => { const m = new RegExp(`\\b${key}\\s*=\\s*"([^"]*)"`).exec(args); return m ? m[1] : null; };

/** The statements of a record's braces, split at the semicolons outside strings and brackets. */
function statements(inner) {
  const out = [];
  let depth = 0, quote = false, cur = "";
  for (let i = 0; i < inner.length; i++) {
    const c = inner[i];
    if (quote) { if (c === "\\") { cur += c + (inner[++i] || ""); continue; } if (c === '"') quote = false; }
    else if (c === '"') quote = true;
    else if ("([{".includes(c)) depth++;
    else if (")]}".includes(c)) depth--;
    else if (c === ";" && depth === 0) { if (cur.trim()) out.push(cur.trim()); cur = ""; continue; }
    cur += c;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

/** A package file as record lines written with *, which SPICE and Spectre both read, and the
 * statements of its header record other than VERSION and PACKAGE (its devices, the packages it
 * uses). A package file is plain RNL (a `.rnl` file) or, like a netlist, RNL in comments. */
function packageParts(text) {
  let pl = String(text).replace(/\r\n/g, "\n").split("\n");
  pl = pl.some(l => HEADER.test(l)) ? pl.map(l => l.replace(/^\/\//, "*")) : pl.map(l => (l ? `* ${l}` : "*"));
  const ps = recordSpan(pl, HEADER);
  let stmts = [];
  if (ps) {
    const head = pl.slice(ps[0], ps[1] + 1).map(l => l.replace(MARK, "")).join("\n");
    stmts = statements(head.slice(head.indexOf("{") + 1, head.lastIndexOf("}"))).filter(x => !/^@(VERSION|PACKAGE)\s*\(/.test(x));
  }
  return { body: pl.filter((_, i) => !ps || i < ps[0] || i > ps[1]), stmts };
}

/** One text for the viewer: includes of the object's own files put in place, and the packages the
 * netlist's header uses put after it, with their USE-PACKAGE taken out and the rest of their own
 * header (devices, the packages they use) moved into the netlist's. A package comes from the
 * symbol of an interface (by its name) or from a file of the object (by `path`). */
export function textForViewer(text, others, packages) {
  let lines = String(text).replace(/\r\n/g, "\n").split("\n");
  const INC = /^\s*\.?inc(?:lude)?\s+["']?([^"'\s]+)["']?\s*$/i;
  lines = lines.flatMap(l => {
    const m = INC.exec(l);
    const p = m && m[1].replace(/^\.\//, "");
    return p && others[p] !== undefined ? [`* (Gazettoa: the file ${p} of the object, included here)`, ...String(others[p]).replace(/\r\n/g, "\n").split("\n")] : [l];
  });
  const span = recordSpan(lines, HEADER);
  if (!span) return lines.join("\n");
  const mark = MARK.exec(lines[span[0]])[1];
  let head = lines.slice(span[0], span[1] + 1).map(l => l.replace(MARK, "")).join("\n");
  const uses = [...head.matchAll(USE_PACKAGE)].map(m => ({ all: m[0], name: argOf(m[1], "name"), path: argOf(m[1], "path") }));
  const symbols = new Map();
  for (const pk of packages) {
    const m = PKG_NAME.exec(pk.text);
    if (m && !symbols.has(m[1])) symbols.set(m[1], pk);
  }
  const chosen = [];
  for (const u of uses) {
    const own = u.path ? others[u.path.replace(/^\.\//, "")] : undefined;
    if (own !== undefined && own !== null) chosen.push({ use: u, text: own, label: `the package ${u.name}, the file ${u.path} of the object` });
    else if (u.name && symbols.has(u.name)) chosen.push({ use: u, text: symbols.get(u.name).text, label: `the symbol package ${u.name} of the interface ${symbols.get(u.name).ifc}, put here from its symbol.rnl` });
  }
  if (!chosen.length) return lines.join("\n");
  const add = [], extra = [];
  const named = new Set(uses.map(u => u.name));
  for (const c of chosen) {
    head = head.replace(c.use.all, "\u0001");
    const { body, stmts } = packageParts(c.text);
    for (const x of stmts) {
      // a package it uses once, unless the netlist names it already; any other statement once
      const use = /^@USE-PACKAGE\s*\(([^)]*)\)$/.exec(x);
      if (use) {
        const n = argOf(use[1], "name");
        if (named.has(n)) continue;
        named.add(n);
      } else if (extra.includes(x)) continue;
      extra.push(x);
    }
    add.push(`* (Gazettoa: ${c.label})`, ...body);
  }
  head = head.replace(/\u0001\s*;?/g, "").replace(/\{\s*;/, "{");
  if (extra.length) {
    const close = head.lastIndexOf("}");
    const before = head.slice(0, close).replace(/\s+$/, "");
    head = `${before}${/[{;]$/.test(before) ? "" : ";"}\n  ${extra.join(";\n  ")}\n${head.slice(close)}`;
  }
  const newHead = head.split("\n").map(l => (l ? `${mark} ${l}` : mark));
  return [...lines.slice(0, span[0]), ...newHead, ...add, ...lines.slice(span[1] + 1)].join("\n");
}

