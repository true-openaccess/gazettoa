"""The targets of a circuit, and the sets of conditions each holds under (type ckt, B36).

A target is what the author of a circuit aims for on one metric of a testbench, by the metric's
full name `<name>.<id>`: at least one of `min` and `max`, and optionally `preset`, the preset of
that testbench under which it holds; without `preset`, it holds under every set of conditions.
A preset is one set of conditions or a list of sets (type tb). Evidence records give their
conditions, not the name of a preset, so a record is matched to a preset by its three slots
(`parameters`, `options`, `models`), compared as data: numbers by value, keys in any order. A set
of a Monte Carlo simulation also has `statistics` (B37), compared without `first`, `points` and
`run`: a record of the first ten samples of a preset of two hundred is a record of that preset.

Targets are not results. Whether a value meets a target is shown; a value that misses one is no
problem of the circuit or of the record.
"""

from __future__ import annotations

from .fields import CKT, COND, SPEC, TARGET, TB
from .repro import canonical, shared_statistics


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    return float(v) if isinstance(v, (int, float)) else None


def _norm(v):
    """A value with its numbers by value, so that 2 and 2.0 compare alike."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        f = float(v)
        return int(f) if f.is_integer() else f
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _norm(x) for k, x in v.items()}
    return v


def cond_key(c) -> str:
    """The key of a set of conditions: its three slots, and the statistics of a Monte Carlo
    simulation but which samples and how, as data."""
    c = c if isinstance(c, dict) else {}
    k = {s: c.get(s) for s in COND.SLOTS if s in c}
    st = shared_statistics(c)
    if st is not None:
        k[COND.STATISTICS] = st
    return canonical(_norm(k))


def preset_sets(presets, name: str) -> list[dict] | None:
    """The sets of conditions of a preset of a testbench, or None when it has no such preset."""
    p = presets.get(name) if isinstance(presets, dict) else None
    if isinstance(p, dict):
        return [p]
    if isinstance(p, list):
        return [x for x in p if isinstance(x, dict)]
    return None


def targets_of(manifest: dict) -> list[dict]:
    """The targets of a circuit in the order written: `{metric, min, max, preset}`. An entry that is
    not a target is left out; the index reports it."""
    sp = manifest.get(CKT.SPECIFICATIONS)
    tg = sp.get(SPEC.TARGETS) if isinstance(sp, dict) else None
    out: list[dict] = []
    if not isinstance(tg, dict):
        return out
    for metric, val in tg.items():
        for x in val if isinstance(val, list) else [val]:
            if not isinstance(x, dict):
                continue
            lo, hi = _num(x.get(TARGET.MIN)), _num(x.get(TARGET.MAX))
            if lo is None and hi is None:
                continue
            preset = x.get(TARGET.PRESET)
            out.append({"metric": str(metric), "min": lo, "max": hi, "preset": preset if isinstance(preset, str) else None})
    return out


def preset_keys(model, ifc: str | None, metric: str, preset: str) -> set[str] | None:
    """The keys of the sets of conditions of `preset`, in the testbenches of `ifc` whose name is the
    first part of `metric`, every generation of them; None when none of them has that preset."""
    tb_name = metric.rpartition(".")[0]
    keys: set[str] = set()
    found = False
    for n in model.referrers(ifc, "toa.yaml:" + TB.IFC, "tb") if ifc else []:
        m = model.manifest(n)
        if m.get(TB.NAME) != tb_name:
            continue
        sets = preset_sets(m.get(TB.PRESETS), preset)
        if sets is None:
            continue
        found = True
        keys.update(cond_key(s) for s in sets)
    return keys if found else None


def meets(target: dict, value: float) -> bool:
    return (target["min"] is None or value >= target["min"]) and (target["max"] is None or value <= target["max"])
