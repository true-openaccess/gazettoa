"""List the texts of Gazettoa's interface and check each language's catalog against them.

    python gaze/scripts/i18n_keys.py            report, per language: missing, untranslated, unused
    python gaze/scripts/i18n_keys.py --write    add missing texts to each catalog as null

The texts are the t("English") calls in web/assets/*.js, plus the labels passed to t() through
the tables TYPE_NAMES, TYPE_PLURAL, IFC_TABS and NAV, and the labels of the fixed columns of the
selection table (builder/gaze/selection.py). A catalog, i18n/<code>/web.json, is keyed by
the English text with its runs of white space as one space; null is a text not translated yet,
shown in English. As in toa's i18n, a missing translation is reported and never fails a build.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GAZE = Path(__file__).resolve().parent.parent
CALL = re.compile(r'\bt\("((?:[^"\\]|\\.)*)"')
TABLE = re.compile(r"(?:TYPE_NAMES|TYPE_PLURAL)\s*=\s*\{([^}]*)\}|(?:IFC_TABS|NAV)\s*=\s*\[(.*?)\];", re.S)
LABEL = re.compile(r'"([A-Z][^"]*)"')
COLUMN_LABEL = re.compile(r'"label":\s*"([^"]+)"')


def keys() -> list[str]:
    out: list[str] = []
    for f in sorted((GAZE / "web" / "assets").glob("*.js")):
        s = f.read_text(encoding="utf-8")
        for m in CALL.finditer(s):
            k = re.sub(r"\s+", " ", json.loads('"' + m.group(1) + '"'))
            if k not in out:
                out.append(k)
        for m in TABLE.finditer(s):
            for lm in LABEL.finditer(m.group(1) or m.group(2) or ""):
                if lm.group(1) not in out:
                    out.append(lm.group(1))
    # the labels of the fixed columns of the selection table, which the builder writes
    for m in COLUMN_LABEL.finditer((GAZE / "builder" / "gaze" / "selection.py").read_text(encoding="utf-8")):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def main(argv: list[str]) -> int:
    ks = keys()
    langs = json.loads((GAZE / "i18n" / "languages.json").read_text(encoding="utf-8"))["languages"]
    for lang in langs:
        if lang["code"] == "en":
            continue
        path = GAZE / "i18n" / lang["code"] / "web.json"
        cat = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        missing = [k for k in ks if k not in cat]
        todo = [k for k in ks if k in cat and cat[k] is None]
        unused = [k for k in cat if k not in ks]
        done = len(ks) - len(missing) - len(todo)
        print(f"{lang['code']}: {done}/{len(ks)} translated, {len(missing)} missing, {len(todo)} null, {len(unused)} unused")
        for k in missing:
            print(f"  missing: {k}")
        for k in unused:
            print(f"  unused: {k}")
        if "--write" in argv and missing:
            for k in missing:
                cat[k] = None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((json.dumps(cat, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
