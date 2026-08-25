# Implementation status

## Completed in the current sandbox

| Item | Status | Evidence |
|---|---|---|
| Architecture/config/ISA/descriptor contracts | PASS | `configs/`, `spec/` |
| 128-bit command pack/unpack | PASS | `tests/test_command.py` |
| INT8/BF16/W4 matrix functional model | PASS | `src/heteronpu/matrix_engine.py` |
| CNN im2col path vs direct convolution | PASS, exact | `tests/test_matrix.py`, `tests/test_workloads.py` |
| CGRA/SFU numerical functions | PASS | online softmax, RoPE, Norm, activation, pool tests |
| Paged KV BF16/INT8 | PASS | append/read/free/prefix/fork/COW/invariants |
| Toy Transformer block | PASS | BF16 paged path exact; INT8 KV within frozen threshold |
| Analytical task/cycle scheduler | PASS | CNN, q384 prefill, context4096 decode reports |
| Randomized reference sweep | PASS | 100 GEMM + 40 Conv + 100 Softmax + 1200 KV commands |
| Independent C++17 smoke | PASS | INT8 GEMM + paged KV |
| Clean-room RTL source | PRESENT | FIFO, matrix/SFU/KV contracts, command shell, L5/L6 scoreboard/adapters/shared L2 |
| RTL structural checker | PASS | 9 modules; delimiter/module checks |
| Upstream reproduction scripts | PRESENT | Gemmini, AHA, iDMA, IMAX3 |
| Icarus/Verilator compilation and contract simulation | PASS | `scripts/run_open_rtl.sh`; six testbenches pass |
| L5/L6 contract integration | PASS | event wait/signal; 10,000 shared-L2 transactions |
| L7-L11 model regression | PASS, model-level | `reports/l7_l11_model_regression.json`; 100,000 KV commands |
| L11 integrated clean-room RTL/model regression | PASS, scoped | `reports/l11_integrated_rtl_model_regression.json`; q128/q384/decode4096/continuous model cases plus concurrent Matrix/SFU/KV RTL, 20 measured cycles |
| Verilator lint | PASS | Verilator 5.050 in `work/toolchain/conda` |
| CIRCT/firtool | AVAILABLE | `work/toolchain/riscv/bin/firtool`, CIRCT firtool-1.75.0, user-scoped install |
| DRAMSim2 runtime library | PASS | `work/upstream/chipyard_gemmini/tools/DRAMSim2/libdramsim.a`, rebuilt `-fPIC` for Conda PIE link |
| Upstream clone/lock | BLOCKED_PARTIAL | Chipyard commit present; 5 submodules uninitialized and 42 shallow/non-exact; see `reports/upstream_progress.json` |
| Yosys | AVAILABLE | 0.9 unpacked under `work/toolchain/apt-yosys` |
| 22nm DC contract smoke | PASS | TSMC CLN22UL SVT `.db`; five tops including integrated numerical shell, 0 unmapped, positive 1.0 ns slack |
| RISC-V compiler/Spike smoke | PASS | GCC 10.2 bare ELF + Spike 1.1.1-dev 20-instruction run |
| RISC-V proxy kernel | BLOCKED | Ubuntu toolchain lacks Chipyard libgloss/crt0 contract |
| Gemmini software compile | PASS | clean minimal Chipyard/Gemmini tree produced libgemmini and bare-metal binaries |
| Gemmini Spike extension gate | PASS, targeted | `work/results/gemmini_baseline_minimal_v3/spike_mvin_preload_full.log`, `spike_matmul_preload_full.log`; Spike loads `libgemmini.so` + `libcustomext.so` together |
| Official GemminiRocketConfig RTL/elaboration | PASS | `work/upstream/chipyard_gemmini/sims/verilator/generated-src/chipyard.harness.TestHarness.GemminiRocketConfig/gen-collateral`; CIRCT firtool-1.75.0 emitted split Verilog |
| Official Gemmini Verilator simulator | PASS | `work/upstream/chipyard_gemmini/sims/verilator/simulator-chipyard.harness-GemminiRocketConfig`; Verilator 5.050, 650 modules |
| Official Gemmini interface audit | COMPLETE, integration boundary identified | `reports/OFFICIAL_GEMMINI_INTERFACE_AUDIT.md`; generated Gemmini is a 157-port RocketTile RoCC/PTW/TileLink client, not a direct 128-bit standalone macro |
| Official generated Gemmini MacUnit regression | PASS, exhaustive primitive scope | `reports/official_gemmini_micro_regression.json`; 327,680 signed INT8/accumulator checks against the pinned generated `MacUnit.sv` |
| Official generated Gemmini MacUnit TSMC DC | PASS, primitive scope | `work/results/dc22_tsmc_svt/official_gemmini_macunit/status.txt`; 0 unmapped, 1 GHz WNS `0.000536978 ns` |
| Gemmini 128-bit to RoCC wrapper contract | PASS, wrapper-only scope | `work/results/open_rtl/tb_gemmini_rocc_adapter.log`; legal/illegal translation and response event pass in 6 cycles |
| Gemmini RoCC wrapper TSMC DC | PASS, wrapper-only scope | `work/results/dc22_tsmc_svt/gemmini_rocc_adapter/status.txt`; 0 unmapped, 1 GHz WNS `0.0107245 ns` |
| Gemmini RoCC shell-level integration | PASS, wrapper-only scope | `work/results/open_rtl/tb_gemmini_rocc_integration.log`; command scoreboard/shell/Matrix-RoCC and SFU event path pass in 12 cycles |
| Gemmini RoCC shell-level integration TSMC DC | PASS, wrapper-only scope | `work/results/dc22_tsmc_svt/gemmini_rocc_integration/status.txt`; 0 unmapped, 1 GHz WNS `0.000330031 ns` |
| Official Gemmini mvin/mvout RTL run | PASS | `work/results/gemmini_baseline_minimal_v3/verilator_mvin_mvout.log`; `$finish`, 669 us simulated, 39.6 s walltime |
| Official Gemmini FAST matmul RTL run | PASS | `work/results/gemmini_baseline_minimal_v3/verilator_matmul_fast.log`; all transpose/dataflow combinations, `$finish`, 2 ms simulated, 119.3 s walltime |
| Official Gemmini matmul OS RTL run | PASS | `work/results/gemmini_baseline_minimal_v3/verilator_matmul_os.log`; official N=2 output-stationary workload, `$finish`, 10 ms simulated, 583.96 s walltime |
| Official Gemmini matmul WS RTL run | BLOCKED_TIMEOUT | `work/results/gemmini_baseline_minimal_v3/verilator_matmul_ws.log`; official N=2 weight-stationary workload reached 10,000,001-cycle TestDriver timeout without mismatch output |
| Official Gemmini matmul WS historical 20M-cycle log | UNVERIFIED_HISTORICAL | `work/results/gemmini_baseline_minimal_v3/verilator_matmul_ws_20m.log` has `$finish` but no captured command or binary hash; fresh canonical 10M run timed out, see `reports/execution/L1_GEMMINI_WS_AUDIT.md` |
| Official Gemmini FAST matmul WS RTL run | PASS, targeted | `work/results/gemmini_baseline_minimal_v3/verilator_matmul_ws_fast.log`; official WS source with `FAST=1`, `$finish`, 1 ms simulated, 72.38 s walltime |
| Official Gemmini default matmul RTL run | BLOCKED_TIMEOUT | `work/results/gemmini_baseline_minimal_v3/verilator_matmul.log`; reached output- and weight-stationary phases, then TestDriver timeout at 10,000,001 cycles |
| Official Gemmini default matmul 20M-cycle RTL run | BLOCKED_TIMEOUT, workload budget | `work/results/gemmini_baseline_minimal_v3/verilator_matmul_20m.log`; reached multiple transpose/dataflow combinations, then timeout at 20,000,001 cycles without mismatch |
| Stage gate ledger | CURRENT | `reports/stage_gate_status.json`; L0/L5-L6/L7-L10 and scoped clean-room L11 closed, L1-L3 plus official full-chip L11 remain open |

## Deliberate non-claims

- The clean-room matrix RTL is a small interface/verification target, not a replacement for Gemmini.
- The clean-room KV RTL implements basic append/read/free only; the Python model covers prefix/fork/COW semantics, while production refcount/COW/gather hardware remains a local stage.
- Cycle reports are analytical and are not labeled as RTL-measured.
- W4 storage-only mode does not double MAC throughput. 4096 effective MAC/cycle is a native dual-dot target.
- Official Gemmini macro-level RTL generation and targeted mvin/FAST matmul runs are now proven; the clean-room integrated numerical gate is also closed at its stated scope. No hetero_npu top equivalence, full-size default matmul completion, AHA equivalence, or full numerical macro-RTL co-simulation is claimed yet.
- The DC smoke synthesizes current small contract RTL with flop arrays; it is not the production SRAM-macro implementation.

## Current host revalidation

- L0 Python/architecture validation: 27 tests PASS.
- Independent C++17 smoke: PASS.
- Icarus 11.0/Verilator 5.050 compile and contract simulation: six testbenches PASS; shared L2 reports 10,000 transactions.
- L7-L10 model regression PASS: CNN exact, BF16 q128/q384 exact, KV INT8 within threshold, 100,000 advanced-KV commands.
- TSMC CLN22UL SVT DC smoke PASS for shell/matrix/SFU/KV and integrated numerical shell; integrated shell WNS is `9.75132e-05 ns` with 0 unmapped cells.
- The local RTL result is a contract-level first RTL baseline, not the planned Gemmini/AHA integrated macro RTL.
- All compile/test commands for this revalidation were restricted to `taskset -c 8-25`; this host exposes CPUs 0-23, so the effective affinity was 8-23.
- Official Gemmini/AHA baselines and full numerical macro-RTL co-simulation remain open until upstream lock and official flow prerequisites close.
- First official Gemmini macro-level RTL artifact was produced on 2026-08-25 in the isolated Chipyard tree after installing the locked targeted dependencies, CIRCT firtool-1.75.0, and DRAMSim2; the artifact is a baseline evidence path, not yet the final hetero_npu RTL.
