// Gazettoa: the page chrome (top bar, theme, language, quick search), the router, and the
// filling of slots with files fetched from libraries.
import { S, t, esc, getJSON, getText, getBytes, decodeText, sha256Hex, rawUrl, st, REG, renderMd, toast, short, prefixOf, NAME_RE, fmtDate, RNL_RECORD, textForViewer, SHOW_MAX } from "./core.js";
import { mountSelection } from "./selection.js";
import { pageHome, pageIfcName, pageIfc, pageObject, pageLibrary, pageSearch, pageUpdates, pageAbout, pageAgent, srcLabel } from "./pages.js";

const app = document.getElementById("app");
const root = document.documentElement;
const LS_LANG = "gaze-lang";
const LS_THEME = "gaze-theme";

function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* private mode */ } }
function load(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }

/* ---------------------------------------------------------------- language */
function pickLang() {
  const codes = S.langs.map(l => l.code);
  const q = new URLSearchParams(location.hash.split("?")[1] || "").get("lang") || new URLSearchParams(location.search).get("lang");
  if (q && codes.includes(q)) return q;
  const saved = load(LS_LANG);
  if (saved && codes.includes(saved)) return saved;
  for (const nav of navigator.languages || [navigator.language || "en"]) {
    const hit = S.langs.find(l => (l.matches || [l.code]).some(m => nav.toLowerCase() === m.toLowerCase() || nav.toLowerCase().startsWith(m.toLowerCase() + "-")));
    if (hit) return hit.code;
  }
  return "en";
}

async function setLang(code, { remember = true } = {}) {
  S.lang = code;
  if (remember) store(LS_LANG, code);
  S.catalog = {};
  if (code !== "en") {
    try { S.catalog = await getJSON(`i18n/${code}/web.json`); } catch (e) { S.catalog = {}; }
  }
  const l = S.langs.find(x => x.code === code);
  root.lang = (l && l.html_lang) || code;
  paintChrome();
  route();
}

/* ---------------------------------------------------------------- theme */
const darkMq = window.matchMedia("(prefers-color-scheme: dark)");
const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : darkMq.matches);
const SUN = '<svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3" fill="currentColor"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.5 1.5M11.5 11.5L13 13M3 13l1.5-1.5M11.5 4.5L13 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/></svg>';
const MOON = '<svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true"><path d="M13.5 9.8A6 6 0 0 1 6.2 2.5a6 6 0 1 0 7.3 7.3z" fill="currentColor"/></svg>';
function paintTheme() {
  const b = document.getElementById("theme-btn");
  b.innerHTML = isDark() ? `${SUN}<span>${esc(t("Light"))}</span>` : `${MOON}<span>${esc(t("Dark"))}</span>`;
  b.title = isDark() ? t("Switch to the light theme") : t("Switch to the dark theme");
}
const savedTheme = load(LS_THEME);
if (savedTheme === "light" || savedTheme === "dark") root.dataset.theme = savedTheme;
document.getElementById("theme-btn").addEventListener("click", () => {
  const next = isDark() ? "light" : "dark";
  root.dataset.theme = next;
  store(LS_THEME, next);
  paintTheme();
  syncEmbedTheme();
});
darkMq.addEventListener("change", () => { paintTheme(); syncEmbedTheme(); });

/* ---------------------------------------------------------------- chrome */
// the interfaces are listed by the search page, which an interface's page belongs to
const NAV = [["#/", "Home", r => r === ""], ["#/search", "Search", r => r.startsWith("search") || r.startsWith("ifc/") || prefixOf(r.split("/")[0]) === "ifc"], ["#/updates", "Updates", r => r.startsWith("updates")], ["#/about", "About", r => r.startsWith("about")]];

// Gazettoa has no released version yet: every page says so, in the top bar and in a band below it.
// Set to false at the first release.
const PREVIEW = true;

function paintChrome() {
  const s = S.site;
  document.getElementById("brand-title").textContent = (s && s.title) || "Gazettoa";
  const tag = document.getElementById("preview-tag");
  const band = document.getElementById("preview-band");
  tag.hidden = band.hidden = !PREVIEW;
  if (PREVIEW) {
    tag.textContent = t("preview");
    band.firstElementChild.textContent = t("Preview: Gazettoa has no released version yet, so its pages, addresses and data may still change.");
  }
  const r = location.hash.replace(/^#\/?/, "");
  document.getElementById("nav").innerHTML = NAV.map(([href, label, on]) => `<a href="${href}" class="${on(r) ? "on" : ""}">${esc(t(label))}</a>`).join("");
  const seg = document.getElementById("lang-seg");
  seg.setAttribute("aria-label", t("Language"));
  seg.innerHTML = S.langs.map(l => `<button type="button" data-lang="${esc(l.code)}" class="${l.code === S.lang ? "on" : ""}" title="${esc(l.name)}">${esc(l.short || l.code)}</button>`).join("");
  const q = document.getElementById("qbar-in");
  q.placeholder = t("Search names, interfaces, processes");
  q.setAttribute("aria-label", t("Search"));
  paintTheme();
  const foot = document.querySelector("#site-foot .wrap");
  if (s) {
    foot.innerHTML = [
      `<span>${esc(t("Built {d}", { d: fmtDate(s.built) }))}</span>`,
      `<span>${esc(t("Index by {tool}, TOA {v}", { tool: s.index.tool || "toa", v: s.index.standard || "?" }))}</span>`,
      `<span>${esc(t("Objects are their authors'; each keeps its own license."))}</span>`,
      `<a href="#/agent">${esc(t("For agents"))}</a>`,
      `<a href="llms.txt">llms.txt</a>`,
      s.repository ? `<a href="${esc(s.repository)}" target="_blank" rel="noopener noreferrer">${esc(t("Code of this site"))}</a>` : "",
    ].join("");
  }
}

document.getElementById("lang-seg").addEventListener("click", e => {
  const b = e.target.closest("button[data-lang]");
  if (b && b.dataset.lang !== S.lang) setLang(b.dataset.lang);
});

/* ---------------------------------------------------------------- quick search */
const qIn = document.getElementById("qbar-in");
const qDrop = document.getElementById("qdrop");
let qSel = -1;
let qItems = [];
async function quickSearch() {
  const q = qIn.value.trim().toLowerCase();
  if (!q) { qDrop.hidden = true; return; }
  const all = await getJSON("data/search.json");
  qItems = all.filter(e => e.n.startsWith(q) || e.d.toLowerCase().includes(q) || (e.ifc || "").toLowerCase().includes(q)).slice(0, 12);
  qSel = qItems.length ? 0 : -1;
  qDrop.innerHTML = qItems.length
    ? qItems.map((e, i) => `<a class="qitem${i === qSel ? " act" : ""}" href="#/${esc(e.n)}"><span><span class="tag prefix">${esc(e.p)}</span> ${esc(e.d)}</span><span class="oname-short">${esc(short(e.n))}</span></a>`).join("") + `<a class="qitem" href="#/search?q=${encodeURIComponent(qIn.value.trim())}"><span>${esc(t("All results"))} →</span></a>`
    : `<div class="qitem"><span class="faint">${esc(t("Nothing found."))}</span></div>`;
  qDrop.hidden = false;
}
qIn.addEventListener("input", () => { quickSearch().catch(() => {}); });
qIn.addEventListener("keydown", e => {
  const links = [...qDrop.querySelectorAll("a.qitem")];
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    qSel = Math.max(0, Math.min(links.length - 1, qSel + (e.key === "ArrowDown" ? 1 : -1)));
    links.forEach((a, i) => a.classList.toggle("act", i === qSel));
  } else if (e.key === "Enter") {
    e.preventDefault();
    const v = qIn.value.trim();
    if (NAME_RE.test(v)) location.hash = "#/" + v;
    else if (links[qSel]) location.hash = links[qSel].getAttribute("href");
    else location.hash = "#/search?q=" + encodeURIComponent(v);
    qDrop.hidden = true;
    qIn.blur();
  } else if (e.key === "Escape") {
    qDrop.hidden = true;
    qIn.blur();
  }
});
document.addEventListener("click", e => { if (!e.target.closest(".qwrap")) qDrop.hidden = true; });
document.addEventListener("keydown", e => {
  if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "")) { e.preventDefault(); qIn.focus(); }
});

/* ---------------------------------------------------------------- copy, help */
async function copy(text, msg) {
  try { await navigator.clipboard.writeText(text); toast(msg); } catch (e) { toast(text); }
}
document.addEventListener("click", e => {
  const c = e.target.closest("[data-copy]");
  if (c) { e.preventDefault(); copy(c.dataset.copy, t("Copied {n}", { n: c.dataset.copyLabel || c.dataset.copy })); return; }
  const l = e.target.closest("[data-copy-link]");
  if (l) { e.preventDefault(); copy(location.href, t("Copied the address of this page")); }
});

const pop = document.getElementById("help-pop");
let pinned = null;
function showHelp(btn) {
  pop.innerHTML = btn.dataset.help;
  pop.hidden = false;
  const r = btn.getBoundingClientRect();
  const left = Math.max(12, Math.min(window.innerWidth - pop.offsetWidth - 12, r.left + r.width / 2 - pop.offsetWidth / 2));
  let top = r.bottom + 7;
  if (top + pop.offsetHeight > window.innerHeight - 12) top = Math.max(12, r.top - pop.offsetHeight - 7);
  pop.style.left = left + "px";
  pop.style.top = top + "px";
}
document.addEventListener("click", e => {
  const b = e.target.closest(".qmark");
  if (b) {
    e.preventDefault();
    if (pinned === b) { pop.hidden = true; pinned = null; return; }
    pinned = b; showHelp(b); return;
  }
  if (!e.target.closest("#help-pop")) { pop.hidden = true; pinned = null; }
}, true);
document.addEventListener("mouseover", e => { const b = e.target.closest(".qmark"); if (b && !pinned) showHelp(b); });
document.addEventListener("mouseout", e => { if (!pinned && e.target.closest(".qmark")) pop.hidden = true; });

/* ---------------------------------------------------------------- files from libraries */
// lock.json (type evd, format lock/1): the tree by path, then the file as written.
function lockHtml(text) {
  let lock = null;
  try { lock = JSON.parse(text); } catch (e) { /* shown as text */ }
  if (!lock || !Array.isArray(lock.tree)) return `<pre>${esc(text)}</pre>`;
  const link = n => (typeof n === "string" && NAME_RE.test(n) ? `<a href="#/${esc(n)}" class="mono" title="${esc(n)}">${esc(short(n))}</a>` : esc(String(n ?? "")));
  const rows = lock.tree.map(r => `<tr><td class="mono">${r.path ? esc(r.path) : `<span class="faint">${esc(t("(the circuit tested)"))}</span>`}</td><td>${link(r.object)}</td><td>${link(r.ifc)}</td><td class="r num">${esc(String(Object.keys(r.files || {}).length))}</td></tr>`).join("");
  return `<div class="scroll"><table><thead><tr><th>${esc(t("Path"))}</th><th>${esc(t("Circuit"))}</th><th>${esc(t("Interface"))}</th><th class="r">${esc(t("Files"))}</th></tr></thead><tbody>${rows}</tbody></table></div><pre>${esc(text)}</pre>`;
}

/* ---------------------------------------------------------------- the files panel */
// A panel registered by pages.js (kind "files"): the files of one object, read from the place
// chosen (a library, or the site's copy) and checked against the SHA-256 of the index.
const checkMark = state => (state === "ok" ? st("multi", t("matches the index"))
  : state === "bad" ? st("disputed", t("differs from the index"), t("This is not the object's file: the place it was read from holds something else."))
  : state === "unchecked" ? st("none", t("not checked"), t("This page cannot compute SHA-256 here (it needs https or this machine)."))
  : `<span class="faint">—</span>`);

async function loadFile(fs, path) {
  const src = fs.sources[fs.src];
  if (!src) throw new Error(t("no place to read it from"));
  const url = rawUrl(src.raw, path);
  const bytes = await getBytes(url);
  const f = fs.files.find(x => x.path === path);
  const hash = await sha256Hex(bytes);
  const state = hash === null ? "unchecked" : f && hash === f.sha256 ? "ok" : "bad";
  fs.checked[`${fs.src}\u0000${path}`] = state;
  return { url, bytes, state, text: decodeText(bytes) };
}

function paintChecks(panel, fs) {
  for (const el of panel.querySelectorAll("[data-file-check]")) el.innerHTML = checkMark(fs.checked[`${fs.src}\u0000${el.dataset.fileCheck}`]);
}

async function showFile(panel, fs, path) {
  const view = panel.querySelector("[data-file-view]");
  if (!view) return;
  fs.open = path;
  for (const b of panel.querySelectorAll("[data-file-open]")) b.classList.toggle("on", b.dataset.fileOpen === path);
  const src = fs.sources[fs.src];
  const url = rawUrl(src.raw, path);
  view.innerHTML = `<p class="faint">${esc(t("Loading {file}…", { file: path }))}</p>`;
  try {
    const r = await loadFile(fs, path);
    if (fs.open !== path) return;
    paintChecks(panel, fs);
    const head = `<div class="file-head"><b class="mono">${esc(path)}</b><span class="faint">${esc(t("{n} bytes", { n: r.bytes.length }))} · ${esc(srcLabel(src))}</span>${checkMark(r.state)}`
      + `<span class="right"><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(t("Raw"))} ↗</a>${r.text !== null ? ` <button type="button" class="btn sm" data-copy-text>${esc(t("Copy"))}</button>` : ""}</span></div>`;
    const cut = r.text !== null && r.text.length > SHOW_MAX;
    const body = r.text === null ? `<p class="faint">${esc(t("Not text; open it to save it."))}</p>`
      : `<pre class="file-text">${esc(cut ? r.text.slice(0, SHOW_MAX) : r.text)}</pre>`
        + (cut ? `<p class="faint">${esc(t("The first {n} characters are shown; open the raw file for all of it.", { n: SHOW_MAX }))}</p>` : "");
    view.innerHTML = head + body;
    const cb = view.querySelector("[data-copy-text]");
    if (cb) cb.addEventListener("click", () => copy(r.text, t("Copied {n}", { n: path })));
  } catch (e) {
    if (fs.open !== path) return;
    view.innerHTML = `<p class="faint">${esc(t("Could not read {file} from {src} ({e}).", { file: path, src: srcLabel(src), e: e.message }))} <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(t("Open it"))} ↗</a></p>`;
  }
}

function mountFiles(panel) {
  const fs = REG.get(panel.dataset.files);
  if (!fs || !fs.sources.length) return;
  panel.addEventListener("click", e => {
    const b = e.target.closest("[data-file-open]");
    if (b) { showFile(panel, fs, b.dataset.fileOpen); return; }
    const all = e.target.closest("[data-check-all]");
    if (all) {
      all.disabled = true;
      (async () => {
        for (const f of fs.files) {
          try { await loadFile(fs, f.path); } catch (err) { fs.checked[`${fs.src}\u0000${f.path}`] = "failed"; }
          paintChecks(panel, fs);
        }
        all.disabled = false;
      })();
    }
  });
  const sel = panel.querySelector("[data-src-select]");
  if (sel) {
    sel.addEventListener("change", () => {
      fs.src = Number(sel.value) || 0;
      paintChecks(panel, fs);
      if (fs.open) showFile(panel, fs, fs.open);
      for (const fn of fs.listeners) fn();
    });
  }
  if (fs.main) showFile(panel, fs, fs.main);
}

/* ---------------------------------------------------------------- schematics */
// The netlist goes to the RNL viewer as text, by postMessage: a viewer on another origin cannot
// be relied on to fetch files from this site's libraries (a page on this machine, a host
// without CORS). Text has no sibling files, so the page puts them into it: the files a netlist
// includes from its own object, and the symbol package of each interface that draws one of its
// blocks (type ifc: chosen by references, not by the package's name).
function viewerUrl(params) {
  const u = new URL(S.site.viewer_url || "https://rich-netlist.github.io/rnl/viewer/", location.href);
  for (const [k, x] of Object.entries(params)) u.searchParams.set(k, x);
  return u;
}

async function prepareDrawing(ds, fs) {
  const d = ds.drawing;
  const main = await loadFile(fs, d.entry);
  if (main.state === "bad") throw new Error(t("{file} differs from the index", { file: d.entry }));
  if (main.text === null) throw new Error(t("{file} is not text", { file: d.entry }));
  const others = {};
  for (const f of d.files.slice(1)) {
    try { const r = await loadFile(fs, f); if (r.state !== "bad" && r.text !== null) others[f] = r.text; } catch (e) { /* left out */ }
  }
  const packages = [];
  for (const sy of d.symbols) {
    if (!sy.file || !sy.sources.length) continue;
    try {
      const b = await getBytes(rawUrl(sy.sources[0].raw, sy.file.path));
      const h = await sha256Hex(b);
      const text = decodeText(b);
      if ((h === null || h === sy.file.sha256) && text !== null) packages.push({ ifc: sy.ifc, text });
    } catch (e) { /* drawn without it */ }
  }
  // a circuit is drawn at the subcircuit its first netlist defines; a testbench at its top level
  const sub = prefixOf(ds.name) === "ckt" ? /^\s*\.?subckt\s+([^\s(]+)/im.exec(main.text) : null;
  return { name: d.entry.split("/").pop(), text: textForViewer(main.text, others, packages), records: RNL_RECORD.test(main.text), level: sub ? sub[1] : null };
}

const EMBEDS = new Set();
function syncEmbedTheme() {
  for (const e of EMBEDS) {
    if (!e.frame.isConnected) { EMBEDS.delete(e); continue; }
    if (e.ready) e.frame.contentWindow.postMessage({ rnl: 1, type: "background", value: isDark() ? "dark" : "light" }, e.origin);
  }
}

function embed(box, drawing) {
  const vu = viewerUrl({ embed: "1", origin: location.origin, background: isDark() ? "dark" : "light" });
  const origin = vu.origin;
  box.innerHTML = `<div class="sch-wrap" data-state="loading"><iframe class="sch-frame" title="${esc(drawing.name)}" src="${esc(vu.href)}"></iframe>`
    + `<button type="button" class="sch-guard"><span>${esc(t("Click to move and zoom the drawing"))}</span></button><div class="sch-status faint">${esc(t("Starting the RNL viewer…"))}</div></div><p class="sch-msg faint" hidden></p>`;
  const wrap = box.querySelector(".sch-wrap");
  const frame = box.querySelector("iframe");
  const status = box.querySelector(".sch-status");
  const msg = box.querySelector(".sch-msg");
  box.querySelector(".sch-guard").addEventListener("click", () => wrap.classList.add("live"));
  wrap.addEventListener("mouseleave", () => wrap.classList.remove("live"));
  const req = "gaze-" + Math.random().toString(36).slice(2);
  const e = { frame, origin, ready: false };
  EMBEDS.add(e);
  // fitted once the viewer has laid the level out, and once more when it has settled
  const fit = () => { for (const ms of [120, 700]) setTimeout(() => { if (frame.isConnected) frame.contentWindow.postMessage({ rnl: 1, type: "fit" }, origin); }, ms); };
  // a frame out of sight when its drawing arrives (below the fold, a page in the background) may
  // be laid out late by the browser, and the fit then misses: it is fitted again when first seen
  let loaded = false;
  const seen = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
    if (!loaded || !frame.isConnected || !entries.some(x => x.isIntersecting)) return;
    seen.disconnect();
    fit();
  }) : null;
  if (seen) seen.observe(frame);
  const fail = text => { wrap.dataset.state = "error"; status.hidden = true; msg.hidden = false; msg.textContent = text; };
  const timer = setTimeout(() => { if (!e.ready) fail(t("The RNL viewer did not answer. Open the netlist in the viewer instead.")); }, 20000);
  const onMsg = ev => {
    if (!frame.isConnected) { window.removeEventListener("message", onMsg); return; }
    if (ev.source !== frame.contentWindow || ev.origin !== origin || !ev.data || ev.data.rnl !== 1) return;
    const m = ev.data;
    if (m.type === "ready") {
      e.ready = true;
      clearTimeout(timer);
      frame.contentWindow.postMessage({ rnl: 1, type: "open", requestId: req, name: drawing.name, text: drawing.text }, origin);
    } else if (m.type === "loaded" && (!m.requestId || m.requestId === req)) {
      const lv = drawing.level && (m.levels || []).find(x => x.toLowerCase() === drawing.level.toLowerCase());
      if (lv && lv !== m.level) frame.contentWindow.postMessage({ rnl: 1, type: "level", name: lv }, origin);
      else fit();
      loaded = true;
      wrap.dataset.state = "loaded";
      status.hidden = true;
      const counts = [t("{n} levels", { n: (m.levels || []).length }), t("{n} errors", { n: m.errors || 0 }), t("{n} warnings", { n: m.warnings || 0 })];
      msg.hidden = false;
      msg.textContent = t("Drawn by the RNL viewer: {c}.", { c: counts.join(t(", ")) });
    } else if (m.type === "level") {
      // the viewer keeps its own zoom; a drawing shown on a new level is fitted to the frame
      fit();
    } else if (m.type === "error" && (!m.requestId || m.requestId === req) && m.reason !== "superseded") {
      fail(t("The RNL viewer could not draw it: {m}", { m: m.message || m.reason || "" }));
    }
  };
  window.addEventListener("message", onMsg);
}

// The complete viewer in a tab of its own: opened in the click itself, then sent the text.
let viewerTab = null;
function openInViewer(drawing) {
  const token = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/[^A-Za-z0-9-]/g, "");
  const vu = viewerUrl({ api: "1", origin: location.origin, token });
  const send = (win, tok) => win.postMessage({ rnl: 1, type: "open", token: tok, requestId: "gaze-" + Date.now(), name: drawing.name, text: drawing.text }, vu.origin);
  if (viewerTab && viewerTab.win && !viewerTab.win.closed && viewerTab.ready) { viewerTab.win.focus(); send(viewerTab.win, viewerTab.token); return; }
  const win = window.open(vu.href, "rnl-viewer");
  if (!win) { toast(t("The browser blocked the new tab; allow pop-ups for this site.")); return; }
  viewerTab = { win, token, ready: false };
  const onMsg = ev => {
    if (ev.source !== win || ev.origin !== vu.origin || !ev.data || ev.data.rnl !== 1 || ev.data.token !== token) return;
    if (ev.data.type === "ready") { viewerTab.ready = true; send(win, token); }
    else if (ev.data.type === "error" && ev.data.reason !== "superseded") toast(t("The RNL viewer could not open it: {m}", { m: ev.data.message || ev.data.reason || "" }));
  };
  window.addEventListener("message", onMsg);
}

async function mountDrawing(panel) {
  const ds = REG.get(panel.dataset.draw);
  const fs = ds && REG.get(ds.filesId);
  const box = panel.querySelector("[data-sch]");
  const openBtn = panel.querySelector("[data-rnl-open]");
  if (!ds || !fs || !box) return;
  if (!fs.sources.length) { box.innerHTML = `<p class="faint">${esc(t("The files of this object cannot be fetched from here."))}</p>`; return; }
  let drawing = null;
  openBtn.addEventListener("click", () => { if (drawing) openInViewer(drawing); });
  const draw = async () => {
    openBtn.disabled = true;
    box.innerHTML = `<p class="faint">${esc(t("Reading the netlist…"))}</p>`;
    try {
      drawing = await prepareDrawing(ds, fs);
    } catch (e) {
      box.innerHTML = `<p class="faint">${esc(t("The netlist could not be read: {e}", { e: e.message }))}</p>`;
      return;
    }
    openBtn.disabled = false;
    if (!drawing.records) {
      box.innerHTML = `<p class="faint">${esc(t("This netlist has no RNL records, so it holds no drawing. Open it in the RNL viewer to have one solved there."))}</p>`;
      return;
    }
    if (ds.drawing.clash.length && !ds.anyway) {
      box.innerHTML = `<div class="notice-warn"><b>${esc(t("Two interfaces share a name"))}</b><p>${esc(t("The blocks of {names} come from different interfaces with the same name, so their symbol packages have the same name too; RNL uses only one of them. This makes no object invalid.", { names: ds.drawing.clash.join(", ") }))}</p><button type="button" class="btn sm" data-anyway>${esc(t("Draw anyway"))}</button></div>`;
      box.querySelector("[data-anyway]").addEventListener("click", () => { ds.anyway = true; draw(); });
      return;
    }
    embed(box, drawing);
  };
  fs.listeners.push(draw);
  draw();
}

// A long text (a README) is shown up to a height, with a button for the rest; a short one whole.
const CLAMP = 320;
function clampLong(el) {
  if (el.scrollHeight <= CLAMP * 1.4) return;
  el.classList.add("clamped");
  const b = document.createElement("button");
  b.type = "button";
  b.className = "btn sm clamp-btn";
  const paint = () => { b.textContent = el.classList.contains("clamped") ? t("Show all") : t("Show less"); };
  b.addEventListener("click", () => { el.classList.toggle("clamped"); paint(); });
  paint();
  el.after(b);
}

function hydrate(scope) {
  for (const el of scope.querySelectorAll("[data-files]")) mountFiles(el);
  for (const el of scope.querySelectorAll("[data-draw]")) mountDrawing(el);
  for (const el of scope.querySelectorAll("[data-sel]")) { const d = REG.get(el.dataset.sel); if (d) mountSelection(el, d); }
  for (const el of scope.querySelectorAll(".raw-slot[data-raw]")) {
    const url = el.dataset.raw;
    getText(url).then(text => {
      if (el.dataset.kind === "md") el.innerHTML = renderMd(text);
      else if (el.dataset.kind === "lock") el.innerHTML = lockHtml(text);
      else el.innerHTML = `<pre>${esc(text)}</pre>`;
      if (el.dataset.clamp) clampLong(el);
    }).catch(err => {
      el.innerHTML = `<p class="faint">${esc(t("Could not fetch {file} from its library ({e}).", { file: el.dataset.file || "", e: err.message }))} <a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(t("Open it"))} ↗</a></p>`;
    });
  }
  const form = scope.querySelector("#search-form");
  if (form) {
    form.addEventListener("submit", e => {
      e.preventDefault();
      const u = new URLSearchParams();
      for (const [k, v] of new FormData(form)) if (v) u.set(k, v);
      location.hash = "#/search?" + u.toString();
    });
  }
}

/* ---------------------------------------------------------------- router */
let seq = 0;
async function resolveShort(id) {
  const all = await getJSON("data/search.json");
  const hits = all.filter(e => e.n.startsWith(id));
  return hits.length === 1 ? hits[0].n : null;
}

async function route() {
  const my = ++seq;
  const raw = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  const [path, query] = raw.split("?");
  const params = new URLSearchParams(query || "");
  paintChrome();
  REG.clear();
  let res;
  try {
    if (!path) res = await pageHome();
    else if (path === "ifcs") res = { redirect: "#/search?p=ifc" + (params.get("view") === "symbols" ? "&view=symbols" : "") };
    else if (path.startsWith("ifc/")) res = await pageIfcName(path.slice(4));
    else if (path.startsWith("lib/")) res = await pageLibrary(path.slice(4));
    else if (path === "search") res = await pageSearch(params);
    else if (path === "updates") res = await pageUpdates();
    else if (path === "about") res = pageAbout();
    else if (path === "agent") res = pageAgent();
    else {
      let [name, tab] = path.split("/");
      if (!NAME_RE.test(name) && /^[a-z][a-z0-9]*_[0-9a-f]{4,39}$/.test(name)) {
        const full = await resolveShort(name);
        if (full) { location.replace("#/" + full + (tab ? "/" + tab : "")); return; }
      }
      if (prefixOf(name) === "ifc" && NAME_RE.test(name)) {
        try { res = await pageIfc(name, tab); } catch (e) { if (e.status === 404) res = await pageObject(name); else throw e; }
      } else res = await pageObject(name);
    }
  } catch (e) {
    res = { title: t("Error"), html: `<div class="alert"><h3>${esc(t("This page could not be shown"))}</h3><p>${esc(e.message || String(e))}</p></div>` };
  }
  if (my !== seq) return;
  if (res.redirect) { location.replace(res.redirect); return; }
  // another tab of the same page replaces only its part: the head of the page stays as it is
  const part = res.part && app.querySelector("[data-part]");
  if (part && part.dataset.part === res.part.key) {
    part.innerHTML = res.part.html;
    hydrate(part);
  } else {
    app.innerHTML = res.html;
    hydrate(app);
  }
  const brand = (S.site && S.site.title) || "Gazettoa";
  document.title = res.title && res.title !== brand ? `${res.title} · ${brand}` : brand;
  // a new page starts at the top; another tab of the same object keeps the place
  const page = path.split("/")[0];
  if (page !== lastPage) window.scrollTo(0, 0);
  lastPage = page;
}
let lastPage = null;

/* ---------------------------------------------------------------- start */
(async function start() {
  try {
    const [site, langs] = await Promise.all([getJSON("data/site.json", { fresh: true }), getJSON("i18n/languages.json").catch(() => null)]);
    S.site = site;
    S.langs = (langs && langs.languages) || [{ code: "en", name: "English", short: "EN" }];
  } catch (e) {
    app.innerHTML = `<div class="alert"><h3>No data</h3><p>data/site.json could not be read: ${esc(e.message)}. Build the site with <code>python -m gaze build</code>.</p></div>`;
    return;
  }
  window.addEventListener("hashchange", route);
  await setLang(pickLang(), { remember: false });
})();
