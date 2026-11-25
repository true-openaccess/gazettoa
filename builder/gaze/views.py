"""From the index to what the pages show: names for people, cards for lists, views for pages.

Every manifest field is read through `fields`; the views use Gazettoa's own keys, so the pages
never depend on a manifest field's name.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from . import config as cfgmod
from . import repro
from . import targets as tgmod
from .fields import (ANALYZE, AUTHOR, BASE, CKT, COND, DESCRIPTION, DOC, ENV, EVD, HISTORY, IFC, INDEX, LIB, LICENSE, LOCK,
                     MCSTAT, METRIC, PIN, PROBE, ROLE, SOURCE, SPEC, STAT, TAGS, TB, TITLE, USE, kind_of, metric_full_name)

SHORT = 12  # "the first 12 characters of the object name" (type specifications, readable names)
MEMBERS_SHOWN = 2000  # lines of a frozen library's list of members put into its page


def one_line(s) -> str | None:
    """The first line of a text, for a list."""
    if not isinstance(s, str):
        return None
    line = next((x.strip() for x in s.splitlines() if x.strip()), "")
    return line or None


def title_of(o: dict) -> str | None:
    """The title to show: the index's `title` (the manifest's `title`, or for a document without
    one the first heading of its README.md, index-format.md), else the manifest's own."""
    t = o.get("title")
    if not isinstance(t, str) or not t:
        t = (o.get("manifest") or {}).get(TITLE)
    return t if isinstance(t, str) and t else None


def process_of(m: dict) -> str | None:
    """The process a circuit names (`specifications.process`)."""
    sp = m.get(CKT.SPECIFICATIONS)
    p = sp.get(SPEC.PROCESS) if isinstance(sp, dict) else None
    return p if isinstance(p, str) else None


def history_of(o: dict) -> dict:
    h = o.get(INDEX.HISTORY)
    return h if isinstance(h, dict) else {}


def base_of(o: dict) -> list[str]:
    """`base` as the object writes it: the index's copy, else the manifest's."""
    b = o.get(INDEX.BASE)
    if not isinstance(b, list):
        b = (o.get("manifest") or {}).get(BASE)
    return [x for x in b if isinstance(x, str)] if isinstance(b, list) else []


def generation(o: dict) -> int | None:
    """The generation of an object (TOA 0.1, 3.4): the one its `history.json` gives, as the index
    reads it; 1 for an object without `base`. None when the object was not read, or when its
    history gives none."""
    if not o.get("present"):
        return None
    h = history_of(o)
    g = h.get(HISTORY.GENERATION)
    if isinstance(g, int) and not isinstance(g, bool) and g >= 1:
        return g
    return None if h.get(HISTORY.LISTED) or base_of(o) else 1


def metric_view(tb_name: str | None, md: dict) -> dict:
    """A metric of a testbench, with Gazettoa's keys."""
    return {"id": md.get(METRIC.ID), "full": metric_full_name(tb_name or "?", md.get(METRIC.ID, "?")),
            "unit": md.get(METRIC.UNIT), "better": md.get(METRIC.BETTER),
            "tolerance": md.get(METRIC.TOLERANCE), "description": md.get(METRIC.DESCRIPTION)}


_LOCK_TREE = re.compile(rf"^{re.escape(EVD.LOCK_FILE)}:{LOCK.TREE}/(\d+)/({LOCK.OBJECT}|{LOCK.IFC})$")


def parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def date_key(s: str | None) -> float:
    d = parse_date(s)
    return d.timestamp() if d else 0.0


# the kinds of timestamp proofs the page knows how to check, by extension; any other is "other"
STAMP_KINDS = {".ots": "opentimestamps", ".tsr": "rfc3161"}


def stamp_kind(file: str) -> str:
    """The kind of a timestamp proof as a hint from its extension, as the index of toa gives it."""
    name = file.rsplit("/", 1)[-1]
    return STAMP_KINDS.get(name[name.rfind("."):].lower(), "other") if "." in name else "other"


def prefix_of(name: str) -> str:
    """The kind of an object (`ifc`, `ckt`, `tb`, `evd`, `doc`, `lib`), from its name through fields.TYPES."""
    return kind_of(name)


# the field that holds the design's `name`, by kind: the types whose generations share a name (3.4)
_NAME_FIELD = {"ifc": IFC.NAME, "ckt": CKT.NAME, "tb": TB.NAME, "lib": LIB.NAME}


def probes_of(m: dict) -> list[dict]:
    """The probes an interface declares (B36): `{name, description}` in the order written."""
    return [{"name": str(x.get(PROBE.NAME)), "description": x.get(PROBE.DESCRIPTION)}
            for x in m.get(IFC.PROBES) or [] if isinstance(x, dict) and x.get(PROBE.NAME) is not None]


def preset_rows(presets) -> list[dict] | None:
    """The presets of a testbench, one row per set of conditions (B36: a preset is one set or a list
    of sets): `{name, index, count, parameters, options, models, statistics}`, `index` counting from 1
    in a list; `statistics` only in a set of a Monte Carlo simulation (B37). A preset that is
    neither is shown as written (`raw`)."""
    if not isinstance(presets, dict):
        return None
    rows = []
    for name, p in presets.items():
        sets = [p] if isinstance(p, dict) else p if isinstance(p, list) else None
        if sets is None or not all(isinstance(x, dict) for x in sets):
            rows.append({"name": str(name), "raw": p})
            continue
        for i, x in enumerate(sets):
            rows.append({"name": str(name), "index": i + 1 if isinstance(p, list) else None, "count": len(sets),
                         **{k: x.get(k) for k in COND.SLOTS}, "statistics": x.get(COND.STATISTICS),
                         "other": {k: y for k, y in x.items() if k not in COND.SLOTS and k != COND.STATISTICS} or None})
    return rows


class Model:
    def __init__(self, index, cfg, copied: set[str] | None = None, local_files: list[Path] | None = None):
        self.index = index
        self.cfg = cfg
        self.copied = copied or set()
        self.local_files = [Path(d) for d in local_files or []]
        self.order = {lib["key"]: i for i, lib in enumerate(index.libraries)}
        self.templates: dict[str, tuple[str, str] | None] = {}
        for lib in index.libraries:
            self.templates[lib["key"]] = cfgmod.library_templates(cfg, lib.get("address"))
        self._display: dict[str, str] = {}
        # evidence of authorship and time (authorship.py), set by the build
        self.seen: dict[str, dict] = {}        # name -> when this site first saw it
        # name -> same files, lineage not declared (8.3), as the index computed them; only the
        # objects concerned. An index older than the key has none.
        self.same: dict[str, dict] = {}
        for n, o in index.objects.items():
            s = o.get(INDEX.SAME_FILES)
            if isinstance(s, dict) and (s.get("earlier") or s.get("later") or s.get("common")):
                self.same[n] = s
        self.signatures: dict[str, dict] = {}  # commit -> what GitHub says of its signature

    # ------------------------------------------------------------ names for people

    def manifest(self, name: str | None) -> dict:
        o = self.index.get(name)
        return (o or {}).get("manifest") or {}

    def label(self, o: dict) -> str | None:
        for loc in self.sorted_locations(o):
            if loc.get("label"):
                return loc["label"]
        for rem in o.get("removals") or []:
            lab = (rem.get("record") or {}).get("label")
            if lab:
                return lab
        return None

    def ifc_name(self, ifc_object: str | None) -> str:
        """The `name` of an interface, or the first 12 characters of its object name."""
        if not ifc_object:
            return "?"
        n = self.manifest(ifc_object).get(IFC.NAME)
        return n if isinstance(n, str) and n else ifc_object[:SHORT]

    def ifc_of(self, name: str | None) -> str | None:
        """The interface an object belongs to: its own name, its `ifc`, for an evidence record its
        `dut`'s, for a document the first interface among its `refs`. A frozen library has none."""
        if not name:
            return None
        p = prefix_of(name)
        if p == "ifc":
            return name
        m = self.manifest(name)
        if p in ("ckt", "tb"):
            ifc = m.get(CKT.IFC if p == "ckt" else TB.IFC)
            return ifc if isinstance(ifc, str) else None
        if p == "evd":
            dut = m.get(EVD.DUT)
            return self.manifest(dut).get(CKT.IFC) if isinstance(dut, str) else None
        if p == "doc":
            return next((r for r in m.get(DOC.REFS) or [] if isinstance(r, str) and prefix_of(r) == "ifc"), None)
        return None

    def design(self, name: str | None) -> str | None:
        """The `name` field of a type whose generations share it (ifc, ckt, tb, lib)."""
        f = _NAME_FIELD.get(prefix_of(name or ""))
        d = self.manifest(name).get(f) if f else None
        return d if isinstance(d, str) and d else None

    def display(self, name: str | None) -> str:
        if not name:
            return ""
        if name in self._display:
            return self._display[name]
        self._display[name] = d = self._make_display(name)
        return d

    def _make_display(self, name: str) -> str:
        o = self.index.get(name)
        p = prefix_of(name)
        short = name[:SHORT]
        if not o:
            return short + "…"
        if not o.get("present"):
            return self.label(o) or short + "…"
        m = o.get("manifest") or {}
        g = generation(o)
        gen = f".g{g}" if g else ""
        if p == "ifc":
            return m.get(IFC.NAME) or self.label(o) or short
        if p in ("ckt", "tb"):
            design = self.design(name)
            if design:
                return f"{self.ifc_name(self.ifc_of(name))}/{design}{gen}"
            return self.label(o) or short
        if p == "lib":
            design = self.design(name)
            return f"{design}{gen}" if design else self.label(o) or short
        if p == "evd":
            lab = self.label(o)
            if lab:
                return lab
            dut_ifc = self.manifest(m.get(EVD.DUT)).get(CKT.IFC)
            ifcn = self.ifc_name(dut_ifc) if dut_ifc else (m.get(EVD.DUT) or "?")[:SHORT]
            return f"{ifcn}/{short}"
        if p == "doc":
            return self.label(o) or title_of(o) or short
        return self.label(o) or short

    def names(self, names) -> dict[str, list]:
        """name -> [display, prefix, present]: what a page needs to show the names it links to."""
        out = {}
        for n in names:
            if not n or n in out:
                continue
            o = self.index.get(n)
            out[n] = [self.display(n), prefix_of(n), 1 if (o and o.get("present")) else 0]
        return out

    # ------------------------------------------------------------ series, latest marks, newer versions

    def series(self, name: str) -> str:
        """The series of an object (TOA 0.1, 3.4), named by its earliest generation: objects of one
        type with the same `name`, linked along the first item of `base`; for a type without `name`
        the whole lineage. Its generation says how many of its nearest ancestors are in it."""
        o = self.index.get(name) or {}
        listed = [x for x in history_of(o).get(HISTORY.LISTED) or [] if isinstance(x, str)]
        if prefix_of(name) not in _NAME_FIELD:
            return listed[-1] if listed else name
        g = generation(o) or 1
        return listed[g - 2] if 1 < g <= len(listed) + 1 else name

    def latest_in(self, o: dict) -> list[str]:
        """The libraries whose library list marks the object `latest` (TOA 0.1, 5.2), in the order
        of the workspace list. A mark is that library's word, not the object's."""
        out = []
        for loc in self.sorted_locations(o):
            if loc.get(INDEX.LATEST) is True and loc["library"] not in out:
                out.append(loc["library"])
        return out

    def newer(self, name: str) -> list[dict]:
        """The newer versions of an object (TOA 0.1, 7.5), as the index gives them: valid objects
        that a library marks `latest`, of the same series, whose verified history holds it. Each
        with the libraries that mark it, those that hold both, and whether its interface differs;
        the newest generation first."""
        out = []
        for e in (self.index.get(name) or {}).get(INDEX.NEWER) or []:
            if not isinstance(e, dict) or not isinstance(e.get("name"), str):
                continue
            strs = lambda k: [x for x in e.get(k) or [] if isinstance(x, str)]
            out.append({"name": e["name"], "libraries": strs(INDEX.MARKED_BY), "together": strs(INDEX.TOGETHER),
                        "ifc_changed": e.get(INDEX.IFC_CHANGED) is True})
        out.sort(key=lambda e: (-(generation(self.index.get(e["name"]) or {}) or 0), e["name"]))
        return out

    def series_groups(self, names: list[str]) -> list[dict]:
        """The objects of one list by series, in the order of the list: in each, the generations
        some library marks `latest`, every library's word shown (TOA 0.1, 5.2); without a mark,
        the newest generation. The other generations are `rest`, for the page to fold."""
        by: dict[str, list[str]] = {}
        for n in names:
            by.setdefault(self.series(n), []).append(n)
        out = []
        for key, members in by.items():
            marked = [n for n in members if self.latest_in(self.index.get(n) or {})]
            if marked:
                heads = marked
            else:
                newest = max(members, key=lambda n: (generation(self.index.get(n) or {}) or 0,
                                                     ((self.index.get(n) or {}).get("first") or {}).get("date") or ""))
                heads = [newest]
            out.append({"series": key, "name": self.design(members[0]), "marked": bool(marked),
                        "heads": heads, "rest": [n for n in members if n not in heads]})
        return out

    # ------------------------------------------------------------ places and files

    def sorted_locations(self, o: dict) -> list[dict]:
        return sorted(o.get("locations") or [], key=lambda l: (self.order.get(l["library"], 1 << 30), l["path"]))

    def libraries_of(self, o: dict) -> list[str]:
        seen = []
        for loc in self.sorted_locations(o):
            if loc["library"] not in seen:
                seen.append(loc["library"])
        return seen

    def local_dir(self, key: str) -> Path | None:
        """A checkout of the library on this machine (`--local-files`), for a preview."""
        for d in self.local_files:
            if (d / key).is_dir():
                return d / key
        return None

    def library_mode(self, key: str) -> str:
        """How the page reaches the files of a library: `url` (its host, at the commit read),
        `local` (a checkout on this machine, through scripts/serve.py) or `copy` (copied into the site)."""
        if self.local_dir(key):
            return "local"
        if self.cfg.library_raw_mode(key) == "copy":
            return "copy"
        lib = self.index.library(key) or {}
        if self.templates.get(key) and lib.get("commit") and lib.get("readable", True):
            return "url"
        return "copy"

    def library_file(self, key: str, path: str) -> str | None:
        """The address of a path of a library, for the page; None when only a copy reaches it."""
        mode = self.library_mode(key)
        if mode == "local":
            return f"local/{quote(key)}/{path}"
        if mode == "url":
            return cfgmod.fill(self.templates[key][0], "", (self.index.library(key) or {})["commit"], path)
        return None

    def raw_sources(self, o: dict) -> list[dict]:
        """Where the page can fetch an object's files, one entry per place: the site's copy first,
        then each library that holds it, in the order of the workspace list."""
        out = []
        if o["name"] in self.copied:
            out.append({"library": None, "raw": f"raw/{o['name']}", "kind": "copy"})
        for loc in self.sorted_locations(o):
            url = self.library_file(loc["library"], loc["path"])
            if url:
                lib = self.index.library(loc["library"]) or {}
                out.append({"library": loc["library"], "raw": url, "kind": self.library_mode(loc["library"]),
                            "commit": lib.get("commit")})
        return out

    def raw_prefix(self, o: dict) -> str | None:
        """The first place of `raw_sources`."""
        srcs = self.raw_sources(o)
        return srcs[0]["raw"] if srcs else None

    def web_url(self, key: str, path: str) -> str | None:
        tpl = self.templates.get(key)
        lib = self.index.library(key) or {}
        if not tpl or not tpl[1] or not lib.get("commit"):
            return None
        return cfgmod.fill(tpl[1], "", lib["commit"], path)

    def location_view(self, o: dict, loc: dict) -> dict:
        key = loc["library"]
        notes = []
        for n in loc.get("notes") or []:
            nv = {k: n.get(k) for k in ("file", "commit", "date", "size", "text")}
            if n.get("text") is None:
                nv["raw"] = self.library_file(key, f"{loc['path']}.notes/{n['file']}")
            notes.append(nv)
        return {
            "library": key,
            "path": loc["path"],
            "first_commit": loc.get("first_commit"),
            "first_date": loc.get("first_date"),
            "label": loc.get("label"),
            "signature": self.signature_of(key, loc.get("first_commit"), loc, INDEX.FIRST_SIGNATURE),
            "latest": loc.get(INDEX.LATEST) is True,
            "source_list": loc.get("source_list"),
            "notes": notes,
            "web": self.web_url(key, loc["path"]),
        }

    def stamps_of(self, o: dict) -> list[dict] | None:
        """The timestamp proofs of an object (TOA 4.3), from the stamps directories beside its copies:
        None when the index does not say (an index older than the key), else one entry per proof,
        the same file name, kind and size in several places being one proof, with each place that
        holds it (library, the commit that first added it and its date, where the page fetches it).
        A proof is of the object name, so it holds for every copy. Nothing here checks it.

        TOA does not say what the directory holds (decision of 11-25): a file may be in a
        subdirectory (`file` holds `/`), and its kind is a hint from its extension, taken from the
        index or, when the index gives none, guessed the same way."""
        locs = self.sorted_locations(o)
        if not any(isinstance(loc.get(INDEX.STAMPS), list) for loc in locs):
            return None
        out: dict[tuple, dict] = {}
        for loc in locs:
            for s in loc.get(INDEX.STAMPS) or []:
                if not isinstance(s, dict) or not isinstance(s.get("file"), str):
                    continue
                parts = s["file"].split("/")
                if any(x in ("", ".", "..") for x in parts):   # a path inside the directory, nothing else
                    continue
                kind = s.get("kind") if isinstance(s.get("kind"), str) and s.get("kind") else stamp_kind(s["file"])
                # each part of the path as it goes into an address: a file name may hold any character
                path = f"{loc['path']}{INDEX.STAMPS_DIR}/" + "/".join(quote(x, safe="") for x in parts)
                e = out.setdefault((s["file"], kind, s.get("size")),
                                   {"file": s["file"], "kind": kind, "size": s.get("size"), "places": []})
                e["places"].append({"library": loc["library"], "commit": s.get("commit"), "date": s.get("date"),
                                    "raw": self.library_file(loc["library"], path), "web": self.web_url(loc["library"], path)})
        return sorted(out.values(), key=lambda e: (min(date_key(p["date"]) for p in e["places"]), e["file"]))

    def signature_of(self, key: str | None, commit, place: dict, field: str) -> dict | None:
        """The signature of the commit that put an object into a library, from the index and from
        GitHub: None when the index does not say (an index older than the key), {"kind": None} when
        not signed, else its format, whether the library is on github.com and what GitHub said."""
        if not isinstance(place, dict) or field not in place:
            return None
        kind = place.get(field)
        if not isinstance(kind, str) or not kind:
            return {"kind": None}
        hr = cfgmod.split_address((self.index.library(key) or {}).get("address")) if key else None
        return {"kind": kind, "github": bool(hr and hr[0] == "github.com"),
                "check": self.signatures.get(commit) if isinstance(commit, str) else None}

    # ------------------------------------------------------------ cards and views

    def card(self, name: str) -> dict:
        o = self.index.get(name) or {"name": name, "present": False}
        p = prefix_of(name)
        m = o.get("manifest") or {}
        first = o.get("first") or {}
        c = {
            "name": name,
            "prefix": p,
            "display": self.display(name),
            "present": bool(o.get("present")),
            "valid": bool(o.get("valid")),
            "ifc": self.ifc_of(name),
            "libraries": self.libraries_of(o),
            "latest": self.latest_in(o),
            "first_date": first.get("date"),
            "generation": generation(o),
            "same": bool((self.same.get(name) or {}).get("earlier")),
            "title": title_of(o),
            # one line for lists: the title, or else the first line of the description
            "summary": one_line(title_of(o)) or one_line(m.get(DESCRIPTION)),
        }
        if p == "ifc":
            c.update(pins=len(m.get(IFC.PINS) or []))
        elif p == "ckt":
            c.update(design=m.get(CKT.NAME), form=m.get(CKT.FORM), process=process_of(m), author=m.get(AUTHOR),
                     newer=[n["name"] for n in self.newer(name)], base=(base_of(o) or [None])[0])
        elif p == "tb":
            c.update(design=m.get(TB.NAME), newer=[n["name"] for n in self.newer(name)],
                     metrics=[metric_full_name(m.get(TB.NAME) or "?", md.get(METRIC.ID, "?"))
                              for md in m.get(TB.METRICS) or [] if isinstance(md, dict)])
        elif p == "evd":
            c.update(kind=m.get(EVD.KIND), dut=m.get(EVD.DUT), tbs=m.get(EVD.TBS) or [],
                     metrics=m.get(EVD.METRICS) if isinstance(m.get(EVD.METRICS), dict) else {}, author=m.get(AUTHOR))
        elif p == "doc":
            c.update(date=m.get(DOC.DATE), tags=m.get(TAGS) or [])
        elif p == "lib":
            c.update(design=m.get(LIB.NAME), newer=[n["name"] for n in self.newer(name)])
        return c

    def drawing(self, o: dict, m: dict, p: str) -> dict | None:
        """What the page needs to draw the netlist of a circuit or a testbench: its netlists and
        packages, and the symbol of each interface that draws one of its blocks. Which package
        draws a subcircuit is decided by references (type ifc, symbol.rnl): the `ifc` of a circuit
        or a testbench, and the `ifc` of each item of `uses`."""
        files = {f["path"] for f in o.get("files") or []}
        roles = m.get(CKT.FILES if p == "ckt" else TB.FILES)
        roles = roles if isinstance(roles, dict) else {}
        netlists = [x for x in roles.get(ROLE.NETLIST) or [] if x in files]
        extra = [x for r in (ROLE.PACKAGES, ROLE.EXTRAS) for x in roles.get(r) or [] if x in files]
        if p == "ckt":
            ifcs = [m.get(CKT.IFC)] + [u.get(USE.IFC) for u in (m.get(CKT.USES) or {}).values() if isinstance(u, dict)]
        else:
            ifcs = [m.get(TB.IFC)]
        if not netlists:
            return None
        symbols, seen = [], set()
        for ifc in ifcs:
            if not isinstance(ifc, str) or ifc in seen:
                continue
            seen.add(ifc)
            io = self.index.get(ifc) or {}
            f = next((f for f in io.get("files") or [] if f.get("path") == IFC.SYMBOL_FILE), None)
            symbols.append({"ifc": ifc, "name": self.ifc_name(ifc),
                            "file": {k: f.get(k) for k in ("path", "size", "sha256")} if f else None,
                            "sources": self.raw_sources(io) if io.get("present") else []})
        by_name: dict[str, set] = {}
        for sy in symbols:
            if sy["file"]:
                by_name.setdefault(sy["name"], set()).add(sy["ifc"])
        return {"entry": netlists[0], "files": list(dict.fromkeys(netlists + extra)), "symbols": symbols,
                "clash": sorted(n for n, ifcs_ in by_name.items() if len(ifcs_) > 1)}

    def referrers(self, name: str, at: str, prefix: str | None = None) -> list[str]:
        """The objects that refer to `name` at `at` (`toa.yaml:ifc`), or anywhere under it when `at`
        ends with `/` (`toa.yaml:refs/`), of the kind `prefix` when given."""
        o = self.index.get(name) or {}
        out = []
        for r in o.get("referenced_by") or []:
            a = r.get("at") or ""
            hit = a.startswith(at) if at.endswith("/") else a == at
            if hit and (prefix is None or prefix_of(r["name"]) == prefix) and r["name"] not in out:
                out.append(r["name"])
        return out

    def members(self, ifc: str) -> dict[str, list[str]]:
        """The circuits and testbenches of an interface, and the documents about it. Circuits and
        testbenches by series (the series of the same `name` together, then by the earliest
        generation of each), each series by generation, then first publication."""
        def order(n):
            c = self.index.get(n) or {}
            s = self.series(n)
            return (self.design(s) or self.design(n) or "~", s, generation(c) or 0, (c.get("first") or {}).get("date") or "", n)
        out = {"ckt": self.referrers(ifc, "toa.yaml:" + CKT.IFC, "ckt"),
               "tb": self.referrers(ifc, "toa.yaml:" + TB.IFC, "tb"),
               "doc": self.referrers(ifc, "toa.yaml:" + DOC.REFS + "/", "doc")}
        out["ckt"].sort(key=order)
        out["tb"].sort(key=order)
        out["doc"].sort(key=lambda n: ((self.index.get(n) or {}).get("first") or {}).get("date") or "", reverse=True)
        return out

    def lib_members(self, text: bytes | None) -> dict:
        """The list of members of a frozen library (`members.source.jsonl`, type lib), by group in
        the order the list first names them. It is read leniently, to be shown: toa checked it."""
        if text is None:
            return {"read": False, "groups": [], "count": 0, "shown": 0}
        groups: dict[str, list[dict]] = {}
        count = 0
        for line in text.decode("utf-8", "replace").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or not isinstance(d.get(SOURCE.OBJECT), str):
                continue
            count += 1
            if count > MEMBERS_SHOWN:
                continue
            srcs = [s.get("git") for s in d.get(SOURCE.SOURCES) or [] if isinstance(s, dict) and isinstance(s.get("git"), str)]
            g = d.get(SOURCE.GROUP)
            groups.setdefault(g if isinstance(g, str) else "", []).append({
                "object": d[SOURCE.OBJECT],
                "label": d.get(SOURCE.LABEL) if isinstance(d.get(SOURCE.LABEL), str) else None,
                "license": d.get(SOURCE.LICENSE) if isinstance(d.get(SOURCE.LICENSE), str) else None,
                "sources": srcs})
        return {"read": True, "groups": [{"group": g, "members": ms} for g, ms in groups.items()],
                "count": count, "shown": min(count, MEMBERS_SHOWN)}

    def record_targets(self, m: dict) -> list[dict]:
        """The targets of the circuit a record tested (B36) on the metrics of the record, that hold
        under its conditions: a record of the kind mc is held against them by its samples (B37)."""
        dut = m.get(EVD.DUT)
        dm = self.manifest(dut) if isinstance(dut, str) else {}
        mets = m.get(EVD.METRICS) if isinstance(m.get(EVD.METRICS), dict) else {}
        conds = m.get(EVD.CONDITIONS) if isinstance(m.get(EVD.CONDITIONS), dict) else {}
        # a preset of a Monte Carlo simulation holds for the records of its statistics; a preset of
        # one simulation also for the samples drawn around its conditions
        key = tgmod.cond_key(conds)
        plain = tgmod.cond_key({k: x for k, x in conds.items() if k != COND.STATISTICS})
        out = []
        for tg in tgmod.targets_of(dm):
            if tg["metric"] not in mets:
                continue
            if tg["preset"]:
                keys = tgmod.preset_keys(self, dm.get(CKT.IFC), tg["metric"], tg["preset"])
                if keys is None or (key not in keys and plain not in keys):
                    continue
            out.append(tg)
        return out

    def mc_run(self, name: str) -> dict:
        """One record of the kind mc, as the page compares it with another (B37): which samples it
        ran and how, its simulator, its statistics, and where its samples.csv is."""
        o = self.index.get(name) or {}
        m = o.get("manifest") or {}
        conds = m.get(EVD.CONDITIONS) if isinstance(m.get(EVD.CONDITIONS), dict) else {}
        st = conds.get(COND.STATISTICS) if isinstance(conds.get(COND.STATISTICS), dict) else {}
        env = m.get(EVD.ENVIRONMENT) if isinstance(m.get(EVD.ENVIRONMENT), dict) else {}
        sim = env.get(ENV.SIMULATOR) if isinstance(env.get(ENV.SIMULATOR), dict) else {}
        f = next((f for f in o.get("files") or [] if f.get("path") == EVD.SAMPLES_FILE), None)
        mets = m.get(EVD.METRICS) if isinstance(m.get(EVD.METRICS), dict) else {}
        return {"name": name, "first": st.get(STAT.FIRST, 1), "points": st.get(STAT.POINTS), "run": st.get(STAT.RUN),
                "sampling": st.get(STAT.SAMPLING),
                "simulator": " ".join(str(sim[k]) for k in (ENV.NAME, ENV.VERSION) if sim.get(k) is not None) or None,
                "raw": self.raw_prefix(o) if o.get("present") else None,
                "samples": EVD.SAMPLES_FILE if f else None, "samples_sha256": (f or {}).get("sha256"),
                "stats": {k: {s: x.get(s) for s in MCSTAT.ALL} for k, x in mets.items() if isinstance(x, dict)}}

    def test_plan(self, members: dict) -> dict | None:
        """A test plan (type lib): a frozen library whose members are an interface and the testbenches
        that measure it, with circuits when needed; it holds testbenches, and nothing but interfaces,
        testbenches and circuits. Its interfaces (those it holds, and those its testbenches
        measure), its testbenches with their metrics and presets, and its circuits. None for any
        other frozen library, such as one that freezes a whole library."""
        objs = [x["object"] for g in members.get("groups") or [] for x in g["members"]]
        tbs = [x for x in objs if prefix_of(x) == "tb"]
        if not tbs or any(prefix_of(x) not in ("ifc", "tb", "ckt") for x in objs):
            return None
        ifcs = [x for x in objs if prefix_of(x) == "ifc"] + [self.ifc_of(x) for x in tbs]
        rows = []
        for x in tbs:
            m = self.manifest(x)
            presets = m.get(TB.PRESETS) if isinstance(m.get(TB.PRESETS), dict) else {}
            rows.append({"tb": x, "known": self.index.get(x) is not None,
                         "metrics": [metric_view(m.get(TB.NAME), md)["full"] for md in m.get(TB.METRICS) or [] if isinstance(md, dict)],
                         "presets": [{"name": str(k), "sets": len(p) if isinstance(p, list) else 1,
                                      "mc": any(isinstance(y, dict) and COND.STATISTICS in y for y in (p if isinstance(p, list) else [p]))}
                                     for k, p in presets.items()]})
        return {"ifcs": list(dict.fromkeys(x for x in ifcs if x)), "tbs": rows,
                "ckts": [x for x in objs if prefix_of(x) == "ckt"]}

    def ifc_generations(self, name: str) -> list[dict]:
        """The other generations of an interface along `base`, earlier and later, with how many
        circuits and testbenches refer to each: each refers to one generation, so the page of one
        says where the others are."""
        seen, out = {name}, []
        todo = [(x, "earlier") for x in base_of(self.index.get(name) or {})[:1]]
        todo += [(x, "later") for x in (self.index.get(name) or {}).get(INDEX.BASE_BY) or []]
        while todo:
            x, way = todo.pop(0)
            o = self.index.get(x)
            if x in seen or not o or not o.get("present") or prefix_of(x) != "ifc":
                continue
            seen.add(x)
            mb = self.members(x)
            out.append({"ifc": x, "way": way, "generation": generation(o), "ckts": len(mb["ckt"]), "tbs": len(mb["tb"])})
            todo += [(y, way) for y in (base_of(o)[:1] if way == "earlier" else o.get(INDEX.BASE_BY) or [])]
        out.sort(key=lambda e: (e["generation"] or 0, e["ifc"]))
        return out

    def targets_view(self, m: dict, groups: list[dict]) -> list[dict]:
        """The targets of a circuit (B36), each with the values its reproduction groups hold under the
        sets of conditions it holds under, and whether each meets it."""
        out = []
        for tg in tgmod.targets_of(m):
            keys = tgmod.preset_keys(self, m.get(CKT.IFC), tg["metric"], tg["preset"]) if tg["preset"] else None
            # a preset that no testbench of the interface has: the target is shown, never judged
            tg["preset_known"] = tg["preset"] is None or keys is not None
            results = []
            for g in groups if tg["preset_known"] else []:
                if g.get("kind") == EVD.MC:
                    continue  # its samples are held against the target on the record's page
                if keys is not None and tgmod.cond_key(g.get("conditions")) not in keys:
                    continue
                row = next((r for r in g.get("metrics") or [] if r["metric"] == tg["metric"] and r.get("n")), None)
                if row is not None:
                    results.append({"group": g["id"], "cond_text": g.get("cond_text") or "", "value": row["median"],
                                    "n": row["n"], "meets": tgmod.meets(tg, row["median"])})
            tg["results"] = results
            out.append(tg)
        return out

    def view(self, name: str, groups_by_record: dict[str, dict], groups_by_dut: dict[str, list]) -> dict:
        """Everything the page of one object shows."""
        o = self.index.get(name) or {"name": name, "prefix": prefix_of(name), "present": False}
        p = prefix_of(name)
        m = o.get("manifest") or {}
        linked: set[str] = set()
        v: dict = {
            "name": name,
            "prefix": p,
            "display": self.display(name),
            "present": bool(o.get("present")),
            "valid": bool(o.get("valid")),
            "problems": o.get("problems") or [],
            "sha256": o.get("sha256"),
            "license": m.get(LICENSE),
            "author": m.get(AUTHOR),
            "title": title_of(o),
            "description": m.get(DESCRIPTION),
            "tags": [x for x in m.get(TAGS) or [] if isinstance(x, str)] if isinstance(m.get(TAGS), list) else [],
            "generation": generation(o),
            "latest": self.latest_in(o),
            "ifc": self.ifc_of(name),
            "manifest": o.get("manifest"),
            "files": [{k: f.get(k) for k in ("path", "size", "sha256")} for f in o.get("files") or []],
            "locations": [self.location_view(o, loc) for loc in self.sorted_locations(o)],
            "first": o.get("first"),
            "first_signature": self.signature_of((o.get("first") or {}).get("library"), (o.get("first") or {}).get("commit"),
                                                 o.get("first") or {}, INDEX.SIGNATURE),
            "seen": self.seen.get(name),
            "stamps": self.stamps_of(o),
            "same_files": self.same.get(name),
            "removals": [
                {**{k: r.get(k) for k in ("library", "path", "commit", "date", "valid")},
                 "reason": (r.get("record") or {}).get("reason"),
                 "label": (r.get("record") or {}).get("label"),
                 "removed_commit": (r.get("record") or {}).get("commit"),
                 "web": self.web_url(r["library"], r["path"])}
                for r in o.get("removals") or []
            ],
            "references": o.get("references") or [],
            "referenced_by": o.get("referenced_by") or [],
            "base": base_of(o),
            "history": o.get(INDEX.HISTORY),
            "base_by": o.get(INDEX.BASE_BY) or [],
            "newer": self.newer(name),
            "raw": self.raw_prefix(o) if o.get("present") else None,
            "raw_sources": self.raw_sources(o) if o.get("present") else [],
        }
        linked.update(r["name"] for r in v["references"])
        linked.update(r["name"] for r in v["referenced_by"])
        linked.update(v["base"])
        linked.update(v["base_by"])
        linked.update(n["name"] for n in v["newer"])
        h = v["history"] or {}
        for k in ("listed", "verified", "declared"):
            linked.update(h.get(k) or [])
        if h.get("nearest"):
            linked.add(h["nearest"])
        if v["ifc"]:
            linked.add(v["ifc"])
        for k in ("earlier", "later"):
            linked.update(x["object"] for x in (v["same_files"] or {}).get(k) or [])

        if p == "ifc":
            v["pins"] = [{k: pin.get(f) for k, f in (("name", PIN.NAME), ("kind", PIN.KIND), ("direction", PIN.DIRECTION),
                                                     ("width", PIN.WIDTH), ("description", PIN.DESCRIPTION))}
                         for pin in m.get(IFC.PINS) or [] if isinstance(pin, dict)]
            v["probes"] = probes_of(m)
            v["has_symbol"] = any(f["path"] == IFC.SYMBOL_FILE for f in v["files"])
        elif p == "ckt":
            sp = m.get(CKT.SPECIFICATIONS)
            v.update(design=m.get(CKT.NAME), form=m.get(CKT.FORM), process=process_of(m),
                     parameters=m.get(CKT.PARAMETERS),
                     specifications={k: x for k, x in sp.items() if k not in (SPEC.PROCESS, SPEC.TARGETS)} if isinstance(sp, dict) else None,
                     origin=m.get(CKT.ORIGIN), external=m.get(CKT.EXTERNAL),
                     netlist=((m.get(CKT.FILES) or {}).get(ROLE.NETLIST) or []))
            uses = []
            for sub, u in (m.get(CKT.USES) or {}).items():
                u = u if isinstance(u, dict) else {}
                uses.append({"subckt": sub, "ifc": u.get(USE.IFC), "ckt": u.get(USE.CKT),
                             "requirements": u.get(USE.REQUIREMENTS)})
                linked.update(x for x in (u.get(USE.IFC), u.get(USE.CKT)) if isinstance(x, str))
            v["uses"] = uses
            v["drawing"] = self.drawing(o, m, p)
            evds = self.referrers(name, "toa.yaml:" + EVD.DUT, "evd")
            v["records"] = [self.card(r) for r in evds]
            v["groups"] = groups_by_dut.get(name, [])
            for g in v["groups"]:
                linked.update(g["records"])
                linked.update(g["tbs"])
            v["targets"] = self.targets_view(m, v["groups"])
        elif p == "tb":
            metrics = [metric_view(m.get(TB.NAME), md) for md in m.get(TB.METRICS) or [] if isinstance(md, dict)]
            sims = [s for s in m.get(TB.SIMULATORS) or [] if isinstance(s, dict)]
            an = m.get(TB.ANALYZE)
            an = an if isinstance(an, dict) else {}
            # the probes it names, with what the interface says of each (B36)
            known = {p["name"].lower(): p for p in probes_of(self.manifest(m.get(TB.IFC)))}
            probes = [{"name": str(x), "description": (known.get(str(x).lower()) or {}).get("description"),
                       "known": str(x).lower() in known} for x in m.get(TB.PROBES) or [] if isinstance(x, (str, int, float))]
            v.update(design=m.get(TB.NAME), metrics=metrics, simulators=sims, run=m.get(TB.RUN),
                     analyze={k: x for k, x in an.items() if k != ANALYZE.RESULTS} or None, results=an.get(ANALYZE.RESULTS),
                     socket=m.get(TB.SOCKET), probes=probes,
                     parameters=m.get(TB.PARAMETERS), presets=preset_rows(m.get(TB.PRESETS)),
                     external=m.get(TB.EXTERNAL), netlist=((m.get(TB.FILES) or {}).get(ROLE.NETLIST) or []))
            v["drawing"] = self.drawing(o, m, p)
            evds = []
            for r in o.get("referenced_by") or []:
                if prefix_of(r["name"]) == "evd" and r["at"].startswith("toa.yaml:" + EVD.TBS + "/") and r["name"] not in evds:
                    evds.append(r["name"])
            v["records"] = [self.card(r) for r in evds]
            linked.update(c["dut"] for c in v["records"] if c.get("dut"))
        elif p == "evd":
            kind = m.get(EVD.KIND)
            v["kind"] = kind if isinstance(kind, str) else None
            # a kind Gazettoa does not know is shown as it is, by the common rules only (type evd)
            v["known_kind"] = kind in EVD.KINDS
            tree: dict[int, dict] = {}
            for r in o.get("references") or []:
                mt = _LOCK_TREE.match(r.get("at", ""))
                if mt:
                    tree.setdefault(int(mt.group(1)), {})[mt.group(2)] = r["name"]
            env = m.get(EVD.ENVIRONMENT)
            env = env if isinstance(env, dict) else {}
            conds = m.get(EVD.CONDITIONS)
            conds = conds if isinstance(conds, dict) else {}
            # the net of the circuit tested that each probe was, in this run (B36), with what the
            # interface of the circuit says of the probe
            pr = m.get(EVD.PROBES)
            known = {p["name"].lower(): p for p in probes_of(self.manifest(self.ifc_of(m.get(EVD.DUT))))}
            v["probes"] = [{"name": str(k), "net": x, "description": (known.get(str(k).lower()) or {}).get("description")}
                           for k, x in pr.items()] if isinstance(pr, dict) else None
            v.update(dut=m.get(EVD.DUT), tbs=m.get(EVD.TBS) or [],
                     # the three slots in their order, then anything else written there (statistics, B37)
                     conditions=[[k, conds.get(k)] for k in COND.SLOTS] + [[k, x] for k, x in conds.items() if k not in COND.SLOTS],
                     environment=env, simulator=env.get(ENV.SIMULATOR) if isinstance(env.get(ENV.SIMULATOR), dict) else None,
                     metrics=m.get(EVD.METRICS) if isinstance(m.get(EVD.METRICS), dict) else {},
                     evidence=m.get(EVD.EVIDENCE) or [],
                     lock_tree=[{"index": i, **tree[i]} for i in sorted(tree)],
                     group=groups_by_record.get(name))
            v["metric_defs"] = {}
            for t in v["tbs"]:
                tm = self.manifest(t)
                for md in tm.get(TB.METRICS) or []:
                    if isinstance(md, dict):
                        mv = metric_view(tm.get(TB.NAME), md)
                        v["metric_defs"][mv["full"]] = {k: mv[k] for k in ("unit", "better", "tolerance")}
            linked.update(x for x in [v["dut"], *v["tbs"]] if isinstance(x, str))
            if kind == EVD.MC:
                # a Monte Carlo simulation (B37): what the page needs to draw its samples, hold them
                # against the targets of the circuit, and compare it with the others of its group
                st = conds.get(COND.STATISTICS)
                v["statistics"] = st if isinstance(st, dict) else None
                v["targets"] = self.record_targets(m)
                v["runs"] = [self.mc_run(r) for r in (v["group"] or {}).get("records") or [name]]
            v["counts_for"] = repro.record_library(self.index, o) if o.get("present") else None
            if v["group"]:
                linked.update(v["group"]["records"])
        elif p == "doc":
            v.update(date=m.get(DOC.DATE), refs=[x for x in m.get(DOC.REFS) or [] if isinstance(x, str)])
            linked.update(v["refs"])
        elif p == "lib":
            v.update(design=m.get(LIB.NAME), has_members=any(f["path"] == LIB.MEMBERS_FILE for f in v["files"]))
        v["names"] = self.names(sorted(linked | {name}))
        return v
