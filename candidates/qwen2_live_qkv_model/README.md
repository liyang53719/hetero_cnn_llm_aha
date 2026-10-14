# M16 public QKV software gate

Source-only, explicit opt-in. The default is `NOT_EXECUTED`: no inputs, build,
Torch, reference generation, Chisel, RTL, EDA or network request.

## Cold checks (Python 3.12, standard library only)

Run from the checkout root:

```
python -B -S -m candidates.qwen2_live_qkv_model.runner
python -B -S -m unittest candidates.qwen2_live_qkv_model.test_gate -v
python -B -O -S -m unittest candidates.qwen2_live_qkv_model.test_gate -v
```

`pins.json` freezes the original execution dependencies. Existing source guards,
numerical contract and input recipe pins are not rewritten. Cold CI does not
install packages or download fixtures. Full input construction is the separate
published `candidates/qwen2_live_qkv_inputs` recipe. This package only consumes
an existing valid recipe run containing `raw`, `inputs` and `reference`.

## Explicit actual execution

Requires a local C++ compiler and NumPy. The current receipt records their
actual versions and hashes; it does not claim an old toolchain identity.

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
timeout -k 10s 600s python -B -m candidates.qwen2_live_qkv_model.runner \
  --actual --data work/qwen2_live_qkv_inputs/published7b31_fix_v3 \
  --out work/qwen2_live_qkv_numeric_20261014/package_m16_fresh
```

Replace the data run name with another lawful output of the published input
recipe and select a fresh output name. Outputs must be direct children of the
numeric work directory. Existing destinations and aliases are refused.
The process has a 2 GiB address-space cap and a 570-second model deadline;
the shown outer command bounds the complete process at 600 seconds.

The preflight verifies all eight raw BF16 tensors, nine materialized input
roles, the reference manifest and its nine pinned node identities. Only
`x,gamma0,wq,wk,wv,bq,bk,bv,rope` are physical-memory providers. The original
public21 parser and typed jobs execute pc0..8 through the original service
models. Writable tensors begin poisoned, require exact write/ACK coverage,
and cannot feed consumers before public publication. Official reference tensor
files stay closed until all actual producers are saved at the pc8 boundary.

The gate is an explicit Python-path discipline, not an OS sandbox for arbitrary
native code. The reused, hash-checked C++ service has pointer-only arithmetic
entry points and no tensor file-input API. Compile and source reads are not
model inputs. No arbitrary user-supplied code or library is accepted.

## Post-seal raw cross-check

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
timeout -k 10s 120s python -B -m candidates.qwen2_live_qkv_model.raw_reference \
  --actual-result work/qwen2_live_qkv_numeric_20261014/package_m16_fresh \
  --data work/qwen2_live_qkv_inputs/published7b31_fix_v3 \
  --out work/qwen2_live_qkv_numeric_20261014/package_raw_fresh
```

This derives RMS independently from readonly x/gamma, then uses the original
`dot16.inc` direct row-major K1024+512, pair-high-before-low recipe with readonly
weights. Actual outputs are read only for comparison. Actual Matrix arithmetic
uses `matrix_numeric.cpp` and `numeric_smoke.cpp`; it does not include
`dot16.inc`. Both routes share FP32 FMA/libm and mathematical BF16 rules. Their
loop/layout/reduction code is separate, but low-level FPU primitives are not
independent implementations. RMS reference and actual code both use NumPy
FP32 primitives, with separately expressed reduction schedules.

## Acceptance and boundaries

- All six official producers n0/qr/q/kr/k/v are compared in full with the
  unchanged single-operator contract. Missing, extra or aliased reference
  nodes fail closed; an empty comparison cannot pass.
- qraw/kraw/vraw have no official pre-bias reference. Their finite values,
  exact ACK coverage and schedule are recorded separately. The post-seal
  typed-recipe bit-exact check does not create official raw acceptance.
- pc8 public completion remains held: nine owner terminals, eight public
  completions, V not published, no launch result or final fence. Suffix data
  remains untouched. No full-block or all-node acceptance is claimed.
- `source_correspondence.json` maps the reviewed v5 postimage independently.
  Default-off active core hashes are never renamed to the v5 hashes. This is
  source correspondence, not execution or proof of that hardware postimage.
- Ticks and primitive counts are software observations. They are not hardware
  cycles, timing, synthesis resources or utilization. The slice equivalent
  count is derived from actual FMA calls, not an independently observed slice
  handshake. Read/ACK counts do not supply real DDR latency or bandwidth.
- M128 is not admitted. M16 inputs and the 16-row RoPE table cannot be extended
  with zeros or scaled by eight to claim M128 evidence.

Failed runs remain in their fresh directories. This package contains no raw
weights, generated ELF, output tensors, or log bodies. Original `m16_v2` work
evidence remains separately frozen; its result is not this package's acceptance.
