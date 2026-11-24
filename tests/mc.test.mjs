// A Monte Carlo simulation on the page (web/assets/mc.js, B37): samples.csv read, its statistics
// computed, and two records compared sample by sample or by statistics.
// Run from gaze/: node --test tests/mc.test.mjs (test_builder.py runs it when node is on PATH).
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseSamples, statsOf, compare, runText } from "../web/assets/mc.js";

const CSV = "sample,tb_x.d,tb_x.t\n1,0.0,1.0e-10\n2,1.0,1.2e-10\n3,,\n4,1.0,1.1e-10\n";
const DEFS = { "tb_x.d": { tolerance: { abs: 0.25 } }, "tb_x.t": { tolerance: { abs: 1e-12 } } };

test("samples.csv: the metrics of its first line, a value left empty when the sample gave none", () => {
  const p = parseSamples(CSV);
  assert.equal(p.ok, true);
  assert.deepEqual(p.metrics, ["tb_x.d", "tb_x.t"]);
  assert.deepEqual(p.rows.map(r => r.k), [1, 2, 3, 4]);
  assert.deepEqual(p.rows[2].vals, [null, null]);
  assert.equal(p.bad, 0);
  assert.equal(parseSamples("n,a\n1,2\n").ok, false);
  assert.equal(parseSamples("sample,a\n1,x\n2,3\n").bad, 1);
});

test("the statistics of a column: n and failed, sigma with n - 1", () => {
  const s = statsOf([1, 2, null, 3]);
  assert.deepEqual([s.n, s.failed, s.mean, s.min, s.max], [3, 1, 2, 1, 3]);
  assert.equal(s.sigma, 1);
  assert.equal(statsOf([5]).sigma, null);
  assert.equal(statsOf([null]).mean, null);
});

const run = (over = {}) => ({ name: "evd_a", first: 1, points: 4, run: "batch", sampling: "lds", simulator: "spectre 21.1", stats: {}, ...over });

test("the same samples run alike are compared sample by sample, each metric within its tolerance", () => {
  const a = parseSamples(CSV);
  const b = parseSamples("sample,tb_x.d,tb_x.t\n1,0.0,1.005e-10\n2,1.0,1.2e-10\n");
  const r = compare(run(), run({ name: "evd_b", points: 2, run: "each" }), a, b, DEFS);
  assert.equal(r.mode, "samples");
  assert.equal(r.compared, 2);
  assert.equal(r.ok, true);
  const c = parseSamples("sample,tb_x.d,tb_x.t\n1,1.0,1.0e-10\n2,1.0,\n");
  const d = compare(run(), run({ name: "evd_c", points: 2 }), a, c, DEFS);
  assert.equal(d.ok, false);
  assert.deepEqual(d.diffs.map(x => [x.k, x.m]), [[1, "tb_x.d"], [2, "tb_x.t"]]);
});

test("another simulator, or lhs with another number of samples, is compared by statistics", () => {
  const st = (mean, sigma, n) => ({ "tb_x.t": { n, failed: 0, mean, sigma, min: 0, max: 1 } });
  const a = run({ stats: st(1.0, 0.1, 100) });
  const b = run({ name: "evd_b", simulator: "spectre 23.1", stats: st(1.02, 0.11, 100) });
  const r = compare(a, b, null, null, DEFS);
  assert.equal(r.mode, "statistics");
  assert.equal(r.ok, true);
  assert.equal(r.rows[0].binaryUnknown, true);
  const far = compare(a, run({ name: "evd_c", simulator: "x", stats: st(1.5, 0.1, 100) }), null, null, DEFS);
  assert.equal(far.ok, false);
  const lhs = compare(run({ sampling: "lhs", points: 10 }), run({ name: "evd_d", sampling: "lhs", points: 20 }), parseSamples(CSV), parseSamples(CSV), DEFS);
  assert.equal(lhs.mode, "statistics");
});

test("a metric of 0 and 1 only is compared by the binomial distribution", () => {
  const head = "sample,tb_x.d\n";
  const ones = k => head + Array.from({ length: 100 }, (_, i) => `${i + 1},${i < k ? 1 : 0}`).join("\n") + "\n";
  const pa = parseSamples(ones(50)), pb = parseSamples(ones(60));
  const sa = statsOf(pa.rows.map(r => r.vals[0])), sb = statsOf(pb.rows.map(r => r.vals[0]));
  const r = compare(run({ stats: { "tb_x.d": sa } }), run({ name: "evd_b", simulator: "other", stats: { "tb_x.d": sb } }), pa, pb, DEFS);
  assert.equal(r.rows[0].binary, true);
  assert.equal(r.ok, true);   // |0.5 - 0.6| <= 3 sqrt(0.55 * 0.45 * 0.02) = 0.211
  const pc = parseSamples(ones(90));
  const sc = statsOf(pc.rows.map(x => x.vals[0]));
  assert.equal(compare(run({ stats: { "tb_x.d": sa } }), run({ name: "evd_c", simulator: "other", stats: { "tb_x.d": sc } }), pa, pc, DEFS).ok, false);
});

test("which samples a record ran, in words", () => {
  assert.equal(runText({ first: 11, points: 10, run: "each" }), "samples 11 to 20, each in a simulation of its own");
  assert.equal(runText({ first: 1, points: 200, run: "batch" }), "samples 1 to 200, all in one simulation");
});
