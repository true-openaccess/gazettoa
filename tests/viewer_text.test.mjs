// The text the page gives the RNL viewer (web/assets/core.js textForViewer), on the drawing demo.
// Run from gaze/: node --test tests/viewer_text.test.mjs (test_builder.py runs it when node is on PATH).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { RNL_RECORD, textForViewer, fmtDate } from "../web/assets/core.js";

const demo = new URL("../scripts/demo/", import.meta.url);
const read = p => readFileSync(new URL(p, demo), "utf8");
const BUF2 = read("ckt/buf2/two-inv.g1/ckt_draft-buf2-inv/buf2.sp");
const INV = read("ckt/inv/cmos.g1/ckt_draft-inv-cmos/inv.sp");
const INV_SYM = read("ifc/inv/ifc_draft-inv/symbol.rnl");
const BUF2_SYM = read("ifc/buf2/ifc_draft-buf2/symbol.rnl");

test("a symbol package the netlist uses goes after its header record, its USE-PACKAGE taken out", () => {
  const out = textForViewer(BUF2, {}, [{ ifc: "ifc_inv", text: INV_SYM }]);
  assert.doesNotMatch(out, /@USE-PACKAGE\(name="inv-sym"/);
  assert.match(out, /@USE-PACKAGE\(name="rnl-std-all", version="0.4"\)/);
  assert.doesNotMatch(out, /@PACKAGE\(/);
  assert.doesNotMatch(out, /^\/\//m, "record lines of the package are written with *, which SPICE and Spectre both read");
  const header = out.indexOf('@RNL(type="header")');
  const sym = out.indexOf("$INV = @DEFINE-SYMBOL");
  const sub = out.indexOf(".subckt buf2");
  assert.ok(header >= 0 && header < sym && sym < sub);
  assert.match(out, /the symbol package inv-sym of the interface ifc_inv/);
});

test("a package the netlist does not use is left out", () => {
  assert.equal(textForViewer(BUF2, {}, [{ ifc: "ifc_buf2", text: BUF2_SYM }]), BUF2);
});

test("an include of a file of the same object is put in place", () => {
  const net = '* top\n* @RNL(type="header") { @VERSION("0.4"); }\n.include "./sub.sp"\nX1 a b sub\n.end\n';
  const out = textForViewer(net, { "sub.sp": ".subckt sub a b\nR1 a b 1k\n.ends sub" }, []);
  assert.doesNotMatch(out, /\.include/);
  assert.match(out, /\.subckt sub a b\nR1 a b 1k\n\.ends sub\nX1 a b sub/);
  const other = textForViewer('* top\n.include "models.lib"\n.end\n', {}, []);
  assert.match(other, /\.include "models\.lib"/, "a file outside the object stays an include");
});

test("a netlist without a header record is sent as it is", () => {
  const net = "* plain\nR1 a 0 1k\n.end\n";
  assert.equal(textForViewer(net, {}, [{ ifc: "ifc_inv", text: INV_SYM }]), net);
});

test("RNL records are whole-line comments with @RNL after one space at most", () => {
  assert.ok(RNL_RECORD.test("* @RNL { #R1 @PLACE(0, 0); }"));
  assert.ok(RNL_RECORD.test("// @RNL(type=\"header\") {}"));
  assert.ok(!RNL_RECORD.test("*@RNL { #R1 @PLACE(0, 0); }"), "no space: not a record line");
  assert.ok(!RNL_RECORD.test("  * @RNL { #R1 @PLACE(0, 0); }"), "indented: not a record line");
  assert.ok(!RNL_RECORD.test("R1 a 0 1k ; @RNL"));
});

test("a header record of several lines, with the devices of a process, is kept as it is", () => {
  // TOA keeps model cards out of an object (types/ckt, checks at sealing 3): @DEVICE gives the types
  assert.match(INV, /@DEVICE\(model="nch"/);
  assert.doesNotMatch(INV, /^\.model/m);
  assert.equal(textForViewer(INV, {}, [{ ifc: "ifc_inv", text: INV_SYM }]), INV);
});

// A Spectre netlist whose header uses a package of its own object (by path) that declares the
// devices, and the symbol package of an interface written in plain RNL, as the converters write.
const SCS = [
  "simulator lang=spectre",
  '// @RNL(type="header") { @VERSION("0.4"); @USE-PACKAGE(name="rnl-std-all", version="0.4");',
  '//   @USE-PACKAGE(name="sem", version="0.1", path="sem.rnl"); @USE-PACKAGE(name="inv-a-sym", version="0.1") }',
  "subckt inv_a a y vdd vss",
  "MP (y a vdd vdd) pch",
  "MN (y a vss vss) nch",
  "ends inv_a",
  "subckt top a y vdd vss",
  "XI0 (a y vdd vss) inv_a",
  "ends top",
  "",
].join("\n");
const SEM = [
  "/* The devices of a process. */",
  '@RNL(type="header") {',
  '  @VERSION("0.4");',
  '  @PACKAGE(name="sem", version="0.1");',
  '  @USE-PACKAGE(name="rnl-std-all", version="0.4");',
  '  @DEVICE(model="nch", terminals=["d", "g", "s", "b"], type="nmos");',
  '  @DEVICE(model="pch", terminals=["d", "g", "s", "b"], type="pmos")',
  "}",
].join("\n");
const INV_A_SYM = [
  "/* The symbol of the subcircuit inv_a: a standard one, applied by a rule. */",
  '@RNL(type="header") {',
  '  @VERSION("0.4");',
  '  @PACKAGE(name="inv-a-sym", version="0.1");',
  '  @USE-PACKAGE(name="rnl-std-all", version="0.4")',
  "}",
  "@RNL {",
  '  # @SELECT-INSTANCE(model="inv_a", recursive=true) => @SET-SYMBOL(terminals=[[1, "a"], [2, "y"]]) $INVERTER',
  "}",
].join("\n");

test("a package in plain RNL, from the object by path or from an interface, is put in as record lines", () => {
  const out = textForViewer(SCS, { "sem.rnl": SEM }, [{ ifc: "ifc_inv_a", text: INV_A_SYM }]);
  assert.doesNotMatch(out, /@USE-PACKAGE\(name="(sem|inv-a-sym)"/, "the packages put in are not used again");
  assert.doesNotMatch(out, /@PACKAGE\(/);
  assert.equal(out.match(/@USE-PACKAGE\(name="rnl-std-all"/g).length, 1, "a package both use is used once");
  assert.doesNotMatch(out, /^@RNL/m, "no record of a package is left bare, where it would read as an instance");
  assert.match(out, /^\* @RNL \{\n\* {3}# @SELECT-INSTANCE\(model="inv_a"/m);
  // the devices of the package are moved into the netlist's header, whose lines keep their mark
  const lines = out.split("\n");
  const start = lines.findIndex(l => l.includes('@RNL(type="header")'));
  const end = lines.findIndex((l, i) => i >= start && l.trimEnd().endsWith("}"));
  assert.ok(start > 0 && end > start);
  const header = lines.slice(start, end + 1);
  assert.ok(header.every(l => l.startsWith("//")));
  assert.ok(header.some(l => l.includes('@DEVICE(model="pch"')));
  assert.ok(out.indexOf("the package sem, the file sem.rnl of the object") < out.indexOf("subckt inv_a"));
});

test("the text with packages put in reads without errors in rnl", t => {
  const probe = spawnSync("rnl", ["--version"], { encoding: "utf8" });
  if (probe.error || probe.status !== 0) { t.skip("rnl is not on PATH"); return; }
  const dir = mkdtempSync(join(tmpdir(), "gaze-viewer-"));
  try {
    const file = join(dir, "top.scs");
    writeFileSync(file, textForViewer(SCS, { "sem.rnl": SEM }, [{ ifc: "ifc_inv_a", text: INV_A_SYM }]));
    const r = spawnSync("rnl", ["check", file], { encoding: "utf8" });
    assert.match(`${r.stdout}${r.stderr}`, /(^|\s)0 errors,/m, `${r.stdout}${r.stderr}`.slice(-2000));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

// A circuit of the PLL test library as the Virtuoso converter writes it (tests/data/pll-subset,
// scripts/pll_subset.py): a package of its own object by path, and the symbols of the interfaces
// it uses, in the order the page passes them (its own interface, then those of uses).
const pll = new URL("data/pll-subset/pll/", import.meta.url);
const readPll = p => readFileSync(new URL(p, pll), "utf8");
const CMP_DIR = "ckt/cmp-physical-v14-pdk110-54/pll.g1/ckt_2676eab4204171af41fa4f48a446d1d563e13b2b/";
const CMP = readPll(CMP_DIR + "54_cmp_physical_v14.scs");
const CMP_FILES = { "pll_semantics.rnl": readPll(CMP_DIR + "pll_semantics.rnl") };
const CMP_SYMBOLS = [
  ["ifc_90b6278770a1aec49ef5716afd4eb8e298bb326b", "cmp-physical-v14-pdk110-54"],
  ["ifc_fb949e83c8b4b19b98c57d8fcbf49b8bb8f6fb84", "pll-inv-pdk110-55"],
  ["ifc_c0dfe4e6bdb90696e0394568aa04a67a45ac6d4b", "pll-inv-pdk110-7"],
].map(([ifc, dir]) => ({ ifc, text: readPll(`ifc/${dir}/${ifc}/symbol.rnl`) }));

test("a circuit of the PLL library gets its own package and the symbols of the circuits it uses", () => {
  const out = textForViewer(CMP, CMP_FILES, CMP_SYMBOLS);
  assert.doesNotMatch(out, /@USE-PACKAGE\(name="(pll-semantics\/cmp_physical_v14_pdk110_54|pll-inv-pdk110-55-sym|pll-inv-pdk110-7-sym)"/);
  assert.doesNotMatch(out, /@PACKAGE\(/);
  assert.match(out, /@SELECT-INSTANCE\(model="pll_inv_pdk110_55"/);
  assert.match(out, /@SELECT-INSTANCE\(model="pll_inv_pdk110_7"/);
  assert.doesNotMatch(out, /\$COMPARATOR/, "the symbol of its own interface is not used by the netlist, so it is left out");
  const sem = out.indexOf("the file pll_semantics.rnl of the object");
  assert.ok(sem >= 0 && sem < out.indexOf("subckt cmp_physical_v14_pdk110_54"));
});

test("the circuit of the PLL library, with its packages put in, reads without errors in rnl", t => {
  const probe = spawnSync("rnl", ["--version"], { encoding: "utf8" });
  if (probe.error || probe.status !== 0) { t.skip("rnl is not on PATH"); return; }
  const dir = mkdtempSync(join(tmpdir(), "gaze-viewer-"));
  try {
    const file = join(dir, "54_cmp_physical_v14.scs");
    writeFileSync(file, textForViewer(CMP, CMP_FILES, CMP_SYMBOLS));
    const r = spawnSync("rnl", ["check", file], { encoding: "utf8" });
    assert.match(`${r.stdout}${r.stderr}`, /(^|\s)0 errors, 0 violations, 0 warnings/m, `${r.stdout}${r.stderr}`.slice(-2000));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a date is shown as its day in UTC, like the dates of the builds", () => {
  assert.equal(fmtDate("2026-11-24T04:29:19+08:00"), "2026-11-23");
  assert.equal(fmtDate("2026-11-23T20:00:00Z"), "2026-11-23");
  assert.equal(fmtDate("2026-11-24"), "2026-11-24");
  assert.equal(fmtDate(null), "—");
});
