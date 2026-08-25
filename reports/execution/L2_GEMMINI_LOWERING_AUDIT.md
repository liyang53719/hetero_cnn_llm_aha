# L2 Gemmini lowering audit

`src/heteronpu/gemmini_rocc_lowering.py` is now the project-side encoding
source for the pinned GemminiRoCC primitive operations.  It is transcribed from
the locked `gemmini-rocc-tests/include/gemmini.h` macros:

- `mvin` / `mvout`: `gemmini_extended_mvin` and
  `gemmini_extended_mvout`;
- `preload` / `compute`: `gemmini_extended_preload` and the two
  `gemmini_extended_compute_*` forms;
- configuration: `gemmini_extended3_config_ex`,
  `gemmini_extended5_config_ld`, and `gemmini_config_st`;
- command opcode: `XCUSTOM_ACC=3`, therefore RISC-V `CUSTOM_3` (`0x7b`), not
  the legacy clean-room adapter's `CUSTOM_0`.

The lowerer has a resolved, typed single-tile INT8 output-stationary descriptor
view.  It emits the same configuration/load/preload/compute/store ordering as
the official basic OS C test pattern: `config_ex` uses literal unit C/A
strides, while tensor row strides are emitted only by subsequent `config_st`
and `config_ld` operations. It retains literal local-address bits supplied by the
descriptor allocator, and does not emit a fake RoCC response as completion.

The resolved single-tile OS path now also passes a retained-RocketTile test:
official macros and raw-lowered commands run in one GemminiRocketConfig ELF,
commit matching payloads, and produce bit-exact equal outputs/checksum. See
`L2_GEMMINI_RETAINED_ROCKET_EQUIVALENCE.md`.

The same retained RocketTile now covers single-tile OS, multi-tile OS/WS,
mvin/mvout edges, padded convolution, bias and requant/ReLU. A dedicated
CUSTOM_3 program adapter also passes randomized-ready, busy completion and
illegal-first-packet RTL tests. A bind monitor proves actual generated Gemmini
busy transitions for four retained-Rocket programs. Production
descriptor-sequencer integration remains open.

Verification: `PYTHONPATH=src taskset -c 8-25 python3 -m pytest -q
tests/test_gemmini_rocc_lowering.py` (10 PASS).
