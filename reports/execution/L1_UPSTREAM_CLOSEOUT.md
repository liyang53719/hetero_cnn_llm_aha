# L1 upstream reproduction closeout — 2026-08-25

L1 is closed only on its original upstream gates; no clean-room evidence is
used for this decision.

| Upstream gate | Result | Evidence |
|---|---|---|
| Gemmini exact closure and generated RTL | PASS | `upstream_closure.json`, clean `chipyard_gemmini` checkout |
| Gemmini Spike mvin/matmul/CNN | PASS | `l1_gemmini/` mvin, OS matmul, and ResNet50 OS logs |
| Gemmini Verilator mvin/mvout and OS matmul | PASS | `l1_gemmini/mvin_mvout_verilator.log`, `matmul_os_verilator.log` |
| Gemmini Verilator canonical N=2 WS | PASS | `l1_gemmini_ws_loadmem_20m/run.log`; native `LOADMEM=1`, canonical source SHA256 `50e85f9988709b9d6f399766788b75aa875e1f0791bae37c7e8d4dbe4649cf63`, binary SHA256 `433566fdf0f6abd5a070dfd1315bc73227cc6de624b52385c1b8acf8943355c8`, `$finish` at 10 ms within the allowed 20M-cycle cap |
| AHA 4x16 Gaussian generation/map/PnR/bitstream/Verilator | PASS | `l1_aha_verilator_5028_cxx10_makeflags/result.json`, bit-accurate comparison |
| iDMA source enumeration and backend read/write | PASS | `reproduce_idma.sh` results and VCS simple job |
| IMAX3 software audit | PASS, non-RTL source | `LICENSE_MATRIX.md` and IMAX3 audit boundary |

`LOADMEM=1` is a native Chipyard loader option that places the same ELF in
simulated DRAM; it does not alter Gemmini RTL, the canonical WS source, binary,
numerical check, or cycle cap. It is required because the default HTIF path
leaves this binary in boot ROM WFI, while the native loadmem path reaches
firmware and completes. The reproducer fixes this setting explicitly.
