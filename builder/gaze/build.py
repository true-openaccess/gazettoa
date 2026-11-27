"""Building the site: the page shell, and the data the pages read, from the index of `toa`.

What is written under `<out>/`:

    index.html, assets/, i18n/     the page shell (copied from web/ and i18n/)
    data/site.json                 the instance: libraries, interfaces, frozen libraries, recent
                                   additions, changes
    data/ifc/<hh>/<name>.json      one shard per interface: it, its circuits, testbenches, documents,
                                   their series, reproduction groups and lineage
    data/obj/<hh>/<name>.json      one file per object name the index knows, and per name that left
    data/lib/<key>.json            one per library
    data/search.json               every name, for the search
    data/scan.json                 when the libraries were last scanned and the content last changed;
                                   both are this build's time here, and gaze-pages.yml rewrites the
                                   file on each run (scripts/scan.py), even one that builds nothing
    data/changes.json              objects that left a library, with the date the build saw it
    data/seen.json                 when this site first saw each object; kept and added to (authorship.py)
    data/signatures.json           what GitHub says of the signed commits of libraries on github.com
    sym/<hh>/<name>.svg            the symbol of each interface (symbols.py)
    feeds/, llms.txt, registry/    Atom feeds, the text for agents, the instance as a source list (feeds.py)
    raw/<name>/…                   copies of objects' files, only for libraries read by copy

Only `toa` reads libraries. The build reads the index; it calls `toa fetch` only to copy the files
of objects whose library the page cannot reach (a local library, a host with no known address
form, or `raw: copy` in gaze.yaml), and copies what an earlier build already copied instead of
fetching it again. It reads two kinds of files itself, checked against the index: the symbols of
interfaces, and the lists of members of frozen libraries.

The records kept from build to build (changes.json, seen.json, signatures.json) are read from the
previous site: --prev, or the output directory itself. A workflow whose cache was cleared takes
them back from the published site first (gaze-pages.yml), or the record of when each object was
first seen would start again.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from . import authorship as authmod
from . import config as cfgmod
from . import index as idxmod
from . import feeds as feedmod
from . import repro
from . import selection as selmod
from . import symbols as symmod
from .fields import IFC, INDEX, LIB, TYPES
from .views import Model, base_of, date_key, prefix_of, process_of

SITE_FORMAT = "gaze-site/1"
RECENT = 30
CHANGES_KEPT = 500

HERE = Path(__file__).resolve().parent
GAZE_ROOT = HERE.parent.parent           # gaze/ : builder/gaze/build.py -> gaze/
WEB_DIR = GAZE_ROOT / "web"
I18N_DIR = GAZE_ROOT / "i18n"


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
    path.write_bytes((text + "\n").encode("utf-8"))


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        return default


def _log(msg: str) -> None:
    print(f"gaze: {msg}", file=sys.stderr)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------ raw copies

def _needs_copy(model: Model, o: dict, copy_all: bool) -> bool:
    if copy_all:
        return True
    return all(model.library_mode(loc["library"]) == "copy" for loc in model.sorted_locations(o))


def copy_raw(model_probe: Model, out: Path, prev: Path | None, instance: Path, toa: str | None,
             copy_all: bool, offline: bool) -> set[str]:
    idx = model_probe.index
    want = sorted(n for n, o in idx.objects.items() if o.get("present") and _needs_copy(model_probe, o, copy_all))
    if not want:
        return set()
    raw = out / "raw"
    copied, fetch = set(), []
    for n in want:
        old = prev / "raw" / n if prev else None
        if old and old.is_dir():
            # an object's files never change: what an earlier build copied is copied again, not fetched
            shutil.copytree(old, raw / n)
            copied.add(n)
        else:
            fetch.append(n)
    if fetch:
        ws = instance / cfgmod.WORKSPACE_FILE
        if not toa:
            _log(f"{len(fetch)} objects to copy, but no `toa` was given (--toa); their files are not in the site")
        elif not ws.is_file():
            _log(f"no {ws}; cannot copy {len(fetch)} objects")
        else:
            raw.mkdir(parents=True, exist_ok=True)
            for i in range(0, len(fetch), 50):
                part = fetch[i:i + 50]
                cmd = [toa, "fetch", *part, "--into", str(raw), "--workspace", str(ws)]
                if offline:
                    cmd.append("--offline")
                r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
                if r.returncode not in (0, 4):
                    _log(f"toa fetch exit {r.returncode}: {r.stderr.strip()[:400]}")
            for n in fetch:
                if (raw / n).is_dir():
                    copied.add(n)
                else:
                    _log(f"not copied: {n}")
    if raw.is_dir() and not any(raw.iterdir()):
        raw.rmdir()
    return copied


def object_file(model: Model, out: Path, name: str, path: str, toa: str | None, instance: Path,
                offline: bool) -> bytes | None:
    """One file of an object, checked against the index: from the site's copy, a local checkout,
    or `toa cat` (which finds and verifies the object as `toa fetch` does)."""
    o = model.index.get(name) or {}
    want = next((f for f in o.get("files") or [] if f.get("path") == path), None)
    if not want:
        return None
    ok = lambda b: b is not None and hashlib.sha256(b).hexdigest() == want.get("sha256")
    tries = [out / "raw" / name / path]
    for loc in model.sorted_locations(o):
        d = model.local_dir(loc["library"])
        if d:
            tries.append(d / loc["path"] / path)
    for f in tries:
        if f.is_file():
            b = f.read_bytes()
            if ok(b):
                return b
    ws = instance / cfgmod.WORKSPACE_FILE
    if toa and ws.is_file():
        cmd = [toa, "cat", name, path, "--workspace", str(ws)] + (["--offline"] if offline else [])
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode == 0 and ok(r.stdout):
            return r.stdout
    return None


# ------------------------------------------------------------------ symbols

def write_symbols(model: Model, out: Path, prev: Path | None, prev_site: dict, rnl: str | None,
                  toa: str | None, instance: Path, offline: bool) -> dict[str, dict]:
    """sym/<hh>/<name>.svg for every interface present; name -> {svg, kind, note}."""
    prev_kind = {c["name"]: (c.get("symbol") or {}).get("kind") for c in prev_site.get("ifcs") or []}
    made: dict[str, dict] = {}
    drawn = reused = 0
    for n, o in sorted(model.index.objects.items()):
        if prefix_of(n) != "ifc" or not o.get("present"):
            continue
        rel = f"sym/{idxmod.shard_of(n)}/{n}.svg"
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        has = any(f.get("path") == IFC.SYMBOL_FILE for f in o.get("files") or [])
        pins = symmod.pin_list(o.get("manifest") or {})
        name = model.display(n)
        old = prev / rel if prev else None
        if has and prev_kind.get(n) == "rnl" and old and old.is_file():
            shutil.copy2(old, dst)
            made[n] = {"svg": rel, "kind": "rnl"}
            reused += 1
            continue
        note = ""
        if has and rnl:
            text = object_file(model, out, n, IFC.SYMBOL_FILE, toa, instance, offline)
            if text is None:
                note = "symbol.rnl could not be read"
            else:
                svg, note = symmod.render_rnl(rnl, text, name, pins)
                if svg:
                    dst.write_bytes(svg.encode("utf-8"))
                    made[n] = {"svg": rel, "kind": "rnl"}
                    drawn += 1
                    continue
            _log(f"symbol of {n}: {note}; drawn as a box")
        elif has:
            note = "rnl is not at hand"
        dst.write_bytes(symmod.box_svg(name, pins).encode("utf-8"))
        made[n] = {"svg": rel, "kind": "box", **({"note": note} if note else {})}
    if drawn or reused:
        _log(f"symbols: {drawn} drawn with rnl, {reused} reused")
    return made


# ------------------------------------------------------------------ changes between builds

def _prev_places(prev: Path | None) -> tuple[dict[str, dict], list[dict]]:
    if not prev:
        return {}, []
    search = _read_json(prev / "data" / "search.json", []) or []
    places = {e["n"]: e for e in search if e.get("l")}
    changes = _read_json(prev / "data" / "changes.json", []) or []
    return places, changes


def compute_changes(model: Model, prev_places: dict[str, dict], prev_changes: list[dict], built: str) -> list[dict]:
    new = []
    for name, e in prev_places.items():
        o = model.index.get(name) or {}
        now_libs = set(model.libraries_of(o)) if o.get("present") else set()
        for lib in e.get("l") or []:
            if lib in now_libs:
                continue
            if model.index.library(lib) and not model.index.library(lib).get("readable", True):
                continue  # not read this time: nothing is known to have left
            rem = next((r for r in o.get("removals") or [] if r.get("library") == lib), None)
            new.append({
                "kind": "left",
                "name": name,
                "display": e.get("d") or name[:12],
                "prefix": prefix_of(name),
                "library": lib,
                "seen": built,
                "record": bool(rem),
                "reason": ((rem or {}).get("record") or {}).get("reason"),
                "elsewhere": sorted(now_libs),
            })
    return (new + prev_changes)[:CHANGES_KEPT]


# ------------------------------------------------------------------ the page shell

# Cloudflare Web Analytics, when gaze.yaml names a token: the tag Cloudflare gives, as it gives it, put
# before </body>; its script comes from CF_SCRIPT and reports to CF_REPORT, which the policy of the
# page lets through (Cloudflare's documentation of Web Analytics and Content Security Policy).
CF_TAG = ("<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' "
          "data-cf-beacon='{\"token\": \"TOKEN\"}'></script><!-- End Cloudflare Web Analytics -->")
CF_SCRIPT = "https://static.cloudflareinsights.com"
CF_REPORT = "https://cloudflareinsights.com"


def _csp(model: Model) -> str:
    cf = bool(model.cfg.cloudflare_web_analytics)
    origins = set()
    for lib in model.index.libraries:
        tpl = model.templates.get(lib["key"])
        if tpl:
            u = urlsplit(tpl[0].replace("{commit}", "x").replace("{path}", "x"))
            if u.scheme == "https" and u.hostname:
                origins.add(f"https://{u.hostname}")
    connect = " ".join(["'self'", *sorted(origins), *([CF_REPORT] if cf else [])])
    script = " ".join(["'self'", *([CF_SCRIPT] if cf else [])])
    viewer = urlsplit(model.cfg.viewer_url)
    frame = f"https://{viewer.hostname}" if viewer.scheme == "https" and viewer.hostname else "'none'"
    return (f"default-src 'self'; script-src {script}; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            f"connect-src {connect}; frame-src {frame}; object-src 'none'; base-uri 'self'; form-action 'none'")


def write_shell(out: Path, model: Model, web_dir: Path, i18n_dir: Path) -> None:
    for item in web_dir.iterdir():
        dst = out / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        elif item.name != "index.html":
            shutil.copy2(item, dst)
    html = (web_dir / "index.html").read_bytes().decode("utf-8")
    esc = lambda s: s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
    head = (f'<meta http-equiv="Content-Security-Policy" content="{esc(_csp(model))}">\n'
            f"<title>{esc(model.cfg.title)}</title>\n"
            # Gazettoa has no released version yet (app.js, PREVIEW)
            f'<meta name="generator" content="Gazettoa (preview)">')
    # the subtitle of Gazettoa (on the home page), then the instance's own description
    about = " ".join(x for x in ("The Gazetteer of TOA libraries.", model.cfg.description) if x)
    head += f'\n<meta name="description" content="{esc(about)}">'
    if model.cfg.site_url:
        head += f'\n<link rel="alternate" type="application/atom+xml" title="{esc(model.cfg.title)}" href="feeds/all.xml">'
    head += '\n<link rel="help" type="text/plain" href="llms.txt">'
    html = html.replace("<!--gaze:head-->", head)
    # every page of the site is this one file, its routes after the #: one tag counts them all
    if model.cfg.cloudflare_web_analytics:
        end = html.rindex("</body>")
        html = html[:end] + CF_TAG.replace("TOKEN", model.cfg.cloudflare_web_analytics) + "\n" + html[end:]
    (out / "index.html").write_bytes(html.encode("utf-8"))
    if i18n_dir.is_dir():
        shutil.copytree(i18n_dir, out / "i18n")


# ------------------------------------------------------------------ the build

def build(instance: Path, index_dir: Path, out: Path, *, prev: Path | None = None, toa: str | None = None,
          copy_all: bool = False, offline: bool = False, site_url: str | None = None,
          local_files: list[Path] | None = None, rnl: str | None = None,
          web_dir: Path = WEB_DIR, i18n_dir: Path = I18N_DIR, built: str | None = None) -> dict:
    cfg = cfgmod.load(instance, site_url)
    idx = idxmod.read(index_dir)
    built = built or _now()
    if prev is None and (out / "data" / "site.json").is_file():
        prev = out
    prev_places, prev_changes = _prev_places(prev)
    prev_site = (_read_json(prev / "data" / "site.json", {}) or {}) if prev else {}

    tmp = out.parent / (out.name + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    probe = Model(idx, cfg, local_files=local_files)
    copied = copy_raw(probe, tmp, prev, instance, toa, copy_all, offline)
    model = Model(idx, cfg, copied, local_files=local_files)
    write_shell(tmp, model, web_dir, i18n_dir)

    # evidence of authorship and time (TOA decision B35)
    seen = authmod.update_seen(model, _read_json(prev / "data" / "seen.json") if prev else None, built)
    model.seen = seen["objects"]
    # who signed the commits that put objects into libraries on github.com, as GitHub verified it
    prev_sig = _read_json(prev / "data" / "signatures.json") if prev else None
    token = os.environ.get("GITHUB_TOKEN", "")
    if cfg.github_signature_check and not offline and token:
        sigs = authmod.check_signatures(authmod.signed_commits(idx), prev_sig, built, _log, token=token)
    else:
        sigs = authmod.check_signatures({}, prev_sig, built, _log)
    model.signatures = sigs["commits"]
    syms = write_symbols(model, tmp, prev, prev_site, rnl, toa, instance, offline)

    groups = repro.build_groups(idx)
    by_record = {r: g for g in groups for r in g["records"]}
    by_dut: dict[str, list] = {}
    for g in groups:
        by_dut.setdefault(g["dut"], []).append(g)

    changes = compute_changes(model, prev_places, prev_changes, built)
    changes_by_name: dict[str, list] = {}
    for c in changes:
        changes_by_name.setdefault(c["name"], []).append(c)

    data = tmp / "data"
    # one file per name
    names = set(idx.objects) | set(changes_by_name)
    plans: dict[str, list[str]] = {}  # interface -> the test plans that measure it
    for n in sorted(names):
        v = model.view(n, by_record, by_dut)
        v["changes"] = changes_by_name.get(n, [])
        if n in syms:
            v["symbol"] = syms[n]
        if v.get("has_members"):
            # a frozen library: its list of members, read from the object and checked by the index
            v["members"] = model.lib_members(object_file(model, tmp, n, LIB.MEMBERS_FILE, toa, instance, offline))
            v["names"].update(model.names(m["object"] for g in v["members"]["groups"] for m in g["members"]))
            # a frozen library that holds testbenches is a test plan (type lib)
            v["plan"] = model.test_plan(v["members"])
            if v["plan"] and v["present"]:
                v["names"].update(model.names(v["plan"]["ifcs"]))
                for ifc in v["plan"]["ifcs"]:
                    plans.setdefault(ifc, []).append(n)
        _dump(data / "obj" / idxmod.shard_of(n) / f"{n}.json", v)

    # one shard per interface
    ifc_cards = []
    for n, o in sorted(idx.objects.items()):
        if prefix_of(n) != "ifc" or not o.get("present"):
            continue
        members = model.members(n)
        ifcv = model.view(n, by_record, by_dut)
        ifcv["symbol"] = syms.get(n)
        ifc_groups = [g for ckt in members["ckt"] for g in by_dut.get(ckt, [])]
        linked = set(ifcv["names"])
        for k in members:
            linked.update(members[k])
        nodes, edges = [], []
        for ckt in members["ckt"]:
            io = idx.get(ckt) or {}
            parent = (base_of(io) or [None])[0]
            hist = io.get("history") or {}
            nodes.append(ckt)
            if parent:
                state = "verified" if parent in (hist.get("verified") or []) else ("gap" if hist.get("state") == "gap" else "declared")
                edges.append([parent, ckt, state])
                linked.add(parent)
        for g in ifc_groups:
            linked.update(g["records"])
            linked.update(g["tbs"])
        gens = model.ifc_generations(n)
        linked.update(x["ifc"] for x in gens)
        linked.update(plans.get(n, []))
        shard = {
            "ifc": ifcv,
            "ckts": [model.card(x) for x in members["ckt"]],
            "tbs": [model.card(x) for x in members["tb"]],
            "docs": [model.card(x) for x in members["doc"]],
            # each series shows the generations a library marks latest; the others are folded (TOA 3.4, 5.2)
            "series": {"ckt": model.series_groups(members["ckt"]), "tb": model.series_groups(members["tb"])},
            "groups": ifc_groups,
            "selection": selmod.build(model, members["ckt"], members["tb"], ifc_groups),
            "lineage": {"nodes": nodes, "edges": edges},
            # the other generations of this interface, each with its own circuits and testbenches
            "generations": gens,
            "plans": [model.card(x) for x in plans.get(n, [])],
            "names": model.names(sorted(linked)),
        }
        _dump(data / "ifc" / idxmod.shard_of(n) / f"{n}.json", shard)
        card = model.card(n)
        card.update(ckts=len(members["ckt"]), tbs=len(members["tb"]), docs=len(members["doc"]),
                    description=ifcv.get("description"), symbol=syms.get(n),
                    pin_names=[p.get("name") for p in ifcv.get("pins") or []])
        ifc_cards.append(card)
    ifc_cards.sort(key=lambda c: (c["display"].lower(), c["name"]))
    # frozen libraries, by name; within a name the marked ones first, then by generation
    lib_cards = [model.card(n) for n, o in idx.objects.items() if prefix_of(n) == "lib" and o.get("present")]
    lib_cards.sort(key=lambda c: ((c.get("design") or c["display"]).lower(), not c["latest"], -(c.get("generation") or 0), c["name"]))

    # libraries
    addresses = {lib.get("address") for lib in idx.libraries if lib.get("address")}
    lib_summaries = []
    for lib in idx.libraries:
        key = lib["key"]
        objs = [model.card(n) for n in lib.get("objects") or []]
        removed = []
        for n in lib.get("removed") or []:
            o = idx.get(n) or {}
            rem = next((r for r in o.get("removals") or [] if r.get("library") == key), {})
            removed.append({"name": n, "display": model.display(n), "path": rem.get("path"), "date": rem.get("date"),
                            "valid": rem.get("valid"), "reason": (rem.get("record") or {}).get("reason")})
        includes = []
        for inc in lib.get("includes") or []:
            srcs = [s.get("git") for s in inc.get("sources") or [] if s.get("git")]
            includes.append({"group": inc.get("group"), "branch": inc.get("branch"), "addresses": srcs,
                             "in_instance": any(a in addresses for a in srcs)})
        problems = list(lib.get("problems") or []) + [p for p in idx.problems if p.get("library") == key]
        tpl = model.templates.get(key)
        summary = {
            "key": key,
            "groups": lib.get("groups") or [key],
            "address": lib.get("address"),
            "branch": lib.get("branch"),
            "commit": lib.get("commit"),
            "date": lib.get("date"),
            "readable": lib.get("readable", True),
            "previous": lib.get("previous"),
            "title": (lib.get("library_yaml") or {}).get("title"),
            "description": (lib.get("library_yaml") or {}).get("description"),
            "objects": len(lib.get("objects") or []),
            "removed": len(lib.get("removed") or []),
            # objects with same files as an earlier object of another author, lineage not declared
            "same_files": sum(1 for n in lib.get("objects") or [] if (model.same.get(n) or {}).get("earlier")),
            "problems": len(problems),
            "raw": model.library_mode(key),
            "web": model.web_url(key, "") if tpl else None,
        }
        lib_summaries.append(summary)
        left = [c for c in changes if c["library"] == key]
        _dump(data / "lib" / f"{key}.json", {**summary, "library_yaml": lib.get("library_yaml"),
                                              "object_cards": objs, "removed_objects": removed,
                                              "includes": includes, "problem_list": problems, "left": left})

    # search, recent additions
    search = []
    for n in sorted(idx.objects):
        o = idx.objects[n]
        if not o.get("present") and not o.get("removals"):
            continue
        ifc = model.ifc_of(n)
        m = o.get("manifest") or {}
        search.append({"n": n, "d": model.display(n), "p": prefix_of(n), "ifc": model.ifc_name(ifc) if ifc else "",
                       "l": model.libraries_of(o) if o.get("present") else [], "pr": process_of(m) or "",
                       "v": 1 if o.get("valid") else 0, "x": 1 if o.get("present") else 0})
    _dump(data / "search.json", search)
    recent = []
    for n, o in idx.objects.items():
        for loc in o.get("locations") or []:
            recent.append({"name": n, "display": model.display(n), "prefix": prefix_of(n),
                           "library": loc["library"], "date": loc.get("first_date")})
    recent.sort(key=lambda r: (-date_key(r["date"]), r["name"], r["library"]))
    _dump(data / "changes.json", changes)
    _dump(data / "seen.json", seen)
    if sigs["commits"] or prev_sig:
        _dump(data / "signatures.json", sigs)

    feeds_ok = feedmod.write_feeds(model, tmp, changes, built)
    feedmod.write_registry(model, tmp, instance)
    feedmod.write_llms(model, tmp, ifc_cards, lib_cards, built, feeds_ok)

    present = [o for o in idx.objects.values() if o.get("present")]
    counts = {
        "libraries": len(idx.libraries),
        "objects": len(present),
        "valid": sum(1 for o in present if o.get("valid")),
        **{k: sum(1 for o in present if prefix_of(o["name"]) == k) for k in TYPES},
        "problems": len(idx.problems) + sum(len(lib.get("problems") or []) for lib in idx.libraries),
        "groups": len(groups),
        "multi_party": sum(1 for g in groups if g["multi_party"]),
        "same_files": sum(1 for x in model.same.values() if x.get("earlier")),
    }
    site = {
        "format": SITE_FORMAT,
        "title": cfg.title,
        "description": cfg.description,
        "site_url": cfg.site_url,
        "viewer_url": cfg.viewer_url,
        "toa_site": cfg.toa_site,
        "repository": cfg.repository,
        "built": built,
        "feeds": feeds_ok,
        # kind -> the type's name in TOA, the prefix of its object names (fields.TYPES)
        "types": dict(TYPES),
        "index": {"tool": idx.meta.get("tool"), "standard": idx.meta.get("standard"), "built": idx.meta.get("built"),
                  "alarms": idx.meta.get("alarms") or []},
        "counts": counts,
        "libraries": lib_summaries,
        "ifcs": ifc_cards,
        "libs": lib_cards,
        "recent": recent[:RECENT],
        "changes": changes[:20],
        # since when this site records when it first saw each object
        "seen_since": seen["since"],
        # whether it asks GitHub about signed commits: set, and this build had a token and was online
        "sig_check": bool(cfg.github_signature_check and not offline and os.environ.get("GITHUB_TOKEN")),
        # the numbers the index used for the same files of 8.3 (min_size, common_groups, ...), for the help
        "same_rule": idx.meta.get(INDEX.SAME_FILES) if isinstance(idx.meta.get(INDEX.SAME_FILES), dict) else None,
    }
    _dump(data / "site.json", site)
    # the format of scripts/scan.py, which the workflow writes the file with
    _dump(data / "scan.json", {"format": "gaze-scan/1", "scanned": built, "changed": built, "stamp": ""})

    if out.exists():
        shutil.rmtree(out)
    tmp.rename(out)
    return {"objects": len(names), "ifcs": len(ifc_cards), "libraries": len(lib_summaries),
            "groups": len(groups), "copied": len(copied), "changes": len(changes),
            "symbols": sum(1 for x in syms.values() if x["kind"] == "rnl")}
