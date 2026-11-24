"""Put the fonts of the site into web/fonts/, from pinned npm packages of Fontsource.

The site ships its fonts and fetches none from elsewhere (decisions B22, point 5). This script
is how web/fonts/ was made; run it again only to change a version:

    python scripts/fonts.py                 # npm pack the pinned packages into a temporary folder
    python scripts/fonts.py --from DIR      # or use the .tgz files already in DIR

Each package is checked against the SHA-512 pinned below before anything is taken from it, and
only .woff2 files and the licence are read from it. What is written:

- IBM Plex Sans, weights 400, 500, 600 and 700; IBM Plex Mono, 400 and 600; the Latin and
  Latin Extended parts only. Other scripts fall back to the system fonts.
- Noto Sans SC, the variable font (all weights in one file per part), cut by Fontsource into
  about a hundred parts by unicode-range: a page fetches only the parts its characters need.
- fonts.css with the @font-face rules, under the family names tokens.css asks for, and the
  licence of each family (SIL Open Font License 1.1).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

GAZE = Path(__file__).resolve().parents[1]
OUT = GAZE / "web" / "fonts"

PACKAGES = [
    {
        "package": "@fontsource/ibm-plex-sans", "version": "5.3.0",
        "integrity": "sha512-CbE4CbbEEZJX860XyUiRpsksXIQR8Rp2XDva2VO53NJox9tVNtusrysd2x5YkUEY3ErQ66W1IiiQL8/wihhw5w==",
        "family": "IBM Plex Sans", "dir": "ibm-plex-sans", "weights": [400, 500, 600, 700],
    },
    {
        "package": "@fontsource/ibm-plex-mono", "version": "5.3.0",
        "integrity": "sha512-eTgnZjZEGk1QtD3ZstF+Vclo2HLAni8YMy34/DxllwZvyz1lR/1RF/xTiAquOBO7MvqBx8D2Ig2WCPMVfdZu7Q==",
        "family": "IBM Plex Mono", "dir": "ibm-plex-mono", "weights": [400, 600],
    },
    {
        "package": "@fontsource-variable/noto-sans-sc", "version": "5.3.1",
        "integrity": "sha512-UB96JJ17HyD5ehEU7Em0hDdh7fvTMB4B4Hzmq5c4QaNwwSLqTrdM2S+coySeBqCkXwh0DxqXT0b0wMrmzorFpQ==",
        "family": "Noto Sans SC", "dir": "noto-sans-sc", "variable": True,
    },
]
SUBSETS = ("latin", "latin-ext")
FACE = re.compile(r"@font-face\s*\{(?P<body>[^}]*)\}", re.S)
URL = re.compile(r"url\(\./files/(?P<file>[A-Za-z0-9_.\[\]-]+\.woff2)\)")
RANGE = re.compile(r"unicode-range:\s*(?P<r>[^;]+);")
WEIGHT = re.compile(r"font-weight:\s*(?P<w>[^;]+);")


def tgz_name(p: dict) -> str:
    return p["package"].lstrip("@").replace("/", "-") + f"-{p['version']}.tgz"


def integrity(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()


def fetch(dest: Path) -> None:
    specs = [f"{p['package']}@{p['version']}" for p in PACKAGES]
    npm = shutil.which("npm") or sys.exit("npm is needed to fetch the packages (or pass --from DIR)")
    subprocess.run([npm, "pack", *specs, "--pack-destination", str(dest)], check=True, cwd=dest,
                   stdout=subprocess.DEVNULL)


def members(tgz: Path) -> dict[str, bytes]:
    """The regular files of a package, by their path under package/; nothing is extracted to disk."""
    out = {}
    with tarfile.open(tgz, "r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile() and m.name.startswith("package/") and ".." not in m.name.split("/"):
                out[m.name[len("package/"):]] = tf.extractfile(m).read()
    return out


def faces(css: str):
    for m in FACE.finditer(css):
        body = m.group("body")
        u, r, w = URL.search(body), RANGE.search(body), WEIGHT.search(body)
        if u and r and w and "font-style: normal" in body:
            yield u.group("file"), r.group("r").strip(), w.group("w").strip()


def build(src: Path) -> list[str]:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rules = []
    notes = []
    for p in PACKAGES:
        tgz = src / tgz_name(p)
        data = tgz.read_bytes()
        if integrity(data) != p["integrity"]:
            sys.exit(f"{tgz.name}: SHA-512 differs from the pinned one; nothing written")
        files = members(tgz)
        d = OUT / p["dir"]
        d.mkdir()
        (d / "OFL.txt").write_bytes(files["LICENSE"].replace(b"\r\n", b"\n"))
        if p.get("variable"):
            sheets = [files["index.css"].decode("utf-8")]
        else:
            # the stylesheet of a weight has every part with its unicode-range; keep the Latin ones
            sheets = [files[f"{w}.css"].decode("utf-8") for w in p["weights"]]
        keep = tuple(f"-{s}-{w}-normal.woff2" for s in SUBSETS for w in p.get("weights") or [])
        n = 0
        for css in sheets:
            for file, urange, weight in faces(css):
                if keep and not file.endswith(keep):
                    continue
                (d / file).write_bytes(files[f"files/{file}"])
                fmt = "woff2-variations" if p.get("variable") else "woff2"
                rules.append(f"@font-face{{font-family:\"{p['family']}\";font-style:normal;font-weight:{weight};"
                             f"font-display:swap;src:url(./{p['dir']}/{file}) format(\"{fmt}\");unicode-range:{urange}}}")
                n += 1
        notes.append(f"   {p['family']}: {p['package']}@{p['version']} ({p['integrity'][:22]}…), {n} files")
    head = ("/* The fonts of Gazettoa, shipped with the site (none is fetched from elsewhere).\n"
            "   Written by scripts/fonts.py from these npm packages of Fontsource; licences in each folder\n"
            "   (SIL Open Font License 1.1):\n" + "\n".join(notes) + " */\n")
    (OUT / "fonts.css").write_bytes((head + "\n".join(rules) + "\n").encode("utf-8"))
    return notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="src", type=Path, help="a folder that already holds the .tgz files")
    a = ap.parse_args(argv)
    if a.src:
        notes = build(a.src)
    else:
        with tempfile.TemporaryDirectory() as t:
            fetch(Path(t))
            notes = build(Path(t))
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print("\n".join(n.strip() for n in notes))
    print(f"fonts: {OUT} ({size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
