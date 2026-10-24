# Qwen3.5-0.8B private chunk64 contract, source only

This independent proposal adds two Scala source files. It does not modify any
public decoder, M1 recurrent owner, existing Host persistent-root fence, physical
Vector interface, numerical service or production candidate.

`GdnChunkProtocol.scala` defines fixed H16/Dk128/Dv128 M16/M128 jobs and private
staging receipts. No Module/owner, Decoupled execution port or publication action
is added. `GdnChunkAddressPlan.scala` is an immutable BigInt plan for elaboration
and contract checking, not an implemented RTL address generator or ACK tracker.

The 24 matrices use the exact pinned head-major SSA allocation. M16 has one
64-row internal chunk with 48 padded rows; M128 has two full chunks. Per-head
chunk storage is 806,912 bytes. Total scratch is 13,959,168 / 26,869,760 bytes.
StateIn/stateOut are each 1,048,576 FP32 bytes. All five complete spans must be
aligned and disjoint; even cold stateIn retains a declared disjoint span.

The coarse phase list preserves the existing software's serial head/chunk
order. `DerivedAndPair` retains the source's row-interleaved exp/products/pair
micro-order; it is not permission to move all row products ahead of all exp
calls. Chunk1 uses the same head's private chunk0.next_state after that chunk's
output phase, never external stateOut. Every declared stage waits for exact
successful ACK obligations before its successor. No producer of those real
ACK receipts exists in this batch.

Receipt definitions intentionally contain no stateCommitted or advanced
generation field. A complete chunk staging result alone cannot publish a
persistent root. Existing HostBlockCommands terminal fence remains the root
owner and also requires Conv history, final residual, correct identities and
retired obligations. This package does not replace or connect to that fence.

Numerical order remains a declared requirement: separate FP32 RNE Mul then Add,
ascending K from +0, unit-diagonal forward solve, no FMA, state never BF16.
Vector exception policy IDs do not claim either a new port or new hardware
policy. Existing legacy/finite-gradual-underflow behavior still requires its
own physical integration and numerical qualification. No arithmetic is tested.

## Proposed limited controls

Use target CPython 3.12.14 with `-I -S -B`, `tests.py --repo <fixed-source-root>`.
The caller must pin this package manifest before invocation. The test checks
all package and 24 source dependency pins before any controls and again after.
It extracts Scala shape/phase literals and pinned Python AST literals without
executing either candidate. Other formula checks use a separately written
Python model. This does NOT execute/compile the Scala methods or prove Scala
formula/RTL equivalence. Compilation/elaboration remains a separate gate.

The 17 unittest groups cover M16/M128, padded/64-boundary layout, complete
state/region sizes, aliases/overflow, cold/carried roots, exact SSA allocation,
phase dependencies and final ACK/fence rules. ACK tests use only MockAckContract,
which accepts hypothetical receipt fields, not actual Chisel bus handshakes.
They must not be described as real ACK, arithmetic, prefill or throughput tests.

Limits: one CPU, 256 MiB address space; 8 s CPU soft / 9 s hard; 9 s internal
wall alarm within a separately enforced 10 s outer limit. No child processes,
network, ctypes native load or file writes are allowed by the test audit guard.
The wrapper alone captures small stdout/stderr in a fresh directory. No test
was executed by the author before independent review/root admission.

Existing M1 public/recurrent and Host dual-root fence sources remain pinned and
unchanged. The 24 witnesses match fixed remote commit
adefaa78c2d313d9927b4e87550dddc926b3c605; a local mutable HEAD is not its identity.
No new model run, Scala compilation, RTL generation or Vector resource is
authorized by this package. Qwen2's UNKNOWN execution/cleanup is unaffected.
