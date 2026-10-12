# Opt-in Torch210 CPU DEFAULT Norm256 source overlay

Status: **candidate source plus bounded static/symbolic checks only**. This
directory supplies an exact replacement for the existing
`chisel/continuous_prefill/src/main/scala/heteronpu/continuous/QkNorm256Owner.scala`.
It is not a second owner/top, production-source edit, or extra arithmetic unit.
Do not put both Scala copies in the same source set. Production Host callers and
their default constructor remain unchanged; no Host C2 dispatch is connected by
this deliverable.

## Explicit policy and retained contracts

The trailing constructor parameter is `enableTorchDefaultPolicy: Boolean = false`.
Legacy policy `0xc1` is always accepted subject to all original descriptor checks.
Policy `0xc2` (`Torch210CpuDefault256`) is accepted only when that constructor
parameter is true. Every other policy fails the original descriptor path with
`Status.Bounds`, `normStatus=1`, zero writes, and reset required. Enabling the
parameter still permits C1; selection is per job, never per element or value.

C1 retains the original chunk16 balanced trees, serial chunk-root sum, PWL/Newton
inverse, gamma/output arithmetic, literal coefficient ROM, and flag handling.
C2 preserves signed-zero/BF16-exponent95..158 operand admission, nonfinite-before-
finite-range precedence, the fixed FP32 epsilon word `0x358637bd`, address/overlap
checks, opaque Q gate transport, one request outstanding, response tags, memory
error handling, and every norm/gate write-ACK fence. The original domain errors
and reset-required lifecycle are retained. No thresholds are widened.

For C2, BF16 input/weight values are widened exactly. All scalar nodes round
separately to FP32. There is one final BF16 RNE conversion after
`weighted = FP32(FP32(x * inverse) * FP32(1 + weight))`, with the original
conversion flags and rejection rules. No intermediate BF16 cast, fused
operation, native mean/inverse input, coordinate-specific correction, or host
arithmetic result is introduced.

## C2 reduction and scratch lifetime

For vector lane `l=0..7`, residue `r=0..3`, and term `t=0..7`, the existing
8-bit `lane` register is also the input address `32*t + 8*r + l`. Its bit fields
are `[7:5]=t`, `[4:3]=r`, `[2:0]=l`. The original buffered input already supports
this read order. The schedule is serial:

1. Square the selected input using existing Mul1; the result is held in `value`.
2. Add it to the residue accumulator from positive zero using existing Add0.
3. After eight terms, seed the lane accumulator directly from residue0, then
   add residues1,2,3 in that order. This is exactly three residue folds per lane.
4. Add each completed lane to the global accumulator from positive zero,
   strictly in lane0..7 order.
5. Multiply by FP32 `1/256` (`0x3b800000`), add epsilon, request existing Sqrt3,
   then existing Div2 with `(a=1.0, b=root)`. Sqrt's unused `b` is positive zero.

No new accumulator/counter registers are declared:

| Existing storage | C2 meaning and lifetime |
| --- | --- |
| `treeValues(0)` | Current residue sum. Cleared before the first term of every residue, including the first residue of every head/lane. Read only by `torchTermAdd`. |
| `treeValues(1)` | Completed-residue prefix of the current lane. Residue0 overwrites it before the first read in residue1's fold; later folds overwrite it. No stale value crosses lanes. |
| `treeValues(2..15)` | Not used by C2. Retained for C1. |
| `accumulator` | Global lane sum, cleared on each accepted head before reduction. Updated after each completed lane; read for mean. |
| `value` | Immediately preceding scalar result. Carries square→term-add, completed-residue→residue-fold, completed-lane→lane-fold, mean→epsilon→sqrt→divide, and the original output data path. |
| `lane` | C2 input address during reduction. Reset to zero before mean and reused for the original sequential output loop. |
| `treeIndex`, `treeCount` | Retained C1 tree counters; not read or written in the C2 reduction. |
| `seed`, `norm`, `scale`, `coefficient` | Retained C1 inverse scratch; no C2 dependency. |
| `invRms`, `laneGamma` | Original output-stage lifetimes, set before their first use. |

The host-memory state machine is unchanged. New scratch updates happen on
accepted scalar results only. A held scalar request retains its operands, and
head/lane advancement occurs only after the current result is consumed. This
is a source-level lifecycle argument; simulator backpressure/reset testing is
still required.

## Deliberate Div/Sqrt flags contract

The unchanged `BlockScalarFloat` owns the existing
`DivSqrtRecFN_small(8,24,0)`. It provides Sqrt3/Div2 result and error, with
`primitiveFlagsValid=false`; the overlay does not modify it or fabricate raw
flags. Only the two inverse states of an explicitly selected C2 job are exempt
from the owner's raw-flags-presence requirement. They still require no scalar
error and a finite result; the root and inverse must also be positive normal
FP32 values. The existing mean-plus-epsilon range check is retained.

All C1 operations and all C2 Add/Mul operations continue to require valid raw
flags, reject raw flags[4:1] or scalar error/nonfinite results, and OR the genuine
observed flags. Missing Add/Mul flags remains `Status.Protocol`; arithmetic
failure remains `Status.Numerical`, `normStatus=4`. The result's `exceptionFlags`
accumulates observed Add/Mul and BF16 conversion flags only. It makes no claim
to expose or reconstruct the unobservable Div/Sqrt inexact flag. Existing
BlockScalarFloat error already includes Div/Sqrt invalid/divide-by-zero,
overflow, underflow, and nonfinite-result rejection.

## Source, operation, and resource delta

Five operation states are appended to the original sixteen; existing C1 state
numbers are unchanged. The operation register grows from four to five bits
before optimization. No data register/array or loop-counter declaration is
added, and the owner still instantiates zero modules. New logic consists of
policy/opcode selection, operand mux choices, bit-field traversal, reused
scratch updates, and the narrowly scoped result/flags selection. Actual mux
area, post-optimization registers, synthesis/banking, and timing are unmeasured.

| Per admitted H256 head | C1 | C2 | Delta |
| --- | ---: | ---: | ---: |
| Add0 | 515 | 545 | +30 |
| Mul1 | 775 | 769 | -6 |
| Sqrt3 | 0 | 1 | +1 |
| Div2 | 0 | 1 | +1 |
| Total scalar requests | 1290 | 1316 | +26 |

C2 reduction contributes 256 term additions, 24 residue folds, and eight lane
folds: 32 more Add requests than C1 reduction. Its two inverse requests replace
the original two Add and six Mul requests. No extra Scalar/SFU/array/Matrix
instance is needed. With the unchanged shared-scalar FSM, the prior diagnostic
derived +127..129 ideal no-stall cycles per head (+325,120..330,240 over 2,560
heads). Those remain analytic bounds, not measured owner/RTL cycles, throughput,
800MHz timing closure, or an end-to-end speed result.

## Verification performed and remaining gap

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 candidates/qwen35_attention_prefill/torch_norm256_chisel/check_overlay.py
```

`test_overlay.py` exposes the same six checks to the existing
`candidates.qwen35_attention_prefill.run_tests` discovery without running them
or writing files during import. Run just that discovered suite with
`python3 -B -m unittest candidates.qwen35_attention_prefill.torch_norm256_chisel.test_overlay -v`.

Six bounded checks compare the unchanged bundle/register declarations, C1
arithmetic blocks and operand maps, ROM literals, descriptor/domain/transport
and commit logic, and narrow Div/Sqrt flag exemption. An independent nested
expression specification is compared with a symbolic four-state scheduler:
every input appears exactly once, the entire reduction association matches,
poisoned old lane scratch is overwritten before use, final output index is
zero, and the per-head operation counts match the table. These are static source
and symbolic-schedule checks, not a Scala interpreter or arithmetic simulation.

The preceding diagnosis in `work/l3_qnorm_rounding_20261012/REPORT.txt` found the
generic arithmetic recipe matches the fixed Torch2.10.0 CPU DEFAULT native
stages over the 2,560 cold128/carried128 heads. That diagnostic/Python evidence
does not execute this Scala file and is not promoted to Chisel/RTL/Host, full
attention/full-forward, resource, or timing acceptance here.

Scala compilation, Chisel elaboration, and RTL simulation were **not run**.
Read-only inspection found Java but no existing Scala/Chisel jars, compiled
continuous-prefill classes, or HardFloat source in the checked workspace/cache
locations; `OFFLINE_TOOLS` and `HARDFLOAT_SOURCE` are unset. Nothing was fetched
or built. Existing `production_source_identity.py` illustrates the offline
compiler entry point. Reuse requires Scala2.13.16 compiler/library/reflect,
Chisel6.7.0 plus its matching compiler plugin and locked dependencies, and real
project dependency classes or their exact source closure. Full shared-scalar
elaboration additionally requires the pinned HardFloat source.

When those dependencies are supplied, a separate authorized, source-pinned
frontend gate can typecheck this replacement and emit owner-only CHIRRTL for
default/off/on profiles in fresh output directories. A proposed small bound is
two CPUs, 1GiB JVM heap, and 60s total wall time; it is a cap, not a promise of
completion. Do not silently fall back to sbt downloads, firtool, Verilator, or
a full Host build. Frontend success would still leave numeric execution open.

The existing `QkNorm256OwnerSpec.scala` harness provides the real production
BlockScalarFloat, raw flags, held-result checks, fault injection, commit fences,
and reset cases to reuse in a later simulation gate. It is currently C1-only:
its harness needs an explicit constructor option, its job setter needs C2,
and its trace records/assertions must represent flags-valid=false for Sqrt/Div
without inventing flags. Required later cases include C1 parity both with the
option off/on, C2 rejection when off, cold/carried Q/K byte traces, consecutive
mixed-policy jobs, zero/signed-zero heads, faults at Sqrt and Div, missing/failed
Add/Mul flags, held inverse results, and reset while Sqrt/Div are outstanding.
That extension and actual production Host policy wiring are outside this
source-overlay deliverable.
