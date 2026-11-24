"""When the libraries were last scanned, and whether a run of gaze-pages.yml has anything to build.

    python scripts/scan.py check instance/workspace.source.jsonl .work/site
    python scripts/scan.py write .work/site --stamp STAMP --changed TIME

`check` makes the stamp of what a build would read: this repository's commit, the toa it is read with
and the other tools (from the environment of gaze-pages.yml), and the head of the branch of every
library the workspace list includes, read with `git ls-remote`, which fetches nothing. It compares
the stamp with the one in data/scan.json of the last site and writes to the file in GITHUB_OUTPUT
(else to standard output):

    full     "true" to read the libraries and build the site; "false" when the last site is there and
             was built from the same stamp, so the run only writes the new scan time into it
    stamp    the stamp; empty when a head or the commit could not be read, and then the build is
             full, so that the problem shows: never skip on a guess
    changed  when the content last changed: kept from the last site when the stamp is the same,
             empty (now) when it is not
    why      the reason, in words

A run by hand (GITHUB_EVENT_NAME workflow_dispatch) is always full.

`write` writes data/scan.json of a site: `scanned` now, `changed` (now when empty), `stamp`, and
`partial` when toa could not fetch some library: the next run then builds again, keeping `changed`
when the stamp is the same. The page reads the file at load and shows both times, so a run that
builds nothing changes only this file. The builder writes it too, with both times its own.

Standard library only, like the builder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCAN_FORMAT = "gaze-scan/1"
SCAN_FILE = Path("data") / "scan.json"
# what else the site is built with: from the environment of gaze-pages.yml
ENVIRONMENT = ("GITHUB_SHA", "TOA_COMMIT", "TOA_RUST", "RNL_SHA256")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def libraries(text: str) -> list[dict]:
    """The include lines of a workspace list (TOA 8.1): group, branch (main when not written) and the
    git addresses of its sources; a source that is not git (on this machine) is kept as None."""
    out = []
    for line in text.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or "include" not in d:
            continue
        srcs = [s.get("git") if isinstance(s, dict) and isinstance(s.get("git"), str) else None
                for s in d.get("sources") or []]
        out.append({"group": str(d.get("group") or ""), "branch": str(d.get("branch") or "main"), "sources": srcs or [None]})
    return out


def ls_remote(url: str, branch: str) -> str | None:
    """The commit at the head of `branch` of the repository at `url`, or None."""
    try:
        r = subprocess.run(["git", "ls-remote", "--", url, f"refs/heads/{branch}"], capture_output=True, text=True,
                           timeout=60, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in r.stdout.splitlines() if r.returncode == 0 else []:
        commit, _, ref = line.partition("\t")
        if ref == f"refs/heads/{branch}" and len(commit) in (40, 64):
            return commit
    return None


def stamp(libs: list[dict], env: dict, head=None) -> tuple[str, list[str]]:
    """The stamp and the lines it is the SHA-256 of; an empty stamp when any of them is unknown.
    `head(url, branch)` reads a head; git ls-remote when not given."""
    head = head or ls_remote
    lines = [f"{k} {env.get(k, '')}" for k in ENVIRONMENT]
    known = all(env.get(k) for k in ENVIRONMENT[:2])
    for lib in libs:
        for url in lib["sources"]:
            commit = head(url, lib["branch"]) if url else None
            known = known and commit is not None
            lines.append(f"{lib['group']} {url or '(not git)'} {lib['branch']} {commit or '?'}")
    text = "".join(x + "\n" for x in lines)
    return (hashlib.sha256(text.encode("utf-8")).hexdigest() if known else ""), lines


def read_scan(site: Path) -> dict | None:
    try:
        d = json.loads((site / SCAN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("format") == SCAN_FORMAT else None


def decide(new: str, previous: dict | None, site_there: bool, event: str) -> dict:
    """Whether to build: {"full", "changed", "why"}. `previous` is data/scan.json of the last site
    (or of the published one, taken back when the cache is gone); `site_there`, whether the whole
    last site is at hand to publish again."""
    old = str((previous or {}).get("stamp") or "")
    same = bool(new) and new == old
    changed = str(previous.get("changed") or "") if same and previous else ""
    if not new:
        why = "something could not be read"
    elif not old:
        why = "no stamp of an earlier build"
    elif not same:
        why = "something changed"
    elif previous.get("partial"):
        why = "the last build could not fetch every library"
    elif event == "workflow_dispatch":
        why = "run by hand"
    elif not site_there:
        why = "the last site is not at hand"
    else:
        return {"full": False, "changed": changed, "why": "nothing changed"}
    return {"full": True, "changed": changed, "why": why}


def write_scan(site: Path, stamp_: str, changed: str, scanned: str, partial: bool = False) -> dict:
    d = {"format": SCAN_FORMAT, "scanned": scanned, "changed": changed or scanned, "stamp": stamp_}
    if partial:
        d["partial"] = True
    p = site / SCAN_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(d, indent=1) + "\n")
    return d


def output(pairs: dict) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    text = "".join(f"{k}={v}\n" for k, v in pairs.items())
    if out:
        with open(out, "a", encoding="utf-8", newline="\n") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="scan.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="whether this run builds")
    c.add_argument("workspace")
    c.add_argument("site")
    w = sub.add_parser("write", help="write data/scan.json of a site")
    w.add_argument("site")
    w.add_argument("--stamp", default="")
    w.add_argument("--changed", default="")
    w.add_argument("--partial", action="store_true", help="toa could not fetch some library")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        site = Path(a.site)
        new, lines = stamp(libraries(Path(a.workspace).read_text(encoding="utf-8")), dict(os.environ))
        for x in lines:
            print(x)
        d = decide(new, read_scan(site), (site / "index.html").is_file(), os.environ.get("GITHUB_EVENT_NAME", ""))
        print(f"{'build' if d['full'] else 'no build'}: {d['why']}")
        output({"full": "true" if d["full"] else "false", "stamp": new, "changed": d["changed"], "why": d["why"]})
    else:
        d = write_scan(Path(a.site), a.stamp, a.changed, now(), a.partial)
        print(json.dumps(d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
