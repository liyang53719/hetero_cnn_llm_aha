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

Scope deliberately remains limited:

- logical dimensions above 16 and weight-stationary sequence construction are
  rejected until the descriptor allocator and official loop path run inside
  retained RocketTile context;
- this is an encoding/unit-test result, not Gemmini macro numerical or memory
  trace equivalence;
- the next L2 test must execute both the official C sequence and the lowered
  descriptor sequence in the same RocketTile harness and compare writes,
  events, and output bytes.

Verification: `PYTHONPATH=src taskset -c 8-25 python3 -m pytest -q
tests/test_gemmini_rocc_lowering.py` (6 PASS).
