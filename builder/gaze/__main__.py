"""python -m gaze build --instance DIR --index DIR --out DIR

Run from gaze/builder/, or with gaze/builder/ on PYTHONPATH.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from . import __version__
from .build import build
from .config import ConfigError
from .index import IndexError_


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gaze", description="Build the static site of a Gazettoa instance from the index of toa.")
    ap.add_argument("--version", action="version", version=f"gaze {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the site")
    b.add_argument("--instance", required=True, type=Path, help="the instance: workspace.source.jsonl and gaze.yaml")
    b.add_argument("--index", required=True, type=Path, help="the output of `toa index` (format 2)")
    b.add_argument("--out", required=True, type=Path, help="where the site is written; an earlier build there is reused")
    b.add_argument("--prev", type=Path, help="an earlier build to reuse, when it is not in --out")
    b.add_argument("--toa", help="the toa executable, to copy files of libraries the page cannot reach (default: toa on PATH)")
    b.add_argument("--copy-raw", action="store_true", help="copy the files of every object into the site, for a preview or a private instance")
    b.add_argument("--offline", action="store_true", help="stay offline: pass --offline to toa when copying, and ask neither Software Heritage nor GitHub")
    b.add_argument("--site-url", help="the address the site is published at (default: gaze.yaml, else from GitHub Actions)")
    b.add_argument("--local-files", type=Path, action="append", default=[],
                   help="a directory with a checkout of libraries by their keys (DIR/<key>/); the page reads their files "
                        "from local/<key>/, which scripts/serve.py serves. For a preview on this machine; repeatable")
    b.add_argument("--rnl", help="the rnl executable, to draw the symbols of interfaces (default: rnl on PATH)")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        toa = a.toa or shutil.which("toa")
        try:
            r = build(a.instance, a.index, a.out, prev=a.prev, toa=toa, copy_all=a.copy_raw,
                      offline=a.offline, site_url=a.site_url, local_files=a.local_files,
                      rnl=a.rnl or shutil.which("rnl"))
        except (ConfigError, IndexError_) as e:
            print(f"gaze: {e}", file=sys.stderr)
            return 3
        print(f"gaze: built {a.out}: {r['libraries']} libraries, {r['ifcs']} interfaces, "
              f"{r['objects']} names, {r['groups']} reproduction groups, {r['copied']} objects copied, "
              f"{r['changes']} changes, {r['symbols']} symbols drawn with rnl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
