"""The symbol of each interface, as an SVG for the symbol wall and the interface's page.

An interface should have `symbol.rnl`, a package of RNL 0.4 that draws its block (type ifc). When
it has one and the `rnl` command is at hand, the build draws it: a netlist of one instance of the
block and a net on each pin, solved and rendered by `rnl`, so the pins carry their names. The
package says how it is applied in one of two ways, and both are followed:

- a rule that applies a symbol to the instances of one subcircuit
  (`@SELECT-INSTANCE(model="…") => @SET-SYMBOL(terminals=[…]) $SYMBOL`), the symbol its own or a
  standard one: the instance is an instance of that subcircuit, with a node on each port of the
  interface (a bus of width N is N ports, TOA types/ifc), and the rule gives it the symbol and maps
  its ports;
- without such a rule, a symbol it defines (`@DEFINE-SYMBOL`): the instance is given that symbol,
  its terminals in the order the symbol has them, each once (a pin drawn twice is one terminal).

The netlist uses the standard packages as well, whose fills put the name of each net beside its
pin. Those fills need pins with a direction; a symbol whose pins have none (as exported from
Virtuoso, with the names of the pins drawn in the symbol) is drawn again with the package alone.
Otherwise, or when drawing fails, the build draws a plain box from the pins of the interface:
inputs on the left, outputs and the rest on the right, supplies on top, grounds below.

Objects never change, so a drawing an earlier build made is used again.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .fields import IFC, PIN

TIMEOUT = 60
MAX_SVG = 512 * 1024
_NODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_BACKDROP = re.compile(r'<rect class="backdrop"[^>]*/>\s*')
# a rule of the package that applies a symbol to the instances of one subcircuit
_SELECT_MODEL = re.compile(r'@SELECT-INSTANCE\s*\(\s*model\s*=\s*"([^"\\]+)"')


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def pin_list(manifest: dict) -> list[dict]:
    out = []
    for p in manifest.get(IFC.PINS) or []:
        if isinstance(p, dict) and isinstance(p.get(PIN.NAME), str):
            w = p.get(PIN.WIDTH)
            out.append({"name": p[PIN.NAME], "kind": p.get(PIN.KIND), "direction": p.get(PIN.DIRECTION),
                        "width": w if isinstance(w, int) and not isinstance(w, bool) and w >= 1 else 1})
    return out


def box_svg(name: str, pins: list[dict]) -> str:
    """A plain box with the pins of the definition, for a definition without a drawn symbol."""
    left = [p for p in pins if p["direction"] == "in" and p["kind"] not in ("supply", "ground")]
    top = [p for p in pins if p["kind"] == "supply"]
    bottom = [p for p in pins if p["kind"] == "ground"]
    right = [p for p in pins if p not in left and p not in top and p not in bottom]
    step, lead, ch = 22, 18, 7.2
    side_n = max(len(left), len(right), 1)
    label_w = max([len(p["name"]) for p in left] + [0]) * ch + max([len(p["name"]) for p in right] + [0]) * ch
    across_n = max(len(top), len(bottom), 1)
    w = max(110.0, label_w + len(name) * 7.6 + 36, across_n * 40 + 20)
    h = max(60.0, side_n * step + 18, (60.0 if (top or bottom) else 0))
    x0, y0 = lead + 8, lead + 8
    W, H = w + 2 * lead + 16, h + 2 * lead + 16
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}" '
             f'font-family="IBM Plex Sans, Noto Sans SC, sans-serif" font-size="12">',
             f'<rect x="{x0}" y="{y0}" width="{w:.0f}" height="{h:.0f}" fill="none" stroke="#1d1d1f" stroke-width="1.6"/>',
             f'<text x="{x0 + w / 2:.1f}" y="{y0 + h / 2 + 4:.1f}" text-anchor="middle" font-weight="600" fill="#1d1d1f">{_esc(name)}</text>']

    def col(pins_, x_line, x_text, anchor):
        top_y = y0 + (h - (len(pins_) - 1) * step) / 2
        for i, p in enumerate(pins_):
            y = top_y + i * step
            parts.append(f'<line x1="{x_line[0]:.1f}" y1="{y:.1f}" x2="{x_line[1]:.1f}" y2="{y:.1f}" stroke="#1d1d1f" stroke-width="1.6"/>')
            parts.append(f'<text x="{x_text:.1f}" y="{y + 4:.1f}" text-anchor="{anchor}" fill="#1d1d1f">{_esc(p["name"])}</text>')

    def row(pins_, y_line, y_text):
        left_x = x0 + (w - (len(pins_) - 1) * 40) / 2
        for i, p in enumerate(pins_):
            x = left_x + i * 40
            parts.append(f'<line x1="{x:.1f}" y1="{y_line[0]:.1f}" x2="{x:.1f}" y2="{y_line[1]:.1f}" stroke="#1d1d1f" stroke-width="1.6"/>')
            parts.append(f'<text x="{x:.1f}" y="{y_text:.1f}" text-anchor="middle" fill="#1d1d1f">{_esc(p["name"])}</text>')

    col(left, (x0 - lead, x0), x0 + 6, "start")
    col(right, (x0 + w, x0 + w + lead), x0 + w - 6, "end")
    row(top, (y0 - lead, y0), y0 + 15)
    row(bottom, (y0 + h, y0 + h + lead), y0 + h - 7)
    parts.append("</svg>")
    return "".join(parts) + "\n"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          timeout=TIMEOUT, encoding="utf-8", errors="replace")


def render_rnl(rnl: str, text: bytes, name: str, pins: list[dict]) -> tuple[str | None, str]:
    """Draw the symbol a `symbol.rnl` defines with `rnl`: (svg, "") or (None, why not)."""
    with tempfile.TemporaryDirectory(prefix="gaze-sym-") as tmp:
        d = Path(tmp)
        pkg = d / "pkg"
        pkg.mkdir()
        (pkg / IFC.SYMBOL_FILE).write_bytes(text)
        try:
            r = _run([rnl, "catalog", "--package-dir", str(pkg)], d)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"rnl catalog: {e}"
        if r.returncode != 0:
            return None, f"rnl catalog: {r.stderr.strip()[:300]}"
        try:
            cat = json.loads(r.stdout)
        except ValueError:
            return None, "rnl catalog: not JSON"
        package = next((p for p in cat.get("packages") or [] if p.get("file") == IFC.SYMBOL_FILE), None)
        if not package:
            return None, "symbol.rnl is not a package"
        symbols = [s for s in cat.get("symbols") or [] if s.get("file") == IFC.SYMBOL_FILE]
        models = sorted(set(_SELECT_MODEL.findall(text.decode("utf-8", "replace"))))
        q = lambda s: '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'
        if len(models) == 1:
            # the package's rule for the instances of one subcircuit: an instance of it, a node on each port
            model = models[0]
            ports = [p["name"] if p.get("width", 1) == 1 else f"{p['name']}_{i + 1}" for p in pins for i in range(p.get("width", 1))]
            if not ports:
                return None, "the interface has no pins"
            nodes = [t if _NODE.match(t) else f"n{i + 1}" for i, t in enumerate(ports)]
            body = ""
        elif symbols:
            # a symbol of its own: set it on an instance of no subcircuit in particular
            want = {p["name"].lower() for p in pins}
            sym = next((s for s in symbols if {str(t.get("terminal", "")).lower() for t in s.get("pins") or []} == want), symbols[0])
            terminals = list(dict.fromkeys(str(t.get("terminal", "")) for t in sym.get("pins") or []))
            if not terminals:
                return None, f"{sym.get('symbol')} has no pins"
            nodes = [t if _NODE.match(t) else f"n{i + 1}" for i, t in enumerate(terminals)]
            model = "gaze_symbol"
            body = f"#X1 @SET-SYMBOL(terminals=[{', '.join(q(t) for t in terminals)}]) {sym['symbol']}; "
        else:
            return None, "symbol.rnl defines no symbol, nor a rule for the instances of one subcircuit"
        if not re.match(r"^[A-Za-z_][^\s;*]*$", model):
            return None, f"cannot write an instance of {model!r}"
        use = f"@USE-PACKAGE(name={q(package['name'])}, version={q(package.get('version', ''))});"
        why = ""
        # first with the labels of the standard fills, then with the package alone
        for std in ('@USE-PACKAGE(name="rnl-std-all", version="0.4"); ', ""):
            netlist = (
                f"* the symbol of the interface {re.sub(r'[^A-Za-z0-9_.-]', '_', name)}\n"
                f'* @RNL(type="header") {{ @VERSION("0.4"); {std}{use}}}\n'
                f"X1 {' '.join(nodes)} {model}\n"
                f'* @RNL {{ {body}#X1 @PLACE(0, 0); #X1 @TEXT({q(name)}, key="name"); }}\n'
                ".end\n")
            (d / "symbol.sp").write_bytes(netlist.encode("utf-8"))
            for old in ("solved", "svg"):
                shutil.rmtree(d / old, ignore_errors=True)
            try:
                r = _run([rnl, "solve", "symbol.sp", "-o", "solved", "--package-dir", str(pkg)], d)
                if r.returncode != 0:
                    why = f"rnl solve: {(r.stderr or r.stdout).strip()[:300]}"
                    continue
                r = _run([rnl, "render", str(Path("solved") / "symbol.sp"), "-o", "svg", "--package-dir", str(pkg)], d)
                if r.returncode != 0:
                    why = f"rnl render: {(r.stderr or r.stdout).strip()[:300]}"
                    continue
            except (OSError, subprocess.TimeoutExpired) as e:
                return None, f"rnl: {e}"
            why = ""
            break
        if why:
            return None, why
        out = d / "svg" / "symbol.svg"
        if not out.is_file():
            return None, "rnl render wrote no drawing"
        svg = out.read_bytes().decode("utf-8", "replace")
        if not svg.lstrip().startswith("<svg") or len(svg) > MAX_SVG or "nothing is drawn" in svg:
            return None, "rnl drew nothing"
        return _BACKDROP.sub("", svg, count=1), ""


def find_rnl(given: str | None) -> str | None:
    return given or shutil.which("rnl")
