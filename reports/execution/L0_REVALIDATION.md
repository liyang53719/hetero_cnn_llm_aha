# L0 revalidation — 2026-08-25

All commands used `taskset -c 8-25`.

- `scripts/sandbox_validate.sh`: PASS; 27 Python tests, C++ reference smoke,
  architecture report, randomized reference sweep, and RTL contract tests pass.
- `scripts/run_dc22.sh`: PASS at 1.0 ns using CLN22UL base SVT typical/max
  0.8 V, 25 C standard-cell `.db`.

| Top | Unmapped cells | WNS (ns) |
|---|---:|---:|
| hetero_npu_shell | 0 | 0.0072276 |
| matrix_engine_int8_tile | 0 | 0.0000277758 |
| cgra_sfu_vector | 0 | 0.000045836 |
| kv_cache_engine | 0 | 0.000173092 |
| hetero_npu_numerical_integration_v0 | 0 | 0.0000975132 |

This is a clean-room, flop-array contract baseline. It is not an SRAM-macro
implementation and does not close canonical L10.
