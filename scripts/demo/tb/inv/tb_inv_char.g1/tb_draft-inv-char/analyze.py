"""The metrics of tb.sp from the measurements ngspice writes (drawing demo of Gazettoa).

    python analyze.py MEASUREMENTS > metrics.json
"""
import json
import sys

m = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if "=" in line:
        k, v = line.split("=", 1)
        m[k.strip().lower()] = float(v.split()[0])
print(json.dumps({"tpd": m["tpd"] * 1e12, "power": m["pavg"] * 1e6}))
