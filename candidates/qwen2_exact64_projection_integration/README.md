# Exact64 streamed projection diagnostic owner

Scope: **DIAGNOSTIC_SOFTWARE_OWNER**, hardware mapping **NOT_IMPLEMENTED**,
performance **NO_GO**. This is the approved numerical-closure adapter, not a
MatrixStream implementation or Chisel prefill acceptance. No original published
arithmetic, thresholds, failed receipts, or other source files are modified.

## Arithmetic and bounded operands

The new C entry points include the pinned published exact64 source and preserve
its exact graph: increasing k, residue (k modulo 64), 24 FMAs per partial, register
fold offsets 4/2/1, lane fold offsets 4/2/1 and explicit final FP32 +0. The same
fmaf function and compiler floating-point flags are retained. The stream performs
real native FMA/Add operations; counters increment alongside those operations.
Raw output is FP32. Existing public Bias/RoPE remains separate and unchanged.

Each tile has 64 outputs and 64 FP32 partials/output = 16384 bytes. The owner also
has one 6144-byte n0 row, one 128-byte weight tile and one 256-byte sealed output.
Including explicit native/bytes conversions and request/response holds, the
conservative logical arithmetic payload ceiling is 23552 bytes. No complete
layer W or complete multirow n0 is supplied to the native arithmetic entry point.
Python object overhead, the original Dense/Banks, PhysicalMemory, and independent
post-terminal test control are outside that arithmetic-payload count. Existing
DenseSource integrity audit temporarily copies the entire n0 span at entry/exit
(786432 bytes at M128); this is provenance auditing, never arithmetic input.
No claim of a 23552-byte process limit or current hardware bank allocation is made.

Every tile streams two 64-byte W beats for every k. n0 is loaded once per row.
After all k, four raw output writes must each receive successful matching ACKs
before the tile is retired/reused. At M128, Q/K combined perform 352321536 FMAs,
14680064 Adds, 704643072 weight read bytes, 1572864 activation read bytes and
917504 output write bytes. This deliberately inefficient serial diagnostic
schedule is not a performance optimization.

## Public interface

- `compile_library(path)` creates a fresh library, checking pinned arithmetic.
- `Exact64Kernel(path)` owns one bounded partial set.
- `Exact64ProjectionOwner(kernel, max_rows=128)` offers `ports`, `tick`, `report`.
- `Exact64PublicDriver(x, physical, job, projection_owner, final_ack_stall=5)`
  offers `tick` and `run`, admitting only original public pc1/pc4 job objects.

The driver retains the actual PublicExecution Host, PhysicalMemory and original
LoanDenseOwner/Banks. It validates original job/allocation/epoch/dtypes and n0
publication. A guard lease blocks direct Dense/window/Tile/Banks entry points.
One original Dense/Tile clock owns each A begin_cycle. The existing Matrix is
exclusively reserved and released only after owner terminal acceptance; zero
MatrixStream steps or native Matrix FMAs are claimed. The new software arithmetic
ledger is separate. Original Scalar/PV32/V/tail work is not rewritten here.

A mismatched tag or noncanonical response does not retire an accepted debt.
The owner poisons and retains the exact request until its matching response.
Abort after acceptance stops new work and drains accepted memory. Abort before
driver acceptance cancels without acquiring resources or inventing a result.
A matching malformed/error ACK may terminate the owner with failure, but cannot
clear actual PhysicalMemory.pending or release its associated quarantined lease.
An external exclusivity violation raises with leases/debts retained; a caller
must stop and perform coordinated drain/reset, not resume normal success.

## Bounded tests and evidence boundary

`python -m unittest candidates.qwen2_exact64_projection_integration.test_cold`
and the same command under `python -O` run protocol/source gates without native
arithmetic. The type-correct cold kernel shell is explicitly metadata-only.

`python -m candidates.qwen2_exact64_projection_integration.check_small` defaults
to NOT_EXECUTED. The opt-in `--execute --out <fresh private work directory>` has
CPU60s/AS2GiB/file31MiB/total32MiB limits. An external wall75s timeout must cover
compilation and every child. Cases are fixed before execution: M1/Q, M2/K,
M1/K stalled; abort/foreign response on a read and write; short final ACK.
Inputs are deterministic synthetic BF16, including cancellation, varied exponents,
signed zero and subnormals. Successful streamed output is compared bitwise only
after terminal to the included frozen full-array exact64 control.

The small driver services actual PhysicalMemory commands/data/ACKs and actual
base MatrixService reservation plus LoanDenseOwner exclusion. M1/M2 cannot
enter the original ProfiledMatrixService Dense binding (M16/M128 only), so this
small harness does not claim that binding. The public driver still uses the
real Profiled service already bound by original advance_to_request. It uses an explicitly
synthetic fixture with readonly n0. It does not execute public21/Norm, prove
production prefix publication, run M128 or fix the historical four numerical
failures. Public adapter construction/negative checks and this local same-graph
comparison are distinct evidence. A full-run runner/authority adapter is owned
by the independent sibling `qwen2_exact64_diagnostic_fullblock`.

All detailed inputs, output bytes, addresses, shapes, hashes and local receipts
are private work artifacts. Only strict aggregate schemas may be published.
Model ticks/host time are not hardware cycles. Existing Scalar port lower bounds
and unrealized hardware scheduling remain independent NO_GO conditions.

The first small01 attempt stopped at the original missing Dense-binding gate
before accepting a projection job or operand. Its source/receipt remain private
and unchanged. The revised base-service synthetic test is a new execution.
