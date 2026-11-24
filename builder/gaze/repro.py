"""Reproduction groups, multi-party verification and results that disagree.

A group is the evidence records of the kind `sim` of one circuit tested (`dut`: the same object
name; a record tests exactly the tree of its `dut`, user 2026-11-23) by one set of testbenches (`tbs`)
under the same conditions. Within a group, for each metric:

- **Multi-party verified** (user, 2026-11-23): values from records of at least two different
  repositories, and the records' object names differ. Only the repository a record counts for
  and its name are looked at, no accounts. Which repository a record counts for is decided in one
  place, `record_library`. Records are counted by name, so the same record in two repositories
  counts once.
- **Disagree** ("不一致", user 2026-11-23) is a state of its own: two values of the group differ
  by more than the testbench's tolerance, max(abs, rel * |median|); the largest minus the smallest
  is compared, equality agreeing. A metric can be multi-party verified and disagree at once.
  `tol` is required by the `tb` type; a metric without one shows "no tolerance" and is not judged.
- Neither state is a problem: a group without the label only lacks it, and values that disagree
  go into no list of problems.

A group is multi-party verified, or disagrees, when one of its metrics is.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from statistics import median

from .fields import COND, EVD, METRIC, TB, kind_of, metric_full_name

EPS = 1e-12


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def group_key(manifest: dict) -> tuple:
    conds = manifest.get(EVD.CONDITIONS)
    conds = conds if isinstance(conds, dict) else {}
    return (
        manifest.get(EVD.DUT) or "",
        tuple(sorted(manifest.get(EVD.TBS) or [])),
        canonical({k: conds.get(k) for k in COND.SLOTS if k in conds}),
    )


def _short(v) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, list):
        return "[" + ",".join(_short(x) for x in v) + "]"
    return str(v)


def conditions_text(c: dict | None) -> str:
    """The conditions of a record in one short line: the sections of its model files, then its
    parameters and options as `name=value`."""
    if not isinstance(c, dict):
        return ""
    parts = [str(mf.get(COND.MODEL_SECTION)) for mf in c.get(COND.MODELS) or []
             if isinstance(mf, dict) and mf.get(COND.MODEL_SECTION) is not None]
    for slot in (COND.PARAMETERS, COND.OPTIONS):
        vals = c.get(slot)
        for k, v in (vals.items() if isinstance(vals, dict) else ()):
            parts.append(f"{k}={_short(v)}")
    return " ".join(parts)


def tolerance(tol: dict | None, ref: float) -> float | None:
    if not isinstance(tol, dict):
        return None
    a = _num(tol.get(METRIC.TOLERANCE_ABS))
    r = _num(tol.get(METRIC.TOLERANCE_REL))
    if a is None and r is None:
        return None
    return max(a or 0.0, (r or 0.0) * abs(ref))


def metric_defs(index, tb_names: list[str]) -> dict[str, dict]:
    """Full metric name -> its definition, from the testbenches the index has."""
    out: dict[str, dict] = {}
    for n in tb_names:
        tb = index.get(n)
        m = (tb or {}).get("manifest") or {}
        tb_name = m.get(TB.NAME)
        if not tb_name:
            continue
        for md in m.get(TB.METRICS) or []:
            if isinstance(md, dict) and md.get(METRIC.ID):
                out.setdefault(metric_full_name(tb_name, md[METRIC.ID]), md)
    return out


def _when(s) -> float:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def record_library(index, rec: dict) -> str:
    """The library an evidence record counts for when multi-party verification is judged.

    Decided by the user (2026-11-23): by the earliest time. A record counts for the library where it was first published,
    by git history: of its places, the one whose commit that added it is the earliest. A copy into
    another library is a later commit there, so it counts for the library copied from. A fork
    shares its original's commits, so a record the fork carries has the same first commit and date
    in both: git cannot tell the fork from the original, and the tie goes to the library listed
    first in the workspace list. Every record in a shared commit goes to the same library, so a
    fork of a whole library makes no multi-party verification.
    """
    order = {lib["key"]: i for i, lib in enumerate(index.libraries)}
    places = [loc for loc in rec.get("locations") or [] if loc.get("first_date")]
    if places:
        best = min(places, key=lambda l: (_when(l["first_date"]), order.get(l["library"], 1 << 30)))
        return best["library"]
    first = (rec.get("first") or {}).get("library")
    if first:
        return first
    locs = rec.get("locations") or []
    return locs[0]["library"] if locs else ""


def source_of(index, rec: dict) -> str:
    """The repository a record counts for: the address of its `record_library`, else its key."""
    key = record_library(index, rec)
    lib = index.library(key) if key else None
    return (lib or {}).get("address") or key or ""


def build_groups(index) -> list[dict]:
    buckets: dict[tuple, list[dict]] = {}
    for o in index.objects.values():
        if kind_of(o["name"]) != "evd" or not o.get("present") or not o.get("valid"):
            continue
        m = o.get("manifest") or {}
        if m.get(EVD.KIND) != EVD.SIM:
            continue  # only simulations are compared; other kinds of evidence are shown as they are
        if not m.get(EVD.DUT):
            continue
        buckets.setdefault(group_key(m), []).append(o)
    groups = []
    for key, recs in buckets.items():
        recs.sort(key=lambda r: r["name"])
        m0 = recs[0]["manifest"]
        dut, tbs, conds = key
        defs = metric_defs(index, list(tbs))
        sources = {r["name"]: source_of(index, r) for r in recs}
        libraries = {r["name"]: record_library(index, r) for r in recs}
        names = [r["name"] for r in recs]
        metric_names = sorted({k for r in recs for k in (r["manifest"].get(EVD.METRICS) or {})})
        metrics = []
        for full in metric_names:
            vals = []
            for r in recs:
                v = _num((r["manifest"].get(EVD.METRICS) or {}).get(full))
                if v is not None:
                    vals.append({"record": r["name"], "value": v, "source": sources[r["name"]],
                                 "library": libraries[r["name"]]})
            md = defs.get(full) or {}
            n_sources = len({v["source"] for v in vals})
            row = {
                "metric": full,
                "unit": md.get(METRIC.UNIT),
                "better": md.get(METRIC.BETTER),
                "tolerance": md.get(METRIC.TOLERANCE),
                "values": vals,
                "n": len(vals),
                "sources": n_sources,
                # records are distinct object names, so two sources are two names
                "multi_party": n_sources >= 2,
                "agree": None,
                "disagree": False,
            }
            if vals:
                xs = [v["value"] for v in vals]
                med = median(xs)
                spread = max(xs) - min(xs)
                tol = tolerance(md.get(METRIC.TOLERANCE), med)
                row.update(median=med, min=min(xs), max=max(xs), spread=spread, tol_value=tol)
                if tol is not None and len(vals) >= 2:
                    row["agree"] = spread <= tol + EPS
                    row["disagree"] = not row["agree"]
            metrics.append(row)
        groups.append({
            "key": "|".join([dut, ",".join(tbs), conds]),
            "dut": dut,
            "tbs": list(tbs),
            "conditions": m0.get(EVD.CONDITIONS) or {},
            "cond_text": conditions_text(m0.get(EVD.CONDITIONS)),
            "records": names,
            "sources": sorted(set(sources.values())),
            "multi_party": any(r["multi_party"] for r in metrics),
            "disagree": any(r["disagree"] for r in metrics),
            "metrics": metrics,
        })
    groups.sort(key=lambda g: (g["dut"], g["key"]))
    for g in groups:
        # stable from one build to the next: the same records under the same key keep their id
        g["id"] = hashlib.sha256(g["key"].encode("utf-8")).hexdigest()[:12]
    return groups
