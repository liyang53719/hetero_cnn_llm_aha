# Exact64 public tile software profile

One bounded local synthetic batch, two fixed cases, no full projection/fullblock.
Both cases use the existing real M16 pc0 Norm, public completion/publication,
pc1 Profiled Dense binding, unchanged Exact64PublicDriver/owner/kernel, original
PhysicalMemory accepted 64-byte reads and successful write ACKs, original Dense
bank exclusion and Matrix reservation. First case times two tiles without a
profiler, recording cumulative one/two-tile and second-tile incremental CPU/wall.
Second case repeats the same stimulus with cProfile around the same two-tile
loop. It measures profiler overhead and checks both actual outputs are identical.
Setup/Norm/binding and abort/Host retirement have separate timings.

Each case actually executes 196608 FMA and 8192 Add, with eight output ACKs
covering 512 bytes. It then aborts before accepting another tile request. The
actual Protocol terminal must drain both reservations and memory, consume the
Host result, retain sticky reset/locked state and leave partial qraw unpublished.
Zero original Matrix arithmetic issues are invented. Synthetic host input arrays
are explicit fixture storage, not additional arithmetic-owner resident buffers.

The executed native binaries are reused only after fixed prior RESULT, ELF,
source and original compiler-receipt checks. No compilation, external data,
weights download, oracle/reference call or source mutation occurs. Cold/default
entry checks tracked source closure without opening private work. Detailed
profiles, source identities, addresses and outputs remain private work.

Single-run limits: 20 CPU seconds, 2 GiB AS, 30 seconds external wall, 8 MiB final
output, with observed 7 MiB output stop (not a filesystem quota). The supervisor
cleans the complete process group on normal exit, failure or interruption. All
fixed cases or an incomplete failure remain visible; no automatic retry.

Results are software timing, never hardware cycles. Extrapolation from two small
Q tiles is conditional, excludes other stages and cannot identify where the
previous untimed fullblock hit its 3300-second wall. DIAGNOSTIC_SOFTWARE_OWNER,
hardware mapping NOT_IMPLEMENTED, performance NO_GO remain explicit.
