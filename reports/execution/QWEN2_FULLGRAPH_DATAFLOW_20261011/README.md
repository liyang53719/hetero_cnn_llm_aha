# Qwen2 fullgraph dataflow software evidence

SUMMARY.json records one frozen-source cold M16 and one cold M128 execution. All 15
stages compare bit-for-bit with the independent saved v0-equivalent baseline. Raw
input, weights, stage payloads and ELF remain outside Git; only source/hash/counter
metadata is committed. Source fragments are delivered through the existing
candidates/qwen2_transposed_dense entry, with packaging-specific tests and identity.
The historical work driver executions are not rebound as newly executed packaged runs.

The complete native numerical gate and FP32 final gate remain FAIL. No RTL, Chisel,
actual iDMA or leaf pipeline was executed. The 131,727,360-byte ledger combines eight
modified-owner software counters and eleven source-event formulas. The conditional
71.3456% ideal-payload upper bound is neither a measured MAC utilization nor a feasible
full-cycle prediction. See the Chinese design note for fixed capacities, routing costs,
CPU timing, failure semantics and the next actual Chisel integration dependency.

Reproducible entry (ordinary software only):

```sh
PYTHONPATH=src:scripts python candidates/qwen2_transposed_dense/fullgraph_dataflow.py summary --out work/dataflow-source-summary
PYTHONPATH=src:scripts python candidates/qwen2_transposed_dense/fullgraph_dataflow.py small --out work/dataflow-small
PYTHONPATH=src:scripts python candidates/qwen2_transposed_dense/fullgraph_dataflow.py prepare --out work/dataflow-prepared --baseline-root work/qwen2_rectangular_numeric_20261011 --arena work/qwen2_block_recipe_m128_release_20261011/readonly_arena.f32le --small-receipt work/dataflow-small/SUMMARY.json
PYTHONPATH=src:scripts python candidates/qwen2_transposed_dense/fullgraph_dataflow.py run --out work/dataflow-prepared --tokens 16
PYTHONPATH=src:scripts python candidates/qwen2_transposed_dense/fullgraph_dataflow.py run --out work/dataflow-prepared --tokens 128
```

The raw arena and independent comparison artifacts must first exist with the exact
checked identities. See the prior rectangular numeric and transposed dense evidence
for their source-pinned preparation. Each output directory must be new; the run
commands are explicit, have a 180-second bound, and never automatically retry.
The tiny packaging test does not satisfy the full small-suite prerequisite.
Publishing the entry does not authorize calling an unexecuted run a PASS.
