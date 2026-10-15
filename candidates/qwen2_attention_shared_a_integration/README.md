# Shared existing A-bank KV loan, small model integration

This sibling preserves the published resident owner and all original live PV32
arithmetic functions. It changes only supply and admission. `LoanDenseOwner`
constructs the original DenseReductionOwner, original A/B Banks and TileBank,
then installs a guarded view of that same A allocation in both Dense and Tile.
`banked_scratch` gives the unchanged resident scratch a `BankByteView` of those
cells. It allocates 512 bytes of valid metadata, no second A payload bytearray.

## Actual connection and remaining public-launch boundary

`SharedALoanRouter` joins real Dense/Tile, real resident PV32, real Matrix/Scalar,
and a producer-publication authority. Its small check runs the actual
OfficialPrefixOwner KvAppend, accepts every physical test-Bus write/ACK and its
owner terminal, publishes that parent, then feeds its two views to Attention.
This is synthetic M1/M2 producer completion, not the original public21 prefix.

The source-defined `PublicKvPublication` instead requires the actual
PublicExecution/PhysicalMemory objects, ten accepted prefix completions through
pc9, the pending original fused pc12 request, same fixture and parent KV region,
exact write/ACK coverage, original publication hash and epoch. Its constructor
has NOT been executed through public21. One cold unit tests only its continuous
validator using a real PhysicalMemory allocation and accepted writes; that unit
explicitly bypasses the constructor, uses a test host, and cannot establish a
public prefix checkpoint. It also confirms the constructor rejects that host.

The original `PublicExecution.attention_edge` ticks Attention before idle Dense,
whose Tile tick resets A bank ports. This sibling's router instead clocks idle
Dense/Tile FIRST exactly once, then routes the local cache access on that same
edge. The existing default public runner is not silently patched. Its exact
PV32 constructor/driver type pins need an explicit caller selection for this
new LoanDenseOwner and router; no public21/fullgraph continuation is claimed.

## Admission, clock and debt

Before arm, real Dense/window/tile/DMA/seed state, prefix, DDR, Matrix, Scalar and
local obligations must be drained; retained Dense/tile leases are rejected.
The producer authority is inspected, never replaced with a caller success bool.
Every lease edge asserts continued exclusion. Direct normal Dense tick calls
return no accepted job/window/drain handshake. Direct Tile tick and A-bank
read/write/begin_cycle calls outside the router actor/edge raise LoanFault.
The internal clock-only Dense call accepts NO external inputs. scope/edge are
internal simulation scheduling interfaces; Python private-field tampering is
not a security boundary. Per-call original loan flags are not mutated globally.

GuardedBanks explicitly validates canonical integer indices/data and one read
and one write per bank per edge before delegating to original Banks. These
checks survive Python -O. Port snapshots and `words` immutable tuple snapshots
are host debug observations, not cache operands or production read routes.

Accepted local operations retain the published scratch's minimum one-edge
response, stable backpressure and consume ACK. A bank route ValueError or
AssertionError poisons the original owner, leaves the A lease and accepted debts
in place, restores actor scope, then propagates the exception. The caller must
record failure and continue controlled drain; it must never count that edge as
success or immediately restore admission. The fault test injects a second write
on a local-only edge with no external handshake, then proves drain/release.
Abort holds the A lease until local, DDR, Matrix and Scalar drain AND terminal
consume. Only then does normal Dense admission resume.

The small authority hashes the produced KV on every model edge. This is host
validation overhead, not a cache payload read or a hardware-cycle requirement.
Public validation retains the same conservative hash guard. Normal in-flight
Attention DDR traffic is permitted during continuous producer validation;
entry and release separately require the physical port drained.

## Capacity and new route disclosure

Existing A: 16 x 1376 x 32 B = 704512 B (688 KiB). The finite FP32 KV cache uses
262144 B: 4096 x 64 B lines, each mapped to two distinct 32 B bank words among
words 0..511. The rest of A is NOT offered to any other owner during the loan.
Matrix remains its original five contexts / 81920-byte accumulator.

A fill writes two bank words on one model edge. This is an explicit NEW
64-byte/two-bank decode, write route, lease mux and local response interface.
The existing ordinary A ingress exposes a single-bank 32-byte write; this work
has not implemented that new interface in Chisel. Existing per-bank access
budgets are checked, but model edges are not hardware cycles or timing proof.
The unchanged PV32 normal issue count and its low effective lane utilization
remain. This integration does not repair original M128 arithmetic gate failures.

## Bounded checks

Cold checks (no native arithmetic build):

    python -m unittest candidates.qwen2_attention_shared_a_integration.test_cold
    python -O -m unittest candidates.qwen2_attention_shared_a_integration.test_cold

Explicit small execution, fresh PRIVATE work directory only:

    python -m candidates.qwen2_attention_shared_a_integration.check_small --execute --out work/NEW_NAMESPACE

The driver predeclares every case and snapshots source before native build.
Hard limits: one process CPU60s, AS2GiB, each file31MiB and aggregate32MiB, with a
65-second internal wall guard (external timeout must also be applied). It runs
M1/M2 original and banked owners, one stalled M2, and six fault cases. The original
source-bound observer captures all ten intermediate fields; output and observed
payload/coverage/frequency are compared bytewise. Producer output is actual
KvAppend output. Matrix/Scalar counts must remain equal. M128, fullblock, RTL,
CI and original public21 numerical execution are outside this batch.

Detailed receipts, tensors, source/runtime hashes and observation paths stay in
private work. Source publication does not authorize publication of work data.
