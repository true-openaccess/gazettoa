"""The metrics of tb.sp from the results ngspice writes (demo library of Gazettoa).

    python analyze.py RESULTS OUTPUT

RESULTS holds results.raw (the ASCII raw file of SPICE) and conditions.json, whose probes say which
net the probe stage1 was; the script writes OUTPUT/metrics.json and OUTPUT/evidence/.
"""
import json
import sys
from pathlib import Path


def read_raw(path):
    """The vectors of an ASCII raw file of one analysis, by lower-case name."""
    lines = path.read_text(encoding="utf-8").splitlines()
    names, i = [], 0
    while i < len(lines):
        if lines[i].lower().startswith("variables:"):
            i += 1
            while i < len(lines) and not lines[i].lower().startswith("values:"):
                names.append(lines[i].split()[1].lower())
                i += 1
            break
        i += 1
    numbers = " ".join(lines[i + 1:]).split()
    data = {n: [] for n in names}
    k = 0
    while k + len(names) < len(numbers):
        for j, n in enumerate(names):
            data[n].append(float(numbers[k + 1 + j].split(",")[0]))
        k += len(names) + 1
    return data


def crossing(t, v, level, rising):
    for a in range(1, len(v)):
        if (v[a - 1] < level <= v[a]) if rising else (v[a - 1] > level >= v[a]):
            return t[a - 1] + (level - v[a - 1]) * (t[a] - t[a - 1]) / (v[a] - v[a - 1])
    return None


def main(results, output):
    cond = json.loads((results / "conditions.json").read_text(encoding="utf-8"))
    vdd = cond["parameters"]["vdd"]
    d = read_raw(results / "results.raw")
    t = d["time"]
    stage1 = f"v(x1.{cond['probes']['stage1']})".lower()
    start = crossing(t, d["v(a)"], vdd / 2, True)
    tpd = crossing(t, d["v(y)"], vdd / 2, True) - start
    tpd1 = crossing(t, d[stage1], vdd / 2, False) - start
    (output / "evidence").mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps({"tpd": tpd * 1e12, "tpd1": tpd1 * 1e12}), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
