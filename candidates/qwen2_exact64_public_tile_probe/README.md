# Real public M16 one-tile integration probe

This separate local probe addresses the public-entry gap from the M1/M2
standalone arithmetic tests. It uses actual original public21 metadata, a fresh
Host/PhysicalMemory/LoanDenseOwner, the new diagnostic public binding, original
OfficialPrefixOwner and ProfiledMatrixService. No Host state or completion is
fabricated. Only synthetic raw x, gamma0 and wq providers exist.

Fixed case: execute pc0 Norm completely, including physical stores/ACKs, actual
owner result, held/public completion and publication. Then the original
advance_to_request offers pc1 and binds its real M16/Q job in the profiled
Matrix service. The exact64 driver accepts this exact object, streams inputs
from that newly produced n0, emits one 64-output tile and receives four 64-byte
write ACKs. Abort before accepting the next weight read. The generator has
cleared the next partial tile but executes no FMA for it. This is one emitted
and ACKed tile, not an entire Q projection.

Expected actual arithmetic: 98304 exact64 FMAs and 4096 FP32 Adds; zero original
Matrix FMAs/issues. The real failed owner result/completion/launch result must
retire through Host handshakes. qraw stays unpublished. Original n0 publication
and canaries remain intact. Matrix/A reservations are drained; sticky poison
and reset-required remain explicit. Only after the failed terminal is the first
output tile compared to the pinned full-array exact64 graph on the same actual
produced n0 row and synthetic weights. That control is never an input source.

The probe reuses the source/ELF/compiler-verified binaries from the separately
completed small02 batch. Only --execute requires that explicit private work
prerequisite; default/source/cold checks use static source pins and need no old
work receipts. It does not compile during execution, run attention,
complete public21, run M128, repair gate propagation, or establish hardware
mapping/performance. Scope remains DIAGNOSTIC_SOFTWARE_OWNER / NOT_IMPLEMENTED /
NO_GO. Default invocation prints NOT_EXECUTED. Only the reviewed --execute and
fresh private --out path runs this case.

Budget: CPU30s, AS2GiB, individual file15MiB, observed directory limit15MiB,
final total16MiB; external wall40s supervisor covers the process group. The
observed directory limit is not a filesystem quota. Detailed addresses, hashes,
raw outputs and receipts stay in private work. No source publication itself
claims a successful fullblock result.

## Protocol revision after public01

The first public01 preserved a real completed pc0 Norm and profiled pc1 binding,
but rejected before accepting pc1: the original public Dense Job has no c field.
The new protocol revision uses the original validator convention getattr(c, 0),
with a strict integer-zero check. It does not copy or replace the actual Job or
change arithmetic. Real public Job and explicit malformed third-operand cold
regressions accompany the change. small02 and public01 executed source snapshots
and receipts remain unchanged; the public02 execution used this revision.


## Failed-result test correction after public02

public02 passed the actual one-tile arithmetic/ACK checks and consumed the real
failed completion and launch result. Its final test incorrectly required idle.
The original Host correctly stays locked after sticky Protocol poison. The new
probe requires exactly one consumed launch result, locked Host and retained
reset-required. A cold test exercises this original Host behavior. public02 is
preserved as a failed harness execution. A deterministic offline audit of its
archived source and trace can establish only the public-entry evidence that
preceded that failure. The corrected probe has not been executed. No third
business run is needed or implied. No arithmetic or owner/driver bytes change.

public02 stopped at that final terminal assertion: its final canary check and
in-process source-after check were not reached. Later offline source/trace
verification does not claim that those two execution gates ran successfully.
