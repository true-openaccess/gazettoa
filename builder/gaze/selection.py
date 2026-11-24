"""The table of the circuits of an interface (the page's tab "Implementations", with its scatter plot).

One row per circuit; the columns are a few fixed ones from the circuit's card, then one per metric of
the testbenches, keyed by the metric's full name `<name>.<id>`. A circuit's metrics are kept per set
of conditions it was simulated under (`conds`, by an id of the set; `conds` of the table lists the
sets, the one with the most circuits first): a metric cell is the median of the values the
reproduction groups of that circuit and those conditions hold, with the two labels of the groups,
multi-party verified and disagree (repro.py). The page shows one set of conditions at a time.

A circuit may have targets on metrics (`specifications.targets`, B36; targets.py): each row lists
them by metric, with the ids of the sets of conditions each holds under (None: every set), and the
page shows a target beside the value under the conditions chosen.

By default the page shows the head of each series, the generations a library marks latest or else
the newest (TOA 3.4, 5.2; views.Model.series_groups), and the others on request.

This module is the only place that says what the table shows: the fixed columns are read from the
cards of the circuits (views.Model.card, which reads manifests through fields.py), and the
metric columns from the testbenches through fields.py. The page draws whatever columns it is
given, by their kind, and knows no field of a manifest. A label is English and translated on the
page (scripts/i18n_keys.py collects the labels written here).
"""

from __future__ import annotations

from collections import Counter
from statistics import median

from . import targets as tgmod
from .fields import CKT, EVD, METRIC, TB, metric_full_name
from .repro import conditions_text

# The fixed columns, in order: `card` is the key of the circuit's card the value comes from; a
# column `hidden` is left out until the reader chooses it. The kinds: text, number, date, latest (the
# libraries that mark it latest), libraries (where it is), and metric for the columns after these.
FIXED = [
    {"key": "form", "label": "Form", "kind": "text", "card": "form"},
    {"key": "process", "label": "Process", "kind": "text", "card": "process"},
    {"key": "latest", "label": "Latest", "kind": "latest", "card": "latest"},
    {"key": "libraries", "label": "Libraries", "kind": "libraries", "card": "libraries"},
    {"key": "first_date", "label": "First published", "kind": "date", "card": "first_date"},
    {"key": "author", "label": "Author", "kind": "text", "card": "author", "hidden": True},
    {"key": "generation", "label": "Generation", "kind": "number", "card": "generation", "hidden": True},
]


def metric_columns(model, tbs: list[str], groups: list[dict]) -> list[dict]:
    cols: dict[str, dict] = {}
    for n in tbs:
        m = model.manifest(n)
        tb_name = m.get(TB.NAME)
        if not tb_name:
            continue
        for md in m.get(TB.METRICS) or []:
            if isinstance(md, dict) and md.get(METRIC.ID):
                full = metric_full_name(tb_name, md[METRIC.ID])
                cols.setdefault(full, {"key": full, "label": str(md[METRIC.ID]), "group": tb_name, "kind": "metric",
                                       "unit": md.get(METRIC.UNIT), "better": md.get(METRIC.BETTER)})
    # a metric of a record whose testbench is not in this instance still gets a column
    for g in groups:
        for r in g.get("metrics") or []:
            full = r["metric"]
            if full not in cols:
                group, _, mid = full.rpartition(".")
                cols[full] = {"key": full, "label": mid or full, "group": group, "kind": "metric",
                              "unit": r.get("unit"), "better": r.get("better")}
    # the columns of one testbench together, for the page's header over them
    order = {g: i for i, g in enumerate(dict.fromkeys(c["group"] for c in cols.values()))}
    return sorted(cols.values(), key=lambda c: order[c["group"]])


def _cells(metrics: list[dict], gs: list[dict]) -> tuple[dict, dict]:
    values, marks = {}, {}
    for col in metrics:
        rs = [r for g in gs for r in g.get("metrics") or [] if r["metric"] == col["key"]]
        xs = [v["value"] for r in rs for v in r.get("values") or []]
        if not xs:
            continue
        values[col["key"]] = median(xs)
        marks[col["key"]] = {"n": len(xs), "multi": any(r.get("multi_party") for r in rs),
                             "disagree": any(r.get("disagree") for r in rs)}
    return values, marks


def build(model, ckts: list[str], tbs: list[str], groups: list[dict]) -> dict:
    # a Monte Carlo simulation gives statistics, not one value: its groups are on the circuit's
    # page, not in this table (B37)
    groups = [g for g in groups if g.get("kind") != EVD.MC]
    metrics = metric_columns(model, tbs, groups)
    by_dut: dict[str, list[dict]] = {}
    for g in groups:
        by_dut.setdefault(g["dut"], []).append(g)
    # the head of each series, and on its first head how many other generations there are
    place: dict[str, dict] = {}
    for s in model.series_groups(ckts):
        for i, n in enumerate(s["heads"]):
            place[n] = {"head": True, "others": len(s["rest"]) if i == 0 else 0, "unmarked": not s["marked"]}
        for n in s["rest"]:
            place[n] = {"head": False, "others": 0, "unmarked": not s["marked"]}
    # the sets of conditions, by the canonical form of the slots (repro.py), each with an id
    ids: dict[str, str] = {}
    texts: dict[str, str] = {}
    count: Counter = Counter()
    rows = []
    for ckt in ckts:
        card = model.card(ckt)
        sets: dict[str, list[dict]] = {}
        for g in by_dut.get(ckt, []):
            sets.setdefault(tgmod.cond_key(g.get("conditions")), []).append(g)
        conds = {}
        for key, gs in sets.items():
            cid = ids.setdefault(key, f"c{len(ids)}")
            texts[cid] = conditions_text(gs[0].get("conditions"))
            count[cid] += 1
            values, marks = _cells(metrics, gs)
            conds[cid] = {"values": values, "marks": marks, "groups": [g["id"] for g in gs]}
        p = place.get(ckt, {"head": True, "others": 0, "unmarked": True})
        rows.append({"ckt": ckt, "summary": card.get("summary"), **p,
                     # a library of this instance marks a later generation of its series latest (TOA 7.5)
                     "newer": bool(card.get("newer")), "valid": card.get("valid"),
                     "values": {c["key"]: card.get(c["card"]) for c in FIXED}, "conds": conds})
    # the targets of each circuit, with the sets of conditions (by id) each holds under; a set no
    # record of this interface was run under has no id, as the page cannot show it
    for r in rows:
        m = model.manifest(r["ckt"])
        tg: dict[str, list] = {}
        for x in tgmod.targets_of(m):
            conds_of = None
            if x["preset"]:
                keys = tgmod.preset_keys(model, m.get(CKT.IFC), x["metric"], x["preset"])
                conds_of = sorted(ids[k] for k in keys or () if k in ids)
            tg.setdefault(x["metric"], []).append({"min": x["min"], "max": x["max"], "preset": x["preset"], "conds": conds_of})
        if tg:
            r["targets"] = tg
    order = sorted(count, key=lambda c: (-count[c], texts[c]))
    fixed = [{k: c[k] for k in ("key", "label", "kind", "hidden") if k in c} for c in FIXED]
    return {"columns": fixed + metrics, "rows": rows,
            "conds": [{"id": c, "text": texts[c], "circuits": count[c]} for c in order]}
