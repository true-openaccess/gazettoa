"""Serve a built site on this machine, with the files of local libraries beside it.

    python gaze/scripts/serve.py [--site gaze/_site] [--local-files DIR]... [--port 47950]

A site built with `python -m gaze build ... --local-files DIR` reads the files of library <key> from
`local/<key>/…`; this server answers those addresses from `DIR/<key>/…`, the checkout of that
library (the first DIR that has one), so a preview needs no copy of any file. For the small
examples of toa, DIR is `toa/examples`.

Only for this machine: it listens on 127.0.0.1 and answers GET and HEAD.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

GAZE = Path(__file__).resolve().parent.parent
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class Handler(http.server.SimpleHTTPRequestHandler):
    local_files: list[Path] = []

    def translate_path(self, path: str) -> str:
        parts = [p for p in unquote(urlsplit(path).path).split("/") if p]
        if len(parts) >= 2 and parts[0] == "local":
            key, rest = parts[1], parts[2:]
            if not KEY.match(key) or any(p in (".", "..") or "\\" in p or ":" in p for p in rest):
                return str(Path(self.directory) / "__refused__")
            for d in self.local_files:
                if (d / key).is_dir():
                    return str(d.joinpath(key, *rest))
            return str(Path(self.directory) / "__refused__")
        return super().translate_path(path)

    def list_directory(self, path):  # no listings
        self.send_error(404)
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s\n" % (fmt % args))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--site", type=Path, default=GAZE / "_site")
    ap.add_argument("--local-files", type=Path, action="append", default=[],
                    help="a directory holding a checkout of local libraries by their keys; repeatable")
    ap.add_argument("--local-files-from", type=Path,
                    help="a text file of such directories, one a line, relative to the file; a missing file is "
                         "no directory (it keeps paths of this machine out of a shared launch configuration)")
    ap.add_argument("--port", type=int, default=47950)
    a = ap.parse_args()
    if not (a.site / "index.html").is_file():
        sys.exit(f"no site at {a.site}: build it first (python gaze/scripts/examples.py)")
    dirs = list(a.local_files)
    if a.local_files_from and a.local_files_from.is_file():
        for line in a.local_files_from.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                dirs.append(a.local_files_from.parent / line.strip())
    Handler.local_files = [d.resolve() for d in dirs]
    Handler.extensions_map = {**Handler.extensions_map, ".js": "text/javascript", ".json": "application/json",
                              ".scs": "text/plain", ".sp": "text/plain", ".rnl": "text/plain", ".yaml": "text/plain",
                              ".jsonl": "text/plain", ".md": "text/plain", ".py": "text/plain"}
    handler = functools.partial(Handler, directory=str(a.site.resolve()))
    with http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler) as srv:
        print(f"Gazettoa preview on http://127.0.0.1:{a.port}/ (local files: {', '.join(map(str, Handler.local_files)) or 'none'})", file=sys.stderr)
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
