# A demo library

The small examples of toa have no symbols, no RNL drawings and one evidence record. These drafts
make a library that has more, for the preview and the tests of Gazettoa:

- two interfaces with a `symbol.rnl` each (`inv`, `buf2`);
- four circuits of `inv`, of two transistors each: `cmos.g1`, drawn; `cmos.g2`, the next
  generation of it, with a wider p-channel transistor; `cmos-x2.g1`, twice as wide, and
  `cmos-lp.g1`, with long channels, both made from `cmos.g1` (`base`) under names of their own, so
  each starts a series of its own (TOA 3.4). One circuit of `buf2` is made of two instances of
  `inv`, drawn with the symbol of `inv`;
- `cmos-copy.g1`, by another author: the netlist of `cmos.g1` byte for byte, without `base`.
  `examples.py` publishes it a day after the others, and the site marks it: same files, lineage not
  declared (decision B35);
- a testbench of `inv` (`tb_inv_char.g1`: delay and power) and five evidence records of the
  circuits of `inv`, for the selection table. Two records of `cmos.g1` at 1.8 V disagree on power.
  The values are made up;
- a frozen library `gaze-demo.g1` (type `lib`), whose list of members names every other object
  published on the first day, in the groups `inv` and `buf2`.

`scripts/examples.py` copies them into a new git repository, seals them with `toa seal`, publishes
them with `toa publish` and adds the library to the preview's workspace list as
`gaze-demo`. Then it marks one generation of each series latest in the library list, as a
maintainer does by hand (`cmos.g2`, not `cmos.g1`; `cmos-copy.g1` is left unmarked), and publishes
`cmos-copy.g1` a day later. The netlists were solved once with `rnl solve`; their drawings are
complete.

An object holds no model card (`toa/spec/types/en/ckt.md`, checks at sealing, item 3): the types of
the transistor models `nch` and `pch`, which RNL needs to draw them, are given by `@DEVICE` in the
header record of each netlist. The testbench includes neither `inv` nor the models; assembling a
record adds them (TOA 7.6).

All files here are CC0-1.0, as every object says in its `license`.
