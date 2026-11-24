"""Reading the index that `toa index` writes, format 2.

The format is the reference tool's own (`toa-repo/doc/index-format.md` in the toa repository). It
is versioned; a version this reader does not know stops the build. Nothing here reads a library,
a manifest in YAML, or computes a hash: that is `toa`'s.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 2


class IndexError_(RuntimeError):
    pass


def _read_json(path: Path):
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, ValueError) as e:
        raise IndexError_(f"cannot read {path}: {e}") from e


@dataclass
class Index:
    root: Path
    meta: dict
    libraries: list[dict]                 # in the order of the workspace list
    objects: dict[str, dict]              # name -> the object's file
    problems: list[dict] = field(default_factory=list)

    def library(self, key: str) -> dict | None:
        for lib in self.libraries:
            if lib["key"] == key:
                return lib
        return None

    def get(self, name: str | None) -> dict | None:
        return self.objects.get(name) if name else None


def shard_of(name: str) -> str:
    """`<hh>`, the first two hex digits after the underscore, as the index and the site shard by."""
    _, _, h = name.partition("_")
    return h[:2] if len(h) >= 2 else "__"


def read(root: Path) -> Index:
    head = root / "index.json"
    if not head.is_file():
        raise IndexError_(f"no index.json in {root}; run `toa index` first")
    meta = _read_json(head)
    version = meta.get("toa-index")
    if version != FORMAT:
        raise IndexError_(f"{head}: index format {version!r}; this builder reads format {FORMAT}")
    libraries = []
    for summary in meta.get("libraries") or []:
        key = summary["key"]
        rec_path = root / "libraries" / (key + ".json")
        rec = _read_json(rec_path) if rec_path.is_file() else {}
        libraries.append({**summary, **rec})
    objects: dict[str, dict] = {}
    obj_dir = root / "objects"
    if obj_dir.is_dir():
        for f in sorted(obj_dir.glob("*/*.json")):
            o = _read_json(f)
            if o.get("toa-index") != FORMAT:
                raise IndexError_(f"{f}: index format {o.get('toa-index')!r}; expected {FORMAT}")
            objects[o["name"]] = o
    problems = []
    pj = root / "problems.jsonl"
    if pj.is_file():
        for line in pj.read_bytes().decode("utf-8").splitlines():
            if line.strip():
                problems.append(json.loads(line))
    return Index(root=root, meta=meta, libraries=libraries, objects=objects, problems=problems)
