"""Make the test data tests/data/pll-subset/ from a checkout of the PLL test library.

    python gaze/scripts/pll_subset.py --pll DIR [--toa EXE] [--out DIR]

The PLL library (the PLL of rnl-gallery, converted to TOA by the Virtuoso line; CC0-1.0) is not
in this repository. Six of its objects are: the comparator `cmp-physical-v14-pdk110-54` (its
interface, whose symbol.rnl only applies the standard symbol $COMPARATOR to the instances of the
subcircuit, and its circuit, a Spectre netlist that uses the package pll_semantics.rnl of its own
object by path), and the two inverters the circuit uses (their interfaces and circuits). They are
copied byte for byte, published with `toa publish` into a new git repository with a fixed date
and a made-up address, and indexed with `toa index`. Written:

    <out>/pll/      the library as published: the six objects, their source lists, the library list
    <out>/index/    what toa index wrote for it (no paths of this machine)

The objects keep their names: a change to any file of them would be another object.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GAZE = Path(__file__).resolve().parent.parent
IFC_NAME = "cmp-physical-v14-pdk110-54"
ADDRESS = "https://example.org/pll-subset/pll.git"
DATE = "2026-11-24T00:00:00Z"
NAME = re.compile(r"\b(?:ifc|ckt)_[0-9a-f]{40}\b")
INDEX_FILES = ("index.json", "problems.jsonl", "libraries", "objects")


def run(cmd: list, **kw) -> None:
    print("+", " ".join(str(c) for c in cmd), file=sys.stderr)
    r = subprocess.run([str(c) for c in cmd], stdin=subprocess.DEVNULL, **kw)
    if r.returncode != 0:
        sys.exit(f"exit {r.returncode}")


def find(pll: Path, name: str) -> Path:
    """The directory of an object in the library, by its name."""
    kind = name.split("_", 1)[0]
    hits = [d for d in (pll / kind).glob(f"*/{name}") if d.is_dir()] + [d for d in (pll / kind).glob(f"*/*/{name}") if d.is_dir()]
    if len(hits) != 1:
        sys.exit(f"{name}: {len(hits)} directories in {pll / kind}")
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pll", type=Path, required=True, help="a checkout of the PLL test library")
    ap.add_argument("--toa", help="the toa executable (default: ../toa/target/release/toa beside gaze/)")
    ap.add_argument("--out", type=Path, default=GAZE / "tests" / "data" / "pll-subset")
    a = ap.parse_args()
    exe = "toa.exe" if os.name == "nt" else "toa"
    toa = Path(a.toa) if a.toa else GAZE.parent / "toa" / "target" / "release" / exe
    if not toa.is_file():
        sys.exit(f"no toa executable at {toa}")
    pll = a.pll.resolve()

    ckts = [d for d in (pll / "ckt" / IFC_NAME).glob("*/ckt_*") if d.is_dir()]
    if len(ckts) != 1:
        sys.exit(f"{len(ckts)} circuits of {IFC_NAME} in {pll}")
    ckt = ckts[0]
    names = [ckt.name] + sorted(set(NAME.findall((ckt / "toa.yaml").read_bytes().decode("utf-8"))))
    dirs = {n: (ckt if n == ckt.name else find(pll, n)) for n in names}
    if len(dirs) != 6:
        sys.exit(f"expected six objects, found {len(dirs)}: {sorted(dirs)}")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "pll"
        for n, d in dirs.items():
            shutil.copytree(d, repo / d.relative_to(pll))
        (repo / ".gitattributes").write_bytes(b"* -text\n")
        env = {**os.environ, "GIT_AUTHOR_NAME": "Gazettoa test data", "GIT_AUTHOR_EMAIL": "test@example.org",
               "GIT_COMMITTER_NAME": "Gazettoa test data", "GIT_COMMITTER_EMAIL": "test@example.org",
               "GIT_AUTHOR_DATE": DATE, "GIT_COMMITTER_DATE": DATE, "GIT_CONFIG_COUNT": "1",
               "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"}
        run(["git", "init", "--quiet", "--object-format=sha1"], cwd=repo, env=env)
        run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=repo, env=env)
        run(["git", "add", ".gitattributes"], cwd=repo, env=env)
        run(["git", "commit", "--quiet", "-m", "Start the library"], cwd=repo, env=env)
        # toa publish marks the newest generation of each series latest, as for the PLL library
        run([toa, "publish", "--to", ADDRESS, "--branch", "main", "--commit"], cwd=repo, env=env)
        run([toa, "check"], cwd=repo, env=env)
        ws = Path(tmp) / "workspace.source.jsonl"
        ws.write_bytes((json.dumps({"toa": "source/1"}) + "\n" + json.dumps(
            {"include": "library.source.jsonl", "group": "pll", "branch": "main",
             "sources": [{"git": ADDRESS}, {"local": "pll"}]}) + "\n").encode("utf-8"))
        idx = Path(tmp) / "index"
        run([toa, "index", "--workspace", ws, "--out", idx, "--offline"])
        for f in idx.rglob("*"):
            if f.is_file() and tmp.replace("\\", "/").lower() in f.read_bytes().decode("utf-8", "replace").replace("\\\\", "/").replace("\\", "/").lower():
                sys.exit(f"{f}: holds a path of this machine")

        out = a.out.resolve()
        for sub in ("pll", "index"):
            if (out / sub).exists():
                shutil.rmtree(out / sub)
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(repo, out / "pll", ignore=shutil.ignore_patterns(".git"))
        (out / "index").mkdir()
        for f in INDEX_FILES:
            src = idx / f
            if src.is_dir():
                shutil.copytree(src, out / "index" / f)
            elif src.is_file():
                shutil.copy2(src, out / "index" / f)
    (out / ".gitattributes").write_bytes(b"* -text\n")
    print(f"{len(dirs)} objects -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
