"""The metrics of tb.sp from the results ngspice writes (demo library of Gazettoa).

    python analyze.py RESULTS OUTPUT

RESULTS holds results.raw (the ASCII raw file of SPICE) and conditions.json; the script writes
OUTPUT/metrics.json and OUTPUT/evidence/.
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
    vdd = json.loads((results / "conditions.json").read_text(encoding="utf-8"))["parameters"]["vdd"]
    d = read_raw(results / "results.raw")
    t = d["time"]
    tpd = crossing(t, d["v(y)"], vdd / 2, False) - crossing(t, d["v(a)"], vdd / 2, True)
    window = [(a, b) for a, b in zip(t, d["i(vdd)"]) if a >= 0.1e-9]
    charge = sum((window[j][0] - window[j - 1][0]) * (window[j][1] + window[j - 1][1]) / 2 for j in range(1, len(window)))
    power = -charge * vdd / (window[-1][0] - window[0][0])
    (output / "evidence").mkdir(parents=True, exist_ok=True)
    (output / "metrics.json").write_text(json.dumps({"tpd": tpd * 1e12, "power": power * 1e6}), encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
