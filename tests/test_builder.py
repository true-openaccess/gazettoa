"""Tests of the builder. Run from gaze/: python -m unittest discover -s tests

tests/data/examples-index/ is what `toa index` (toa 0.1.0, index format 2) wrote for the small
examples of toa (toa/examples/ in the toa repository, with the names of B32 and B33):
scripts/examples.py builds the example repositories in .work/examples/repos, then
`toa index --workspace .work/examples/repos/workspace.source.jsonl --out tests/data/examples-index --offline`.

tests/data/pll-subset/ is six objects of the PLL test library (CC0-1.0) and their index, made by
`python scripts/pll_subset.py --pll <a checkout of the PLL library>`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

GAZE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GAZE / "builder"))

from gaze import config, repro  # noqa: E402
from gaze import selection as selmod  # noqa: E402
from gaze import symbols as symmod  # noqa: E402
from gaze.build import build  # noqa: E402
from gaze.index import Index, IndexError_, read  # noqa: E402
from gaze.views import Model  # noqa: E402

DATA = GAZE / "tests" / "data" / "examples-index"

IFC_SA = "ifc_12ad57c51e8f36cac47a4b8a53f2949315f190f5"
IFC_DL = "ifc_4915f191ad95b57dd34a628ab49030a457d91398"
CKT_WRAP1 = "ckt_e9ae6546152d10f5ef21958edfa91b1e7c4faab7"
CKT_WRAP2 = "ckt_50231b67183e5ba6c367288e24e9a3c38756e3e8"
CKT_RAZAVI = "ckt_876f99c0ddb9fae4aabf6b8b3b7fd59de24e7e2b"
CKT_LOWKICK = "ckt_ddeacf24a1ad98201f1e46b00ddcabd3e47da576"
CKT_LEE1 = "ckt_3c536534c19f4fd08f986bf49cac879d98f62da4"
CKT_LEE2 = "ckt_4fc19b9fa24339682172aa51ef465bdaff46fe34"
TB = "tb_da7445c069776f4e59f7a9c0ca974ed421b4205e"
EVD = "evd_67a30a965e94ff7d0fe8f1472b1ee51d54b09a85"
DOC = "doc_907ce675ba8c9de5c17d38c1af20c9d2f5b4f071"
LIB_OFFICIAL = "lib_cf125e93948ecdee725718e666cf7aa1be126799"


def load(path: Path):
    return json.loads(path.read_bytes().decode("utf-8"))


def obj_file(site: Path, name: str) -> Path:
    return site / "data" / "obj" / name.split("_")[1][:2] / f"{name}.json"


class YamlSubset(unittest.TestCase):
    def test_reads_mappings_scalars_and_comments(self):
        d = config.parse_yaml_subset(
            "schema: gaze/instance/1   # the format\n"
            "title: \"A # in quotes\"\n"
            "count: 3\nratio: 0.5\non: true\nnothing: ~\n"
            "hosts:\n  git.example.org:\n    raw: 'https://git.example.org/{repo}/raw/{commit}/{path}'\n"
            "libraries:\n  lee: {raw: copy}\n")
        self.assertEqual(d["schema"], "gaze/instance/1")
        self.assertEqual(d["title"], "A # in quotes")
        self.assertEqual((d["count"], d["ratio"], d["on"], d["nothing"]), (3, 0.5, True, None))
        self.assertEqual(d["hosts"]["git.example.org"]["raw"], "https://git.example.org/{repo}/raw/{commit}/{path}")
        self.assertEqual(d["libraries"], {"lee": {"raw": "copy"}})

    def test_refuses_what_it_does_not_read(self):
        for text in ("a:\n  - x\n", "a:\n\tb: 1\n", "a: [1, 2]\n", "a: 1\na: 2\n", "just text\n"):
            with self.subTest(text=text), self.assertRaises(config.ConfigError):
                config.parse_yaml_subset(text)


class Config(unittest.TestCase):
    def test_site_url_from_actions_in_a_fork(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": "someone/gazettoa", "GITHUB_SERVER_URL": "https://github.com"}):
            cfg = config.load(Path(d))
        self.assertEqual(cfg.site_url, "https://someone.github.io/gazettoa/")
        self.assertEqual(cfg.repository, "https://github.com/someone/gazettoa")

    def test_gaze_yaml_overrides_and_checks(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "gaze.yaml").write_bytes(b"title: Ours\nsite_url: https://x.example/g\nlibraries:\n  lee: {raw: copy}\n")
            with mock.patch.dict(os.environ, {}, clear=True):
                cfg = config.load(Path(d))
            self.assertEqual((cfg.title, cfg.site_url, cfg.library_raw_mode("lee"), cfg.library_raw_mode("x")), ("Ours", "https://x.example/g/", "copy", "url"))
            (Path(d) / "gaze.yaml").write_bytes(b"titel: typo\n")
            with self.assertRaises(config.ConfigError):
                config.load(Path(d))

    def test_toa_site_is_an_address_on_the_web(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(config.load(Path(d)).toa_site, "")   # left out: no link on the home page
            (Path(d) / "gaze.yaml").write_bytes(b"toa_site: https://x.example/toa/\n")
            self.assertEqual(config.load(Path(d)).toa_site, "https://x.example/toa/")
            for bad in (b"toa_site: javascript:alert(1)\n", b"toa_site: x.example/toa\n", b"toa_site: 3\n"):
                (Path(d) / "gaze.yaml").write_bytes(bad)
                with self.subTest(text=bad), self.assertRaises(config.ConfigError):
                    config.load(Path(d))

    def test_addresses(self):
        self.assertEqual(config.split_address("https://github.com/a/b.git"), ("github.com", "a/b"))
        self.assertEqual(config.split_address("git@github.com:a/b.git"), ("github.com", "a/b"))
        self.assertEqual(config.split_address("ssh://git@gitlab.com/g/s/p"), ("gitlab.com", "g/s/p"))
        self.assertIsNone(config.split_address("file:///tmp/x"))
        raw, web = config.library_templates(config.Config(), "https://github.com/a/b")
        self.assertEqual(config.fill(raw, "", "c0ffee", "ckt/x/ckt_1"), "https://raw.githubusercontent.com/a/b/c0ffee/ckt/x/ckt_1")
        self.assertIsNone(config.library_templates(config.Config(), "https://example.org/a/b.git"))

    def test_no_organisation_is_written_into_the_code(self):
        # the official instance's name lives only in its configuration, never in the code a fork runs
        files = [*(GAZE / "builder").rglob("*.py"), *(GAZE / "web").rglob("*.js"), GAZE / "web" / "index.html"]
        for f in files:
            with self.subTest(file=f.name):
                # the organisation is lower case; the standard's own name, True-OpenAccess, may appear in text
                self.assertNotIn("true-openaccess", f.read_text(encoding="utf-8"))


class IndexReading(unittest.TestCase):
    def test_reads_format_2(self):
        idx = read(DATA)
        self.assertEqual([lib["key"] for lib in idx.libraries], ["official", "lee", "alice", "official-chen"])
        self.assertEqual(len(idx.objects), 12)
        self.assertFalse(idx.objects[CKT_LEE1]["present"])

    def test_stops_on_another_version(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(DATA, Path(d) / "i")
            head = load(Path(d) / "i" / "index.json")
            head["toa-index"] = 1
            (Path(d) / "i" / "index.json").write_bytes(json.dumps(head).encode())
            with self.assertRaises(IndexError_):
                read(Path(d) / "i")


class Names(unittest.TestCase):
    def setUp(self):
        self.m = Model(read(DATA), config.Config())

    def test_readable_names_follow_the_type_specifications(self):
        d = self.m.display
        self.assertEqual(d(IFC_SA), "strongarm-comp")
        self.assertEqual(d(CKT_WRAP1), "strongarm-comp/wrap-lee.g1")          # from fields: no base, generation 1
        self.assertEqual(d(CKT_WRAP2), "strongarm-comp/wrap-lee.g2")          # the generation its history.json gives
        self.assertEqual(d(TB), "strongarm-comp/tb_offset.g1")
        self.assertEqual(d(EVD), "strongarm-comp/20261110T1200Z-wrap-off")   # the label of its line
        self.assertEqual(d(DOC), "strongarm-comp/kickback")
        self.assertEqual(d(CKT_LEE1), "dyn-latch-cmp/lee-sky130.g1")         # the label in its removal record
        self.assertEqual(d("ckt_" + "0" * 40), "ckt_00000000…")             # unknown: the first 12 characters
        self.assertEqual(d(CKT_LOWKICK), "strongarm-comp/sky130-lowkick.g1")  # made from razavi, but a series of its own

    def test_the_generation_is_the_one_history_json_gives(self):
        # TOA 3.4: sealing writes it; it is never counted from the history again
        idx = read(DATA)
        idx.get(CKT_WRAP2)["history"]["generation"] = 5
        self.assertEqual(Model(idx, config.Config()).display(CKT_WRAP2), "strongarm-comp/wrap-lee.g5")
        del idx.get(CKT_WRAP2)["history"]["generation"]
        m = Model(idx, config.Config())
        self.assertEqual(m.display(CKT_WRAP2), "strongarm-comp/wrap-lee")   # an index without it: no generation shown
        self.assertIsNone(m.card(CKT_WRAP2)["generation"])
        self.assertEqual(m.card(CKT_WRAP1)["generation"], 1)               # no base: 1

    def test_ifc_of_a_record_is_the_ifc_of_its_dut(self):
        self.assertEqual(self.m.ifc_of(EVD), IFC_SA)
        self.assertEqual(self.m.ifc_of(CKT_WRAP1), IFC_SA)

    def test_the_title_comes_from_the_index(self):
        # toa index writes `title`: the manifest's, or for a document without one its README's first heading
        self.assertEqual(self.m.index.get(DOC)["title"], "Less kickback in a StrongARM comparator")
        idx = read(DATA)
        doc = idx.get(DOC)
        del doc["manifest"]["title"]
        doc["title"] = "From the first heading"
        for loc in doc["locations"]:
            loc["label"] = None
        m = Model(idx, config.Config())
        self.assertEqual(m.view(DOC, {}, {})["title"], "From the first heading")
        self.assertEqual(m.card(DOC)["summary"], "From the first heading")
        self.assertEqual(m.display(DOC), "From the first heading")      # no label: the title
        del doc["title"]
        self.assertEqual(Model(idx, config.Config()).display(DOC), DOC[:12])   # neither: the first 12 characters

    def test_a_document_belongs_to_the_first_interface_of_its_refs(self):
        self.assertEqual(self.m.ifc_of(DOC), IFC_SA)
        self.assertEqual(self.m.members(IFC_SA)["doc"], [DOC])
        self.assertEqual(self.m.members(IFC_DL)["doc"], [])

    def test_series_and_generation_order_the_circuits(self):
        ckts = self.m.members(IFC_SA)["ckt"]
        self.assertEqual([self.m.display(n) for n in ckts],
                         ["strongarm-comp/sky130-lowkick.g1", "strongarm-comp/sky130-razavi.g1",   # by series, then generation
                          "strongarm-comp/wrap-lee.g1", "strongarm-comp/wrap-lee.g2"])
        self.assertEqual([self.m.series(n) for n in ckts], [CKT_LOWKICK, CKT_RAZAVI, CKT_WRAP1, CKT_WRAP1])
        self.assertEqual(self.m.card(CKT_WRAP2)["generation"], 2)
        self.assertIsNone(self.m.card(CKT_LEE1)["generation"])   # removed: not read

    def test_type_names_live_in_one_table(self):
        # B32 renamed the types; a later rename changes fields.TYPES and nothing else
        from gaze import fields, views
        self.assertEqual(views.prefix_of(CKT_WRAP1), "ckt")
        self.assertEqual(set(fields.TYPES), {"ifc", "ckt", "tb", "evd", "doc", "lib"})
        self.assertEqual(views.prefix_of("xyz_" + "1" * 40), "xyz")       # an unknown type keeps its prefix
        with mock.patch.dict(fields._KIND_OF, {"circ": "ckt"}):
            self.assertEqual(views.prefix_of("circ_" + "1" * 40), "ckt")
        code = "".join(f.read_text(encoding="utf-8") for f in (GAZE / "builder" / "gaze").glob("*.py") if f.name != "fields.py")
        self.assertNotRegex(code, r'(?:startswith|split)\(\s*"(?:ifc|ckt|tb|evd|doc|lib)_')


def marked(idx, name: str, library: str) -> None:
    """Mark an object latest in a library, as a line of its library list does (TOA 5.2)."""
    hit = [loc for loc in idx.get(name)["locations"] if loc["library"] == library]
    assert hit, (name, library)
    for loc in hit:
        loc["latest"] = True


class LatestMarks(unittest.TestCase):
    """Which generation to use is a library's word (TOA 5.2, 7.5); Gazettoa shows every library's.
    In the examples alice marks wrap-lee.g2, official and official-chen mark sky130-razavi.g1, and
    official-chen marks sky130-lowkick.g1, which was made from it under a name of its own."""

    def test_newer_versions_are_the_index_s(self):
        m = Model(read(DATA), config.Config())
        self.assertEqual(m.card(CKT_WRAP2)["latest"], ["alice"])
        self.assertEqual(m.newer(CKT_WRAP1), [{"name": CKT_WRAP2, "libraries": ["alice"], "together": ["alice"], "ifc_changed": False}])
        self.assertEqual(m.card(CKT_WRAP1)["newer"], [CKT_WRAP2])
        v = m.view(CKT_WRAP2, {}, {})
        self.assertEqual(v["latest"], ["alice"])
        self.assertTrue(v["locations"][0]["latest"])
        self.assertEqual(m.newer(CKT_WRAP2), [])

    def test_a_port_is_not_a_newer_version(self):
        # sky130-lowkick is marked and holds sky130-razavi in its history, but it is another series
        m = Model(read(DATA), config.Config())
        self.assertEqual(m.card(CKT_LOWKICK)["latest"], ["official-chen"])
        self.assertEqual(m.newer(CKT_RAZAVI), [])

    def test_a_newer_version_of_another_interface_says_so(self):
        idx = read(DATA)
        idx.get(CKT_WRAP1)["newer"][0]["ifc_changed"] = True
        self.assertTrue(Model(idx, config.Config()).newer(CKT_WRAP1)[0]["ifc_changed"])

    def test_series_show_the_marked_generations_and_fold_the_rest(self):
        idx = read(DATA)
        ckts = Model(idx, config.Config()).members(IFC_SA)["ckt"]
        series = lambda: {s["series"]: s for s in Model(idx, config.Config()).series_groups(ckts)}
        by = series()
        self.assertEqual(len(by), 3)
        s = by[CKT_WRAP1]
        self.assertEqual((s["heads"], s["rest"], s["marked"]), ([CKT_WRAP2], [CKT_WRAP1], True))
        for loc in idx.get(CKT_WRAP2)["locations"]:
            loc["latest"] = False
        s = series()[CKT_WRAP1]
        self.assertEqual((s["heads"], s["rest"], s["marked"]), ([CKT_WRAP2], [CKT_WRAP1], False))  # no mark: the newest
        marked(idx, CKT_WRAP1, "alice")
        s = series()[CKT_WRAP1]
        self.assertEqual((s["heads"], s["rest"], s["marked"]), ([CKT_WRAP1], [CKT_WRAP2], True))  # a library may keep the older one
        # another library says otherwise: both words are shown
        idx.get(CKT_WRAP2)["locations"].append({**idx.get(CKT_WRAP2)["locations"][0], "library": "official", "latest": True})
        s = series()[CKT_WRAP1]
        self.assertEqual((s["heads"], s["rest"]), ([CKT_WRAP1, CKT_WRAP2], []))


def synthetic(records: list[tuple[str, str, float | None]], tol=None) -> Index:
    """An index with one circuit, one testbench and evidence records (name, first library, value)."""
    libs = [{"key": k, "address": f"https://github.com/x/{k}", "commit": "c" * 40, "readable": True} for k in ("a", "b", "c")]
    dut, tb = "ckt_" + "1" * 40, "tb_" + "2" * 40
    md = {"id": "m", "unit": "V", "better": "lower"}
    if tol is not None:
        md["tolerance"] = tol
    objects = {
        dut: {"name": dut, "prefix": "ckt", "present": True, "valid": True, "manifest": {"type": "ckt", "ifc": "ifc_" + "3" * 40}},
        tb: {"name": tb, "prefix": "tb", "present": True, "valid": True, "manifest": {"type": "tb", "name": "tb_x", "metrics": [md]}},
    }
    for name, lib, val in records:
        objects[name] = {"name": name, "prefix": "evd", "present": True, "valid": True, "first": {"library": lib},
                         "locations": [{"library": lib, "path": "evd/x"}],
                         "manifest": {"type": "evd", "kind": "sim", "dut": dut, "tbs": [tb], "conditions": {"parameters": {"vdd": 1.8}},
                                      "metrics": {} if val is None else {"tb_x.m": val}}}
    return Index(root=Path("."), meta={}, libraries=libs, objects=objects)


R1, R2, R3 = "evd_" + "a" * 40, "evd_" + "b" * 40, "evd_" + "c" * 40


class MultiParty(unittest.TestCase):
    def group(self, records, tol={"abs": 0.2}):
        gs = repro.build_groups(synthetic(records, tol))
        self.assertEqual(len(gs), 1)
        return gs[0]

    def test_two_repositories_two_names_agreeing(self):
        g = self.group([(R1, "a", 1.0), (R2, "b", 1.1)])
        self.assertTrue(g["multi_party"])
        self.assertFalse(g["disagree"])
        self.assertEqual(len(g["sources"]), 2)
        self.assertTrue(g["metrics"][0]["agree"])

    def test_equality_is_within_tolerance(self):
        self.assertFalse(self.group([(R1, "a", 1.0), (R2, "b", 1.25)], {"abs": 0.25})["disagree"])

    def test_relative_tolerance_scales_with_the_median(self):
        self.assertFalse(self.group([(R1, "a", 100.0), (R2, "b", 102.0)], {"rel": 0.03})["disagree"])
        self.assertTrue(self.group([(R1, "a", 100.0), (R2, "b", 104.0)], {"rel": 0.03})["disagree"])

    def test_one_repository_is_not_multi_party_and_not_a_problem(self):
        g = self.group([(R1, "a", 1.0), (R2, "a", 1.0)])
        self.assertFalse(g["multi_party"])
        self.assertNotIn("problem", json.dumps(g))

    def test_disagree_is_a_state_of_its_own(self):
        # user 2026-11-23: a metric can be multi-party verified and disagree at once
        g = self.group([(R1, "a", 1.0), (R2, "b", 1.5)])
        self.assertTrue(g["multi_party"])
        self.assertTrue(g["disagree"])
        m = g["metrics"][0]
        self.assertTrue(m["multi_party"] and m["disagree"])
        self.assertFalse(m["agree"])
        self.assertNotIn("problem", json.dumps(g))

    def test_two_records_of_one_repository_can_disagree(self):
        g = self.group([(R1, "a", 1.0), (R2, "a", 1.5)])
        self.assertFalse(g["multi_party"])
        self.assertTrue(g["disagree"])

    def test_no_tolerance_is_not_judged(self):
        g = self.group([(R1, "a", 1.0), (R2, "b", 9.0)], tol=None)
        self.assertTrue(g["multi_party"])
        self.assertFalse(g["disagree"])
        self.assertIsNone(g["metrics"][0]["agree"])

    def test_a_record_carried_by_a_fork_counts_once(self):
        idx = synthetic([(R1, "a", 1.0)])
        idx.objects[R1]["locations"].append({"library": "b", "path": "evd/x"})   # the fork has the same record
        g = repro.build_groups(idx)[0]
        self.assertFalse(g["multi_party"])
        self.assertEqual(g["sources"], ["https://github.com/x/a"])

    def test_the_same_circuit_is_the_same_dut(self):
        # user 2026-11-23: no override; whatever else a record says, the group is its dut
        idx = synthetic([(R1, "a", 1.0), (R2, "b", 1.0)])
        idx.objects[R2]["manifest"]["override"] = {"x1": "ckt_" + "9" * 40}
        gs = repro.build_groups(idx)
        self.assertEqual(len(gs), 1)
        self.assertNotIn("override", gs[0])

    def test_different_conditions_are_different_groups(self):
        idx = synthetic([(R1, "a", 1.0), (R2, "b", 1.0)])
        idx.objects[R2]["manifest"]["conditions"] = {"parameters": {"vdd": 1.2}}
        gs = repro.build_groups(idx)
        self.assertEqual(len(gs), 2)
        self.assertFalse(any(g["multi_party"] for g in gs))

    def test_only_simulations_are_compared(self):
        # a kind of evidence Gazettoa does not know is kept and shown as it is (type evd)
        idx = synthetic([(R1, "a", 1.0), (R2, "b", 1.0)])
        idx.objects[R2]["manifest"]["kind"] = "silicon"
        gs = repro.build_groups(idx)
        self.assertEqual([g["records"] for g in gs], [[R1]])
        v = Model(idx, config.Config()).view(R2, {}, {})
        self.assertEqual((v["kind"], v["known_kind"]), ("silicon", False))

    def test_group_ids_are_stable(self):
        a = self.group([(R1, "a", 1.0), (R2, "b", 1.1)])["id"]
        b = self.group([(R2, "b", 1.1), (R1, "a", 1.0)])["id"]
        self.assertEqual(a, b)


class RecordLibrary(unittest.TestCase):
    """Which library a record counts for (the user's decision, 2026-11-23): where git shows it first."""

    def rec(self, *places):
        return {"name": R1, "locations": [{"library": k, "path": "evd/x", "first_commit": c, "first_date": d} for k, c, d in places]}

    def setUp(self):
        self.idx = synthetic([])

    def test_the_earliest_commit_wins(self):
        r = self.rec(("a", "1" * 40, "2026-11-10T00:00:00Z"), ("b", "2" * 40, "2026-11-01T09:00:00+08:00"))
        self.assertEqual(repro.record_library(self.idx, r), "b")

    def test_a_copy_counts_for_the_library_copied_from(self):
        r = self.rec(("b", "2" * 40, "2026-11-12T00:00:00Z"), ("a", "1" * 40, "2026-11-02T00:00:00Z"))
        self.assertEqual(repro.record_library(self.idx, r), "a")

    def test_a_shared_commit_goes_to_the_library_listed_first(self):
        # a fork shares the commit: git cannot tell which is the original
        r = self.rec(("c", "1" * 40, "2026-11-02T00:00:00Z"), ("a", "1" * 40, "2026-11-02T00:00:00Z"))
        self.assertEqual(repro.record_library(self.idx, r), "a")

    def test_a_fork_of_a_whole_library_makes_no_multi_party(self):
        idx = synthetic([(R1, "a", 1.0), (R2, "a", 1.0)])
        for n, c, d in ((R1, "1" * 40, "2026-11-02T00:00:00Z"), (R2, "2" * 40, "2026-11-03T00:00:00Z")):
            idx.objects[n]["locations"] = [{"library": k, "path": "evd/x", "first_commit": c, "first_date": d} for k in ("b", "a")]
        g = repro.build_groups(idx)[0]
        self.assertFalse(g["multi_party"])
        self.assertEqual(len(g["sources"]), 1)

    def test_without_dates_the_index_first(self):
        self.assertEqual(repro.record_library(self.idx, {"name": R1, "first": {"library": "c"}, "locations": [{"library": "a", "path": "x"}]}), "c")


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.instance = self.dir / "instance"
        self.instance.mkdir()
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("GITHUB_REPOSITORY", "GITHUB_SERVER_URL"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_examples(self):
        out = self.dir / "site"
        r = build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
        self.assertEqual((r["libraries"], r["ifcs"], r["groups"]), (4, 2, 1))
        site = load(out / "data" / "site.json")
        self.assertEqual(site["format"], "gaze-site/1")
        self.assertEqual(site["toa_site"], "")   # the instance of the tests names no site of TOA
        from gaze import fields
        self.assertEqual(site["types"], fields.TYPES)   # the page maps prefixes through this
        self.assertEqual(site["counts"]["objects"], 11)
        self.assertEqual([p["display"] for p in site["ifcs"]], ["dyn-latch-cmp", "strongarm-comp"])
        self.assertEqual([c["display"] for c in site["libs"]], ["official.g1"])   # the frozen library of the examples
        self.assertEqual((site["counts"]["ckt"], site["counts"]["evd"], site["counts"]["lib"]), (5, 1, 1))
        self.assertIn('http-equiv="Content-Security-Policy"', (out / "index.html").read_text(encoding="utf-8"))
        shard = load(out / "data" / "ifc" / IFC_SA[4:6] / f"{IFC_SA}.json")
        self.assertEqual(len(shard["ckts"]), 4)
        self.assertEqual(len(shard["tbs"]), 1)
        self.assertEqual(len(shard["docs"]), 1)
        self.assertEqual(len(shard["groups"]), 1)
        self.assertFalse(shard["groups"][0]["multi_party"])
        self.assertIn([CKT_RAZAVI, CKT_LOWKICK, "verified"], shard["lineage"]["edges"])
        self.assertEqual([c["display"] for c in shard["ckts"]][2:], ["strongarm-comp/wrap-lee.g1", "strongarm-comp/wrap-lee.g2"])
        self.assertEqual([(s["heads"], s["rest"]) for s in shard["series"]["ckt"]],
                         [([CKT_LOWKICK], []), ([CKT_RAZAVI], []), ([CKT_WRAP2], [CKT_WRAP1])])
        ver = load(obj_file(out, EVD))
        self.assertEqual([r["object"] for r in ver["lock_tree"]], [CKT_WRAP1, CKT_LEE2])
        self.assertEqual([r["ifc"] for r in ver["lock_tree"]], [IFC_SA, IFC_DL])
        self.assertEqual([c[0] for c in ver["conditions"]], ["parameters", "options", "models"])
        self.assertEqual((ver["kind"], ver["known_kind"]), ("sim", True))
        self.assertEqual(ver["simulator"]["name"], "spectre")
        self.assertEqual(ver["group"]["records"], [EVD])
        gone = load(obj_file(out, CKT_LEE1))
        self.assertFalse(gone["present"])
        self.assertEqual(gone["removals"][0]["reason"], "Superseded by lee-sky130.g2.")
        lee = load(out / "data" / "lib" / "lee.json")
        self.assertEqual([r["name"] for r in lee["removed_objects"]], [CKT_LEE1])
        alice = load(out / "data" / "lib" / "alice.json")
        self.assertTrue(all(i["in_instance"] for i in alice["includes"]))
        # the example libraries are on a made-up host: no address for their files, and nothing copied without toa
        self.assertIsNone(ver["raw"])
        self.assertFalse((out / "raw").exists())

    def test_files_on_a_known_host_are_fetched_at_the_commit_read(self):
        idx_dir = self.dir / "index"
        shutil.copytree(DATA, idx_dir)
        head = load(idx_dir / "index.json")
        for lib in head["libraries"]:
            lib["address"] = lib["address"].replace("https://example.org/toa-examples/", "https://github.com/someone/")
        (idx_dir / "index.json").write_bytes(json.dumps(head).encode())
        for f in (idx_dir / "libraries").glob("*.json"):
            rec = load(f)
            rec["address"] = rec["address"].replace("https://example.org/toa-examples/", "https://github.com/someone/")
            f.write_bytes(json.dumps(rec).encode())
        out = self.dir / "site"
        build(self.instance, idx_dir, out)
        ver = load(obj_file(out, EVD))
        commit = next(lib["commit"] for lib in head["libraries"] if lib["key"] == "alice")
        self.assertEqual(ver["raw"], f"https://raw.githubusercontent.com/someone/alice/{commit}/{ver['locations'][0]['path']}")
        self.assertIn("https://raw.githubusercontent.com", (out / "index.html").read_text(encoding="utf-8"))

    def test_an_object_that_leaves_a_library_is_noted_and_its_copy_dropped(self):
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
        # pretend the first build copied the files of the document
        (out / "raw" / DOC).mkdir(parents=True)
        (out / "raw" / DOC / "README.md").write_bytes(b"# x\n")
        # the next commit of official-chen no longer has the document
        idx_dir = self.dir / "index"
        shutil.copytree(DATA, idx_dir)
        lib = load(idx_dir / "libraries" / "official-chen.json")
        lib["objects"].remove(DOC)
        (idx_dir / "libraries" / "official-chen.json").write_bytes(json.dumps(lib).encode())
        doc = load(idx_dir / "objects" / DOC[4:6] / f"{DOC}.json")
        gone = {k: doc[k] for k in ("toa-index", "name", "prefix")}
        gone.update(present=False, history=None, removals=[], referenced_by=[], base_by=[])
        (idx_dir / "objects" / DOC[4:6] / f"{DOC}.json").write_bytes(json.dumps(gone).encode())
        r = build(self.instance, idx_dir, out, built="2026-11-24T00:00:00Z")
        self.assertEqual(r["changes"], 1)
        changes = load(out / "data" / "changes.json")
        self.assertEqual((changes[0]["name"], changes[0]["library"], changes[0]["seen"], changes[0]["record"]),
                         (DOC, "official-chen", "2026-11-24T00:00:00Z", False))
        self.assertEqual(load(obj_file(out, DOC))["changes"][0]["kind"], "left")
        self.assertFalse((out / "raw" / DOC).exists())
        # a third build keeps the note
        build(self.instance, idx_dir, out, built="2026-11-25T00:00:00Z")
        self.assertEqual(len(load(out / "data" / "changes.json")), 1)


LIB = "lib_" + "7" * 40
MEMBERS = (b'{"toa": "source/1"}\n'
           b'{"object": "' + IFC_SA.encode() + b'", "label": "strongarm-comp", "group": "strongarm-comp", "sources": [{"git": "https://example.org/a.git"}]}\n'
           b'{"object": "' + CKT_WRAP2.encode() + b'", "label": "strongarm-comp/wrap-lee.g2", "group": "strongarm-comp", "license": "MIT"}\n'
           b'{"object": "' + IFC_DL.encode() + b'", "label": "dyn-latch-cmp"}\n'
           b'not json\n')


def with_frozen_library(src: Path, dst: Path, files: Path) -> None:
    """A copy of the index with a frozen library in official, and its files in a checkout under `files`."""
    import hashlib
    shutil.copytree(src, dst)
    path = "lib/toa-examples.g1/" + LIB
    o = {"toa-index": 2, "name": LIB, "prefix": "lib", "present": True, "valid": True, "problems": [],
         "manifest": {"type": "lib", "license": "CC0-1.0", "name": "toa-examples", "title": "The examples, frozen"},
         "title": "The examples, frozen", "references": [], "history": {"listed": [], "generation": 1},
         "files": [{"path": "members.source.jsonl", "size": len(MEMBERS), "sha256": hashlib.sha256(MEMBERS).hexdigest()},
                   {"path": "toa.yaml", "size": 1, "sha256": "0" * 64}],
         "locations": [{"library": "official", "path": path, "first_commit": "1" * 40, "first_date": "2026-11-24T00:00:00Z",
                        "notes": [], "source_list": None, "label": None, "latest": True}],
         "first": {"library": "official", "date": "2026-11-24T00:00:00Z"}, "removals": [], "referenced_by": [], "base_by": []}
    (dst / "objects" / "77").mkdir(parents=True, exist_ok=True)
    (dst / "objects" / "77" / f"{LIB}.json").write_bytes(json.dumps(o).encode())
    lib = load(dst / "libraries" / "official.json")
    lib["objects"].append(LIB)
    (dst / "libraries" / "official.json").write_bytes(json.dumps(lib).encode())
    (files / "official" / path).mkdir(parents=True)
    (files / "official" / path / "members.source.jsonl").write_bytes(MEMBERS)


class FrozenLibraries(unittest.TestCase):
    """Type lib: a list of members frozen as an object (TOA 0.1, types/lib)."""

    def test_the_list_of_members_by_group(self):
        mb = Model(read(DATA), config.Config()).lib_members(MEMBERS)
        self.assertEqual((mb["read"], mb["count"], mb["shown"]), (True, 3, 3))
        self.assertEqual([(g["group"], [m["object"] for m in g["members"]]) for g in mb["groups"]],
                         [("strongarm-comp", [IFC_SA, CKT_WRAP2]), ("", [IFC_DL])])
        self.assertEqual(mb["groups"][0]["members"][0]["sources"], ["https://example.org/a.git"])
        self.assertEqual(mb["groups"][0]["members"][1]["license"], "MIT")
        self.assertFalse(Model(read(DATA), config.Config()).lib_members(None)["read"])

    def test_a_frozen_library_has_a_page(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "files").mkdir()
            with_frozen_library(DATA, d / "index", d / "files")
            out = d / "site"
            build(d, d / "index", out, built="2026-11-24T00:00:00Z", local_files=[d / "files"])
            v = load(obj_file(out, LIB))
            site = load(out / "data" / "site.json")
        self.assertEqual(v["display"], "toa-examples.g1")                 # <name>.g<generation>, no interface level
        self.assertEqual(v["latest"], ["official"])
        self.assertIsNone(v["ifc"])
        self.assertEqual([g["group"] for g in v["members"]["groups"]], ["strongarm-comp", ""])
        self.assertEqual(v["names"][CKT_WRAP2][0], "strongarm-comp/wrap-lee.g2")   # members are linked by readable name
        self.assertEqual([c["name"] for c in site["libs"]], [LIB_OFFICIAL, LIB])
        self.assertEqual(site["counts"]["lib"], 2)


COPY = "ckt_" + "c" * 40
RAZAVI_NETLIST = "strongarm_comp.scs"


SAME_RULE = {"min_size": 256, "common_groups": 5, "common_authors": 5, "common_cap": 200, "listed": 50}


def with_copy(src: Path, dst: Path, *, of: str = CKT_RAZAVI, author: str | None = "Mallory Example",
              base: list | None = None, date: str = "2026-11-30T00:00:00Z", extra: list | None = None,
              same: bool = False) -> None:
    """A copy of the index with a circuit in alice that holds the netlist of another circuit byte for byte.
    With `same`, the index says so as toa index writes it (`same_files`, 8.3)."""
    shutil.copytree(src, dst)
    orig = load(dst / "objects" / of[4:6] / f"{of}.json")
    net = next(f for f in orig["files"] if f["path"].endswith(".scs"))
    man = {"type": "ckt", "license": "CC0-1.0", "ifc": IFC_SA, "name": "copied", "form": "transistor"}
    if author is not None:
        man["author"] = author
    if base:
        man["base"] = base
    o = {"toa-index": 2, "name": COPY, "prefix": "ckt", "present": True, "valid": True, "problems": [],
         "manifest": man, "references": [{"name": IFC_SA, "at": "toa.yaml:ifc"}],
         "history": {"listed": list(base or []), "verified": list(base or []), "declared": [], "state": "verified" if base else "none",
                     "generation": 1},
         "files": [dict(net), {"path": "toa.yaml", "size": 99, "sha256": "e" * 64}, *(extra or [])],
         "locations": [{"library": "alice", "path": "ckt/strongarm-comp/copied.g1/" + COPY, "first_commit": "2" * 40,
                        "first_date": date, "notes": [], "source_list": None, "label": None}],
         "first": {"library": "alice", "commit": "2" * 40, "date": date}, "removals": [], "referenced_by": [], "base": list(base or []),
         "base_by": []}
    if same:
        o["same_files"] = {"earlier": [{"object": of, "author": (orig["manifest"] or {}).get("author"), "basis": "dates",
                                        "files": [[net["path"], net["path"]]]}], "later": [], "common": []}
        orig["same_files"] = {"earlier": [], "later": [{"object": COPY, "author": author, "files": [[net["path"], net["path"]]]}],
                              "common": ["models.inc"]}
        (dst / "objects" / of[4:6] / f"{of}.json").write_bytes(json.dumps(orig).encode())
        meta = load(dst / "index.json")
        meta["same_files"] = SAME_RULE
        (dst / "index.json").write_bytes(json.dumps(meta).encode())
    (dst / "objects" / "cc").mkdir(parents=True, exist_ok=True)
    (dst / "objects" / "cc" / f"{COPY}.json").write_bytes(json.dumps(o).encode())
    lib = load(dst / "libraries" / "alice.json")
    lib["objects"].append(COPY)
    (dst / "libraries" / "alice.json").write_bytes(json.dumps(lib).encode())


class Authorship(unittest.TestCase):
    """Evidence of authorship and time (decision B35): first seen, Software Heritage, same files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.instance = self.dir / "instance"
        self.instance.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def built(self, built="2026-12-01T00:00:00Z", **kw):
        idx = self.dir / "index"
        if idx.exists():
            shutil.rmtree(idx)
        with_copy(DATA, idx, **kw)
        out = self.dir / "site"
        build(self.instance, idx, out, built=built)
        return out

    def test_the_index_marks_a_copy_without_base(self):
        out = self.built(same=True)
        v = load(obj_file(out, COPY))
        e = v["same_files"]["earlier"]
        self.assertEqual([(x["object"], x["basis"], x["files"]) for x in e], [(CKT_RAZAVI, "dates", [[RAZAVI_NETLIST, RAZAVI_NETLIST]])])
        orig = load(obj_file(out, CKT_RAZAVI))
        self.assertEqual([(x["object"], x["author"]) for x in orig["same_files"]["later"]], [(COPY, "Mallory Example")])
        self.assertEqual(orig["same_files"]["common"], ["models.inc"])
        self.assertIn(CKT_RAZAVI, v["names"])                       # the page links to the earlier object
        alice = load(out / "data" / "lib" / "alice.json")
        self.assertEqual(alice["same_files"], 1)
        self.assertTrue(next(c for c in alice["object_cards"] if c["name"] == COPY)["same"])
        site = load(out / "data" / "site.json")
        self.assertEqual(site["counts"]["same_files"], 1)
        self.assertEqual(site["same_rule"], SAME_RULE)              # the numbers the help gives

    def test_the_site_computes_nothing_itself(self):
        # the same copy, but an index that does not say so: nothing is marked
        out = self.built()
        self.assertIsNone(load(obj_file(out, COPY))["same_files"])
        self.assertIsNone(load(obj_file(out, CKT_RAZAVI))["same_files"])
        self.assertEqual(load(out / "data" / "site.json")["counts"]["same_files"], 0)
        # an index older than same_files: no numbers for the help either
        d = self.dir / "old"
        shutil.copytree(DATA, d)
        meta = load(d / "index.json")
        del meta["same_files"]
        (d / "index.json").write_bytes(json.dumps(meta).encode())
        build(self.instance, d, self.dir / "old-site", built="2026-12-01T00:00:00Z")
        self.assertIsNone(load(self.dir / "old-site" / "data" / "site.json")["same_rule"])

    def test_the_examples_have_none(self):
        idx = read(DATA)
        self.assertTrue(all(o.get("same_files") == {"earlier": [], "later": [], "common": []}
                            for o in idx.objects.values() if o.get("present")))
        self.assertEqual(idx.meta["same_files"]["common_groups"], 5)
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
        self.assertEqual(load(out / "data" / "site.json")["counts"]["same_files"], 0)
        self.assertIsNone(load(obj_file(out, CKT_RAZAVI))["same_files"])   # empty lists: nothing to show

    def test_the_record_of_first_seen_is_kept_and_added_to(self):
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
        seen = load(out / "data" / "seen.json")
        self.assertEqual((seen["format"], seen["since"]), ("gaze-seen/1", "2026-11-23T00:00:00Z"))
        e = seen["objects"][CKT_RAZAVI]
        self.assertEqual((e["seen"], e["library"], e.get("before")), ("2026-11-23T00:00:00Z", "official", True))
        self.assertNotIn(CKT_LEE1, seen["objects"])                  # not present: never seen
        out = self.built(built="2026-12-01T00:00:00Z")
        seen2 = load(out / "data" / "seen.json")
        self.assertEqual(seen2["since"], "2026-11-23T00:00:00Z")
        self.assertEqual(seen2["objects"][CKT_RAZAVI], e)
        alice = next(x for x in load(out / "data" / "site.json")["libraries"] if x["key"] == "alice")
        self.assertEqual(seen2["objects"][COPY], {"seen": "2026-12-01T00:00:00Z", "library": "alice", "commit": alice["commit"]})
        v = load(obj_file(out, COPY))
        self.assertEqual(v["seen"]["seen"], "2026-12-01T00:00:00Z")
        self.assertEqual(v["swhid"], "swh:1:dir:" + "c" * 40)
        self.assertIsNone(v["swh"])                                  # not asked: off by default

    def test_software_heritage_is_asked_only_when_set(self):
        (self.instance / "gaze.yaml").write_bytes(b"software_heritage_check: true\n")
        sent = []

        class Resp:
            def __init__(self, body):
                self.body = body

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout=None):
            asked = json.loads(req.data)
            sent.append(asked)
            return Resp(json.dumps({s: {"known": s.endswith(CKT_RAZAVI[4:])} for s in asked}).encode())

        out = self.dir / "site"
        with mock.patch("urllib.request.urlopen", urlopen):
            build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
            self.assertEqual(len(sent[0]), 11)
            v = load(obj_file(out, CKT_RAZAVI))
            self.assertEqual(v["swh"], {"known": True, "since": "2026-11-23T00:00:00Z"})
            self.assertEqual(load(obj_file(out, CKT_WRAP1))["swh"], {"known": False, "since": None})
            build(self.instance, DATA, out, built="2026-11-24T00:00:00Z")
            self.assertEqual(len(sent[1]), 10)                         # what is archived is not asked again
            self.assertEqual(load(obj_file(out, CKT_RAZAVI))["swh"]["since"], "2026-11-23T00:00:00Z")
            build(self.instance, DATA, out, built="2026-11-25T00:00:00Z", offline=True)
            self.assertEqual(len(sent), 2)                             # offline: not asked, the record kept
            self.assertTrue(load(obj_file(out, CKT_RAZAVI))["swh"]["known"])
        self.assertTrue(load(out / "data" / "site.json")["swh_check"])

    def test_the_setting_is_true_or_false(self):
        (self.instance / "gaze.yaml").write_bytes(b"software_heritage_check: yes\n")
        with self.assertRaises(config.ConfigError):
            config.load(self.instance)
        self.assertFalse(config.Config().software_heritage_check)


def with_signature(src: Path, dst: Path, *, kind: str | None = "ssh",
                   address: str = "https://github.com/someone/official.git") -> str:
    """The index at src, written to dst with the library official at `address` and the commit that put
    CKT_RAZAVI into it signed (`kind`); every other place unsigned. Returns that commit."""
    shutil.copytree(src, dst)
    meta = load(dst / "index.json")
    for lib in meta["libraries"]:
        if lib["key"] == "official":
            lib["address"] = address
    (dst / "index.json").write_bytes(json.dumps(meta).encode("utf-8"))
    rec = load(dst / "libraries" / "official.json")
    rec["address"] = address
    (dst / "libraries" / "official.json").write_bytes(json.dumps(rec).encode("utf-8"))
    commit = None
    for f in (dst / "objects").glob("*/*.json"):
        o = load(f)
        for loc in o.get("locations") or []:
            signed = o["name"] == CKT_RAZAVI and loc["library"] == "official"
            loc["first_signature"] = kind if signed else None
            if signed:
                commit = loc["first_commit"]
        if o.get("first"):
            o["first"]["signature"] = kind if o["name"] == CKT_RAZAVI and o["first"]["library"] == "official" else None
        f.write_bytes(json.dumps(o).encode("utf-8"))
    return commit


class Signatures(unittest.TestCase):
    """Who signed the commit that put an object into a library (decision B35, second step)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def index(self, **kw):
        d = self.dir / "index"
        if d.exists():
            shutil.rmtree(d)
        commit = with_signature(DATA, d, **kw)
        return read(d), commit

    def github(self, answers: dict):
        """A stand-in for the GitHub API: path -> JSON, or an exception to raise; records the paths asked."""
        self.asked = []

        def get(path):
            self.asked.append(path)
            a = answers[path]
            if isinstance(a, Exception):
                raise a
            return a
        return get

    @staticmethod
    def commit_json(verified, reason="valid", committer="alice-z"):
        return {"commit": {"verification": {"verified": verified, "reason": reason}}, "committer": {"login": committer}}

    def test_libraries_on_github_are_found_by_their_address(self):
        from gaze.authorship import github_repo
        self.assertEqual(github_repo("https://github.com/o/r.git"), "o/r")
        self.assertEqual(github_repo("git@github.com:o/r"), "o/r")
        self.assertIsNone(github_repo("https://gitlab.com/o/r"))
        self.assertIsNone(github_repo("https://github.com/o"))

    def test_only_signed_commits_on_github_are_asked(self):
        from gaze.authorship import signed_commits
        idx, commit = self.index()
        self.assertEqual(signed_commits(idx), {commit: "someone/official"})
        idx, _ = self.index(address="https://codeberg.org/someone/official.git")
        self.assertEqual(signed_commits(idx), {})
        idx, _ = self.index(kind=None)
        self.assertEqual(signed_commits(idx), {})

    def test_what_github_says_is_kept_and_not_asked_again(self):
        from gaze.authorship import check_signatures
        a, b = "a" * 40, "b" * 40
        get = self.github({f"repos/o/r/commits/{a}": self.commit_json(True),
                           f"repos/o/r/commits/{b}": self.commit_json(False, "unknown_key", "bob")})
        r = check_signatures({a: "o/r", b: "o/r"}, None, "2026-12-01T00:00:00Z", self.log.append, get=get)
        self.assertEqual((r["commits"][a]["verified"], r["commits"][a]["signer"]), (True, "alice-z"))
        self.assertEqual((r["commits"][b]["verified"], r["commits"][b]["reason"], r["commits"][b]["signer"]),
                         (False, "unknown_key", None))
        again = check_signatures({a: "o/r", b: "o/r"}, r, "2026-12-02T00:00:00Z", self.log.append, get=self.github({}))
        self.assertEqual(self.asked, [])
        self.assertEqual(again["commits"], r["commits"])

    def test_a_commit_github_signed_on_the_web_names_the_pull_request(self):
        from gaze.authorship import check_signatures
        a = "c" * 40
        get = self.github({f"repos/o/r/commits/{a}": self.commit_json(True, committer="web-flow"),
                           f"repos/o/r/commits/{a}/pulls": [{"number": 7, "user": {"login": "alice-z"},
                                                             "html_url": "https://github.com/o/r/pull/7"}]})
        e = check_signatures({a: "o/r"}, None, "2026-12-01T00:00:00Z", self.log.append, get=get)["commits"][a]
        self.assertEqual((e["web_flow"], e["signer"]), (True, None))
        self.assertEqual(e["pulls"], [{"number": 7, "author": "alice-z", "url": "https://github.com/o/r/pull/7"}])

    def test_a_failure_ends_the_asking_and_keeps_what_was_known(self):
        import urllib.error
        from gaze import authorship
        a, b, c = "a" * 40, "b" * 40, "c" * 40
        prev = {"format": authorship.SIG_FORMAT, "checked": "2026-11-30T00:00:00Z",
                "commits": {a: {"repo": "o/r", "verified": True, "reason": "valid", "signer": "alice-z"}}}
        get = self.github({f"repos/o/r/commits/{b}": urllib.error.HTTPError("u", 404, "Not Found", {}, None),
                           f"repos/o/r/commits/{c}": urllib.error.HTTPError("u", 403, "rate limited", {}, None)})
        r = authorship.check_signatures({a: "o/r", b: "o/r", c: "o/r"}, prev, "2026-12-01T00:00:00Z", self.log.append, get=get)
        self.assertEqual(self.asked, [f"repos/o/r/commits/{b}", f"repos/o/r/commits/{c}"])
        # not found: asked again next time; failed: what was known is kept as it was
        self.assertEqual(set(r["commits"]), {a})
        self.assertEqual(r["checked"], "2026-11-30T00:00:00Z")

    def test_at_most_so_many_commits_a_build(self):
        from gaze import authorship
        shas = [f"{i:040x}" for i in range(5)]
        get = self.github({f"repos/o/r/commits/{x}": self.commit_json(True) for x in shas})
        with mock.patch.object(authorship, "SIG_MAX", 2):
            r = authorship.check_signatures({x: "o/r" for x in shas}, None, "2026-12-01T00:00:00Z", self.log.append, get=get)
        self.assertEqual(len(r["commits"]), 2)
        self.assertIn("3 left for the next build", self.log[-1])

    def test_each_place_shows_its_signature(self):
        idx, commit = self.index()
        m = Model(idx, config.Config())
        m.signatures = {commit: {"repo": "someone/official", "verified": True, "reason": "valid", "signer": "alice-z"}}
        v = m.view(CKT_RAZAVI, {}, {})
        by_lib = {loc["library"]: loc["signature"] for loc in v["locations"]}
        self.assertEqual(by_lib["official"], {"kind": "ssh", "github": True, "check": m.signatures[commit]})
        self.assertEqual(by_lib["official-chen"], {"kind": None})
        self.assertEqual(v["first_signature"]["kind"], "ssh")

    def test_the_commits_of_the_examples_are_not_signed(self):
        v = Model(read(DATA), config.Config()).view(CKT_RAZAVI, {}, {})
        self.assertEqual([loc["signature"] for loc in v["locations"]], [{"kind": None}, {"kind": None}])
        self.assertEqual(v["first_signature"], {"kind": None})

    def test_an_index_without_the_keys_says_nothing_of_signatures(self):
        d = self.dir / "old"
        shutil.copytree(DATA, d)
        for f in (d / "objects").glob("*/*.json"):
            o = load(f)
            for loc in o.get("locations") or []:
                loc.pop("first_signature", None)
            (o.get("first") or {}).pop("signature", None)
            f.write_bytes(json.dumps(o).encode("utf-8"))
        v = Model(read(d), config.Config()).view(CKT_RAZAVI, {}, {})
        self.assertIsNone(v["locations"][0]["signature"])
        self.assertIsNone(v["first_signature"])

    def test_the_build_asks_only_with_a_token_and_online(self):
        idx_dir = self.dir / "index"
        commit = with_signature(DATA, idx_dir)
        instance = self.dir / "instance"
        instance.mkdir()
        out = self.dir / "site"
        answer = {"format": "gaze-signatures/1", "checked": "2026-12-01T00:00:00Z",
                  "commits": {commit: {"repo": "someone/official", "verified": True, "reason": "valid", "signer": "alice-z"}}}
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "t"}), \
                mock.patch("gaze.authorship.check_signatures", return_value=answer) as check:
            build(instance, idx_dir, out, built="2026-12-01T00:00:00Z", offline=True)
            self.assertEqual(check.call_args.args[0], {})          # offline: nothing to ask
            build(instance, idx_dir, out, built="2026-12-02T00:00:00Z")
            self.assertEqual(check.call_args.args[0], {commit: "someone/official"})
            self.assertEqual(check.call_args.kwargs["token"], "t")
            self.assertTrue(load(out / "data" / "site.json")["sig_check"])
        self.assertEqual(load(out / "data" / "signatures.json"), answer)
        loc = next(x for x in load(obj_file(out, CKT_RAZAVI))["locations"] if x["library"] == "official")
        self.assertEqual(loc["signature"]["check"]["signer"], "alice-z")
        # without a token nothing is asked, and what was known is kept
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_TOKEN", None)
            build(instance, idx_dir, out, built="2026-12-03T00:00:00Z")
        self.assertEqual(load(out / "data" / "signatures.json")["commits"], answer["commits"])
        self.assertFalse(load(out / "data" / "site.json")["sig_check"])

    def test_the_setting_is_true_or_false(self):
        instance = self.dir / "instance"
        instance.mkdir()
        (instance / "gaze.yaml").write_bytes(b"github_signature_check: false\n")
        self.assertFalse(config.load(instance).github_signature_check)
        self.assertTrue(config.Config().github_signature_check)
        (instance / "gaze.yaml").write_bytes(b"github_signature_check: maybe\n")
        with self.assertRaises(config.ConfigError):
            config.load(instance)


class Stamps(unittest.TestCase):
    """Timestamp proofs beside the copies of an object (TOA 4.3; decision B35, second step): the index
    lists them, the site shows them and checks none."""
    OTS = {"file": "20261124-btc.ots", "kind": "opentimestamps", "size": 1210}
    TSR = {"file": "20261125-tsa.tsr", "kind": "rfc3161", "size": 953}

    @staticmethod
    def stamped(idx, by_lib: dict) -> None:
        """Give the copies of sky130-razavi in these libraries these stamps (commit and date added)."""
        for loc in idx.get(CKT_RAZAVI)["locations"]:
            loc["stamps"] = by_lib.get(loc["library"], [])

    def test_the_examples_have_none(self):
        m = Model(read(DATA), config.Config())
        self.assertTrue(all(loc.get("stamps") == [] for o in m.index.objects.values() for loc in o.get("locations") or []))
        self.assertEqual(m.view(CKT_RAZAVI, {}, {})["stamps"], [])

    def test_a_proof_in_two_copies_is_one_with_two_places(self):
        idx = read(DATA)
        self.stamped(idx, {
            "official": [{**self.OTS, "commit": "1" * 40, "date": "2026-11-24T10:00:00+08:00"}],
            "official-chen": [{**self.TSR, "commit": "3" * 40, "date": "2026-11-25T10:00:00Z"},
                              {**self.OTS, "commit": "2" * 40, "date": "2026-11-26T10:00:00Z"}],
        })
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "official").mkdir()
            v = Model(idx, config.Config(), local_files=[Path(tmp)]).view(CKT_RAZAVI, {}, {})
        s = v["stamps"]
        self.assertEqual([(x["file"], x["kind"], x["size"]) for x in s],
                         [("20261124-btc.ots", "opentimestamps", 1210), ("20261125-tsa.tsr", "rfc3161", 953)])
        self.assertEqual([(p["library"], p["commit"]) for p in s[0]["places"]], [("official", "1" * 40), ("official-chen", "2" * 40)])
        path = idx.get(CKT_RAZAVI)["locations"][0]["path"]
        self.assertEqual(s[0]["places"][0]["raw"], f"local/official/{path}.stamps/20261124-btc.ots")
        self.assertIsNone(s[0]["places"][1]["raw"])        # official-chen: a made-up host, no checkout here

    def test_a_proof_replaced_by_another_size_is_another_proof(self):
        idx = read(DATA)
        self.stamped(idx, {"official": [{**self.OTS, "commit": "1" * 40, "date": "2026-11-24T00:00:00Z"}],
                           "official-chen": [{**self.OTS, "size": 3000, "commit": "1" * 40, "date": "2026-11-24T00:00:00Z"}]})
        s = Model(idx, config.Config()).view(CKT_RAZAVI, {}, {})["stamps"]
        self.assertEqual([(x["size"], [p["library"] for p in x["places"]]) for x in s], [(1210, ["official"]), (3000, ["official-chen"])])

    def test_the_address_on_the_host_of_a_library(self):
        idx = read(DATA)
        for lib in idx.libraries:
            lib["address"] = lib["address"].replace("https://example.org/toa-examples/", "https://codeberg.org/someone/")
        self.stamped(idx, {"official": [{**self.OTS, "commit": "1" * 40, "date": "2026-11-24T00:00:00Z"}]})
        p = Model(idx, config.Config()).view(CKT_RAZAVI, {}, {})["stamps"][0]["places"][0]
        self.assertTrue(p["raw"].startswith("https://codeberg.org/someone/"))
        self.assertTrue(p["raw"].endswith(".stamps/20261124-btc.ots"))

    def test_an_index_without_the_key_says_nothing_of_stamps(self):
        idx = read(DATA)
        for loc in idx.get(CKT_RAZAVI)["locations"]:
            loc.pop("stamps", None)
        self.assertIsNone(Model(idx, config.Config()).view(CKT_RAZAVI, {}, {})["stamps"])


class FilesAndDrawings(unittest.TestCase):
    """Where the page reads files from, and what it needs to draw a netlist (step 4)."""

    def test_a_checkout_on_this_machine_is_read_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "official").mkdir()
            m = Model(read(DATA), config.Config(), local_files=[Path(tmp)])
            o = m.index.get(IFC_SA)
            srcs = m.raw_sources(o)
            self.assertEqual([(s["library"], s["kind"]) for s in srcs], [("official", "local")])
            self.assertEqual(srcs[0]["raw"], f"local/official/{o['locations'][0]['path']}")
            self.assertEqual(m.library_mode("official-chen"), "copy")   # a made-up host, and no checkout here

    def test_every_library_that_holds_an_object_is_a_place_to_read_it(self):
        idx = read(DATA)
        for lib in idx.libraries:
            lib["address"] = lib["address"].replace("https://example.org/toa-examples/", "https://codeberg.org/someone/")
        m = Model(idx, config.Config())
        srcs = m.raw_sources(idx.get(IFC_SA))
        self.assertEqual([s["library"] for s in srcs], ["official", "official-chen"])
        self.assertTrue(all(s["raw"].startswith("https://codeberg.org/someone/") and s["kind"] == "url" for s in srcs))

    def test_symbols_of_a_drawing_follow_references(self):
        m = Model(read(DATA), config.Config())
        v = m.view(CKT_WRAP1, {}, {})
        d = v["drawing"]
        self.assertEqual(d["entry"], "strongarm_comp.scs")
        self.assertEqual([s["ifc"] for s in d["symbols"]], [IFC_SA, IFC_DL])   # its ifc, then the ifc of uses.dyn_latch_cmp
        self.assertEqual([s["file"] for s in d["symbols"]], [None, None])   # the examples have no symbol.rnl
        self.assertEqual(d["clash"], [])
        tb = m.view(TB, {}, {})
        self.assertEqual((tb["drawing"]["entry"], [s["ifc"] for s in tb["drawing"]["symbols"]]), ("tb.scs", [IFC_SA]))
        self.assertNotIn("drawing", m.view(IFC_SA, {}, {}))

    @unittest.skipUnless(shutil.which("node"), "node is not on PATH")
    def test_the_text_given_to_the_viewer(self):
        r = subprocess.run([shutil.which("node"), "--test", str(GAZE / "tests" / "viewer_text.test.mjs")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=GAZE, timeout=120)
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-3000:])

    def test_two_definitions_of_one_name_in_a_drawing_are_a_warning(self):
        idx = read(DATA)
        dl = idx.get(IFC_DL)
        dl["manifest"]["name"] = "strongarm-comp"
        for n in (IFC_SA, IFC_DL):
            idx.get(n)["files"].append({"path": "symbol.rnl", "size": 10, "sha256": "0" * 64})
        d = Model(idx, config.Config()).view(CKT_WRAP1, {}, {})["drawing"]
        self.assertEqual(d["clash"], ["strongarm-comp"])


class Symbols(unittest.TestCase):
    PINS = [{"name": "a<b", "kind": "digital", "direction": "in"}, {"name": "y", "kind": "digital", "direction": "out"},
            {"name": "vdd", "kind": "supply", "direction": None}, {"name": "vss", "kind": "ground", "direction": None}]

    def test_a_box_from_the_pins(self):
        import xml.dom.minidom
        svg = symmod.box_svg("demo & co", self.PINS)
        doc = xml.dom.minidom.parseString(svg)
        texts = [t.firstChild.data for t in doc.getElementsByTagName("text")]
        self.assertEqual(sorted(texts), sorted(["demo & co", "a<b", "y", "vdd", "vss"]))

    @unittest.skipUnless(shutil.which("rnl"), "rnl is not on PATH")
    def test_symbol_rnl_is_drawn_by_rnl(self):
        text = (GAZE / "scripts" / "demo" / "ifc" / "inv" / "ifc_draft-inv" / "symbol.rnl").read_bytes()
        svg, why = symmod.render_rnl(shutil.which("rnl"), text, "inv", self.PINS[1:] + [{"name": "a", "kind": "digital", "direction": "in"}])
        self.assertEqual(why, "")
        self.assertTrue(svg.startswith("<svg"))
        self.assertNotIn('class="backdrop"', svg)
        for pin in (">a<", ">y<", ">vdd<", ">vss<", ">inv<"):
            self.assertIn(pin, svg)

    # a package that only applies a standard symbol to the instances of one subcircuit, in plain RNL
    RULE_ONLY = b'''/* The symbol of the subcircuit cmp_a: a standard one, applied by a rule. */
@RNL(type="header") {
  @VERSION("0.4");
  @PACKAGE(name="cmp-a-sym", version="0.1");
  @USE-PACKAGE(name="rnl-std-all", version="0.4")
}
@RNL {
  # @SELECT-INSTANCE(model="cmp_a", recursive=true) => @SET-SYMBOL(terminals=[[1, "inp"], [2, "inn"], [3, "out"]]) $COMPARATOR
}
'''
    # a symbol as another tool draws one: pins without a direction, and one pin drawn twice
    NO_DIRECTION = b'''// @RNL(type="header") { @VERSION("0.4"); @PACKAGE(name="buf-sym", version="1.0"); }
// @RNL {
//   $BUF = @DEFINE-SYMBOL {
//     %a = (-4, 0) @PIN(terminal="a");
//     %y = (4, 0) @PIN(terminal="y");
//     %vdd = (0, 2) @PIN(terminal="vdd");
//     %vdd2 = (0, -2) @PIN(terminal="vdd");
//     @LINE {(-4, 0) (-2, 0)};
//     @LINE {(-2, 2) (2, 0) (-2, -2) (-2, 2)};
//     @LINE {(2, 0) (4, 0)};
//   };
// }
'''

    @staticmethod
    def _pins(*names, width=None):
        return [{"name": n, "kind": None, "direction": None, "width": (width or {}).get(n, 1)} for n in names]

    @unittest.skipUnless(shutil.which("rnl"), "rnl is not on PATH")
    def test_a_rule_for_one_subcircuit_is_drawn_on_an_instance_of_it(self):
        svg, why = symmod.render_rnl(shutil.which("rnl"), self.RULE_ONLY, "cmp-a", self._pins("vp", "vn", "out", "vdd", "vss"))
        self.assertEqual(why, "")
        for text in (">vp<", ">out<", ">cmp-a<"):
            self.assertIn(text, svg)

    @unittest.skipUnless(shutil.which("rnl"), "rnl is not on PATH")
    def test_a_bus_is_a_port_for_each_bit(self):
        rule = self.RULE_ONLY.replace(b"cmp_a", b"reg_a")
        svg, why = symmod.render_rnl(shutil.which("rnl"), rule, "reg-a", self._pins("d", "q", width={"d": 2}))
        self.assertEqual(why, "")
        for text in (">d_1<", ">d_2<", ">q<"):
            self.assertIn(text, svg)

    @unittest.skipUnless(shutil.which("rnl"), "rnl is not on PATH")
    def test_a_symbol_whose_pins_have_no_direction_is_drawn_with_the_package_alone(self):
        svg, why = symmod.render_rnl(shutil.which("rnl"), self.NO_DIRECTION, "buf", self._pins("a", "y", "vdd"))
        self.assertEqual(why, "")
        self.assertIn(">buf<", svg)

    def test_a_package_without_a_symbol_is_refused(self):
        if not shutil.which("rnl"):
            self.skipTest("rnl is not on PATH")
        svg, why = symmod.render_rnl(shutil.which("rnl"), b'// @RNL(type="header") { @VERSION("0.4"); @PACKAGE(name="x-sym", version="1.0"); }\n', "x", [])
        self.assertIsNone(svg)
        self.assertTrue(why)


PLL = GAZE / "tests" / "data" / "pll-subset"
CKT_CMP = "ckt_2676eab4204171af41fa4f48a446d1d563e13b2b"
CKT_INV55 = "ckt_915f0e3f6d0190f8767a9ee188b587bef3f4e0ea"
CKT_INV7 = "ckt_7544bbde7fdaef6fb3fa34e72a5c1ebe8aaf398d"
IFC_CMP = "ifc_90b6278770a1aec49ef5716afd4eb8e298bb326b"
IFC_INV55 = "ifc_fb949e83c8b4b19b98c57d8fcbf49b8bb8f6fb84"
IFC_INV7 = "ifc_c0dfe4e6bdb90696e0394568aa04a67a45ac6d4b"
CMP_DIR = "ckt/cmp-physical-v14-pdk110-54/pll.g1/" + CKT_CMP


class PllSubset(unittest.TestCase):
    """Six objects of the PLL test library as the Virtuoso converter writes them (tests/data/pll-subset,
    made by scripts/pll_subset.py): a comparator whose Spectre netlist uses a package of its own object
    by path, the two inverters it uses, and their interfaces, whose symbol.rnl only applies a standard
    symbol by a rule. The library is read from the checkout in tests/data/pll-subset/pll."""

    def model(self) -> Model:
        return Model(read(PLL / "index"), config.Config(), local_files=[PLL])

    def test_the_six_objects_and_their_names(self):
        m = self.model()
        self.assertEqual(sorted(m.index.objects), sorted([CKT_CMP, CKT_INV55, CKT_INV7, IFC_CMP, IFC_INV55, IFC_INV7]))
        self.assertTrue(all(o["valid"] for o in m.index.objects.values()))
        self.assertEqual(m.display(CKT_CMP), "cmp-physical-v14-pdk110-54/pll.g1")
        self.assertEqual(m.display(IFC_INV7), "pll-inv-pdk110-7")
        self.assertEqual(m.index.problems, [])

    def test_publish_marks_every_object_latest(self):
        m = self.model()
        for n in m.index.objects:
            self.assertEqual(m.card(n)["latest"], ["pll"], n)

    def test_the_comparator_is_drawn_with_its_package_and_the_symbols_of_what_it_uses(self):
        m = self.model()
        d = m.view(CKT_CMP, {}, {})["drawing"]
        self.assertEqual(d["entry"], "54_cmp_physical_v14.scs")
        self.assertEqual(d["files"], ["54_cmp_physical_v14.scs", "pll_semantics.rnl"])
        # its own interface, then the interfaces of uses, in the order of toa.yaml
        self.assertEqual([s["ifc"] for s in d["symbols"]], [IFC_CMP, IFC_INV55, IFC_INV7])
        self.assertEqual([s["name"] for s in d["symbols"]], ["cmp-physical-v14-pdk110-54", "pll-inv-pdk110-55", "pll-inv-pdk110-7"])
        self.assertEqual([s["file"]["path"] for s in d["symbols"]], ["symbol.rnl"] * 3)
        self.assertEqual(d["clash"], [])
        src = d["symbols"][1]["sources"]
        self.assertEqual([(s["library"], s["kind"]) for s in src], [("pll", "local")])
        self.assertEqual(src[0]["raw"], "local/pll/ifc/pll-inv-pdk110-55/" + IFC_INV55)
        self.assertTrue((PLL / "pll" / "ifc" / "pll-inv-pdk110-55" / IFC_INV55 / "symbol.rnl").is_file())

    def test_the_files_of_the_checkout_are_the_indexed_ones(self):
        import hashlib
        m = self.model()
        for o in m.index.objects.values():
            d = PLL / "pll" / o["locations"][0]["path"]
            for f in o["files"]:
                b = (d / f["path"]).read_bytes()
                self.assertEqual((len(b), hashlib.sha256(b).hexdigest()), (f["size"], f["sha256"]), f"{o['name']}/{f['path']}")

    @unittest.skipUnless(shutil.which("rnl"), "rnl is not on PATH")
    def test_the_symbol_of_the_comparator_is_drawn_by_rnl(self):
        m = self.model()
        text = (PLL / "pll" / "ifc" / "cmp-physical-v14-pdk110-54" / IFC_CMP / "symbol.rnl").read_bytes()
        pins = symmod.pin_list(m.index.get(IFC_CMP)["manifest"])
        self.assertEqual([p["name"] for p in pins], ["vp", "vn", "out", "vdd", "vss"])
        svg, why = symmod.render_rnl(shutil.which("rnl"), text, "cmp-physical-v14-pdk110-54", pins)
        self.assertEqual(why, "")
        for t in (">vp<", ">vn<", ">out<", ">cmp-physical-v14-pdk110-54<"):
            self.assertIn(t, svg)


class FeedsAndAgents(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.instance = self.dir / "instance"
        self.instance.mkdir()
        (self.instance / "workspace.source.jsonl").write_bytes(b'{"toa": "source/1"}\n')
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("GITHUB_REPOSITORY", "GITHUB_SERVER_URL"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_feeds_need_the_address_of_the_site(self):
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
        self.assertFalse((out / "feeds").exists())
        self.assertFalse(load(out / "data" / "site.json")["feeds"])
        self.assertTrue((out / "llms.txt").is_file())

    def test_feeds(self):
        import xml.dom.minidom
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z", site_url="https://example.org/gaze/")
        self.assertTrue(load(out / "data" / "site.json")["feeds"])
        atom = "{http://www.w3.org/2005/Atom}"
        import xml.etree.ElementTree as ET
        root = ET.parse(out / "feeds" / "all.xml").getroot()
        entries = root.findall(atom + "entry")
        self.assertTrue(entries)
        self.assertEqual(root.find(atom + "link").get("href"), "https://example.org/gaze/feeds/all.xml")
        titles = [e.find(atom + "title").text for e in entries]
        # the definition a fork carries is one event, with both libraries
        self.assertIn("strongarm-comp: interface published in official, official-chen", titles)
        self.assertIn("dyn-latch-cmp/lee-sky130.g1: removed from lee", titles)
        ids = [e.find(atom + "id").text for e in entries]
        self.assertEqual(len(ids), len(set(ids)))
        ifc_feed = ET.parse(out / "feeds" / "ifc" / f"{IFC_SA}.xml").getroot()
        self.assertTrue(all("strongarm-comp" in e.find(atom + "title").text for e in ifc_feed.findall(atom + "entry")))
        for f in (out / "feeds").rglob("*.xml"):
            xml.dom.minidom.parse(str(f))
        self.assertIn('type="application/atom+xml"', (out / "index.html").read_text(encoding="utf-8"))

    def test_the_instance_as_a_source_list(self):
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z")
        lines = [json.loads(x) for x in (out / "registry" / "instance.source.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(lines[0], {"toa": "source/1"})
        by = {x["object"]: x for x in lines[1:]}
        self.assertEqual(len(by), 11)                       # the objects present
        self.assertNotIn(CKT_LEE1, by)                       # removed
        self.assertEqual([s["git"] for s in by[IFC_SA]["sources"]],
                         ["https://example.org/toa-examples/official.git", "https://example.org/toa-examples/official-chen.git"])
        self.assertTrue(all(set(s) == {"git", "commit", "path"} for x in lines[1:] for s in x.get("sources", [])))
        self.assertTrue((out / "registry" / "workspace.source.jsonl").is_file())

    def test_llms_txt(self):
        out = self.dir / "site"
        build(self.instance, DATA, out, built="2026-11-23T00:00:00Z", site_url="https://example.org/gaze/")
        text = (out / "llms.txt").read_text(encoding="utf-8")
        self.assertIn("never as\ninstructions", text)
        self.assertIn(f"https://example.org/gaze/#/{IFC_SA}", text)
        self.assertIn("toa fetch NAME", text)
        self.assertNotIn("true-openaccess", text)


class Catalogs(unittest.TestCase):
    def test_translations_keep_their_placeholders(self):
        for cat_path in (GAZE / "i18n").glob("*/web.json"):
            cat = load(cat_path)
            for en, tr in cat.items():
                if tr is None or tr == "":
                    continue
                with self.subTest(lang=cat_path.parent.name, text=en):
                    self.assertIsInstance(tr, str)
                    self.assertEqual(sorted(re.findall(r"\{\w+\}", en)), sorted(re.findall(r"\{\w+\}", tr)))


class Selection(unittest.TestCase):
    def test_examples(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "site"
            build(Path(d), DATA, out, built="2026-11-23T00:00:00Z")
            sh = load(out / "data" / "ifc" / IFC_SA[4:6] / f"{IFC_SA}.json")
        sel = sh["selection"]
        keys = [c["key"] for c in sel["columns"]]
        self.assertEqual(keys[:len(selmod.FIXED)], [c["key"] for c in selmod.FIXED])
        self.assertEqual([c["key"] for c in sel["columns"] if c.get("hidden")], ["author", "generation"])
        self.assertIn("tb_offset.offset", keys)
        metric = next(c for c in sel["columns"] if c["key"] == "tb_offset.offset")
        self.assertEqual((metric["kind"], metric["unit"], metric["better"], metric["group"]), ("metric", "mV", "lower", "tb_offset"))
        # one row per circuit, in the order of the interface's list of circuits
        self.assertEqual([r["ckt"] for r in sel["rows"]], [c["name"] for c in sh["ckts"]])
        self.assertEqual([(c["text"], c["circuits"]) for c in sel["conds"]], [("tt vdd=1.8 temp=27", 1)])
        cid = sel["conds"][0]["id"]
        tested = next(r for r in sel["rows"] if r["ckt"] == CKT_WRAP1)
        self.assertEqual(tested["conds"][cid]["values"]["tb_offset.offset"], 1.7)
        self.assertTrue(all(not r["conds"] for r in sel["rows"] if r["ckt"] != CKT_WRAP1))
        # the fixed columns come from the cards
        card = next(c for c in sh["ckts"] if c["name"] == CKT_WRAP1)
        self.assertEqual({k: tested["values"][k] for k in ("form", "process", "latest", "libraries", "first_date")},
                         {k: card[k] for k in ("form", "process", "latest", "libraries", "first_date")})
        # by default the page shows the head of each series; the others are counted on its first head
        series = {x["series"]: x for x in sh["series"]["ckt"]}
        heads = {n for x in series.values() for n in x["heads"]}
        self.assertEqual({r["ckt"] for r in sel["rows"] if r["head"]}, heads)
        self.assertEqual(sum(r["others"] for r in sel["rows"]), sum(len(x["rest"]) for x in series.values()))

    def test_one_row_per_circuit_with_the_median_of_its_records_per_set_of_conditions(self):
        idx = synthetic([(R1, "a", 1.0), (R2, "b", 1.6), (R3, "a", 3.0)], {"abs": 0.2})
        idx.objects[R3]["manifest"]["conditions"] = {"parameters": {"vdd": 1.2}}
        model = Model(idx, config.Config())
        dut, tb = "ckt_" + "1" * 40, "tb_" + "2" * 40
        sel = selmod.build(model, [dut], [tb], repro.build_groups(idx))
        self.assertEqual(len(sel["rows"]), 1)
        # the set with the most circuits first; here one each, so by its text
        self.assertEqual([c["text"] for c in sel["conds"]], ["vdd=1.2", "vdd=1.8"])
        by = {c["text"]: sel["rows"][0]["conds"][c["id"]] for c in sel["conds"]}
        self.assertEqual(by["vdd=1.8"]["values"]["tb_x.m"], 1.3)
        self.assertEqual(by["vdd=1.8"]["marks"]["tb_x.m"], {"n": 2, "multi": True, "disagree": True})
        self.assertEqual(by["vdd=1.2"]["marks"]["tb_x.m"], {"n": 1, "multi": False, "disagree": False})
        self.assertTrue(sel["rows"][0]["head"])

    def test_conditions_in_one_line(self):
        c = {"models": [{"file": "a.lib", "section": "ff"}], "parameters": {"vdd": 1.0, "n": [1, 2]}, "options": {"temp": -40}}
        self.assertEqual(repro.conditions_text(c), "ff vdd=1 n=[1,2] temp=-40")
        self.assertEqual(repro.conditions_text({}), "")
        g = repro.build_groups(synthetic([(R1, "a", 1.0)]))[0]
        self.assertEqual(g["cond_text"], "vdd=1.8")   # the page shows the build's text, never reads a slot

    def test_the_page_names_no_field_of_a_manifest(self):
        # the builder says what the columns are; selection.js only draws them
        from gaze import fields
        js = (GAZE / "web" / "assets" / "selection.js").read_text(encoding="utf-8")
        names = {fields.AUTHOR, fields.TITLE, fields.TAGS}
        for cls in (fields.CKT, fields.SPEC, fields.ROLE, fields.USE, fields.TB, fields.EVD, fields.COND, fields.METRIC, fields.ENV):
            names.update(v for k, v in vars(cls).items() if k.isupper() and isinstance(v, str))
        for n in sorted(names):
            with self.subTest(field=n):
                self.assertNotIn(f'"{n}"', js)

    def test_no_page_reads_a_field_that_toa_renamed(self):
        # B26/B27: the page reads the views of the builder, whose keys follow the new names
        # `summary` is the card's own one-line text (title, or the first line of description)
        old = ["series", "version", "status", "cpu_hours", "simulator_params", "params", "specs",
               "dir", "tol", "env", "impl", "modelfile", "simulatorparameter", "parameter"]
        js = "".join((GAZE / "web" / "assets" / f).read_text(encoding="utf-8") for f in ("pages.js", "app.js", "selection.js"))
        for k in old:
            with self.subTest(key=k):
                self.assertNotRegex(js, rf"\b(?:v|c|u|d|m|g|sp|p)\.{k}\b")
        # B32/B33: the types and the fields renamed then
        for k in ("ip", "imp", "ips", "imps", "ver", "based_on", "based_on_by", "together", "simulator_options", "model_files"):
            with self.subTest(key=k):
                self.assertNotRegex(js, rf"\.{k}\b")


class ShippedFiles(unittest.TestCase):
    def test_the_fonts_are_shipped_with_their_licences(self):
        fonts = GAZE / "web" / "fonts"
        css = (fonts / "fonts.css").read_text(encoding="utf-8")
        urls = re.findall(r"url\(\./([^)]+)\)", css)
        self.assertGreater(len(urls), 100)
        for u in urls:
            self.assertTrue((fonts / u).is_file(), u)
        for fam in ("ibm-plex-sans", "ibm-plex-mono", "noto-sans-sc"):
            self.assertIn("SIL Open Font License", (fonts / fam / "OFL.txt").read_text(encoding="utf-8"))
        for family in ("IBM Plex Sans", "IBM Plex Mono", "Noto Sans SC"):
            self.assertIn(f'font-family:"{family}"', css)
        self.assertIn('href="./fonts/fonts.css"', (GAZE / "web" / "index.html").read_text(encoding="utf-8"))
        self.assertNotRegex(css + (GAZE / "web" / "index.html").read_text(encoding="utf-8"), r"https?://")

    def test_the_workflows_pin_what_they_run(self):
        for wf in (GAZE / ".github" / "workflows").glob("*.yml"):
            text = wf.read_text(encoding="utf-8")
            with self.subTest(workflow=wf.name):
                for use in re.findall(r"uses:\s*(\S+)", text):
                    self.assertRegex(use, r"@[0-9a-f]{40}$")
                # nothing ties the workflow to where it is published, so a fork runs it unchanged;
                # the one exception is where the source of toa is fetched from, which a fork shares
                self.assertNotIn("true-openaccess", re.sub(r"(?m)^  TOA_REPO: https://github\.com/true-openaccess/toa$", "", text))
                self.assertNotIn("secrets.", text)
                # a source built from a repository is pinned to a full commit id (empty: not set yet)
                if "TOA_REPO:" in text:
                    self.assertRegex(text, r'(?m)^  TOA_COMMIT: "(?:[0-9a-f]{40})?"$')
                    self.assertRegex(text, r'(?m)^  TOA_RUST: "\d+\.\d+\.\d+"$')
                    self.assertIn("--locked", text)
                # a release archive a workflow downloads comes with its SHA-256
                for name in re.findall(r'(\w+)_URL: (?:""|https://\S+\.(?:tar\.gz|zip))$', text, re.M):
                    self.assertIn(f"{name}_SHA256:", text)


if __name__ == "__main__":
    unittest.main()
