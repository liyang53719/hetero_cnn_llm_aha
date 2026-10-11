# Public Host workspace lease candidate

This default-off source layer connects the existing public Host launch to the
already validated chunked Down owner. It changes the actual
`HostBlockCommands`, `HostBlockTop` and `HostBlockCollection` source in the
frozen composition. It does not create another Matrix, SRAM or iDMA path.

## ABI and admission

`enableTransposedDown=false` preserves all four ordinary permission regions.
Existing drivers leave region 3 empty. The 833-bit `HostCommandLaunch`,
130-bit `Region`, Command128, typed descriptors and `MatrixAux.bias_index`
are unchanged. Region and Host launch are local adapter interfaces introduced
in commits `417541b23c31820191cd7786dc94b8c1798301f1` and
`ef1fa9764bf430e0f376f3d6566d9ac388a50811`; they are not an upstream hardware
promise that a fourth region is reserved.

In the explicit enabled profile:

- Region 3 is a nonempty, 64-byte-aligned, readable and writable workspace.
  Its exclusive limit is at most 2^56. All four regions remain pairwise
  disjoint; command/descriptor tables cannot overlap this workspace.
- Typed tensor permissions, initial readonly liveness, readonly/readwrite
  checks and table permissions exclude region 3. Every ordinary source and
  destination must belong to the first three regions. A write-only ordinary
  destination remains legal under the existing plain Dense contract.
- The accepted launch's existing cfg register snapshots the lease. No live
  launch pin or private address supplies the owner. Internal lease generation
  is the widened `epoch + 1`, so epoch 65535 produces 65536. This identifies
  an accepted request; it is not a checkpoint or cross-reset freshness proof.
- The internal split limit is 2560, an explicit elaboration policy. Selected
  Dense work requires M16 or M128, N divisible by 32, K divisible by 16 and
  at most 8960; native BF16 A additionally requires K divisible by 32.
  The existing dtype/policy checks remain. Native QKV uses the actual token
  window and projection dimensions rather than the full tensor declaration.
- For K > 2560, capacity is `(N/32)*16384` bytes. Full Down N1536 needs
  786432 bytes of external workspace. Single-chunk jobs still need a real
  nonempty lease, but do not reserve an unused N-dependent prefix allocation.
  This allows N8960 single-chunk work to share the same Down lease.

The top profile requires the existing pipelined, weight-read-16 configuration.
It is compatible with ordinary Qwen2 or the existing V/QKV source profiles;
GDN and QK Norm/RoPE/Attention profiles remain excluded by the selected kernel.
The optional internal workspace output is 173 bits and reaches the actual
selected Down owner. Existing burst and write ports still reach one
`RetainedIdmaWeightBurstAdapter`; metadata shares the same two-client hub.

## Lifetime and failure

The cfg snapshot stays owned through all commands, owner terminal ACK,
completion backpressure and final Host result ACK. Composite command, owner,
hub and DMA poison gates both sides of the next launch handshake. Existing
read/response/write/seed ACK drain wiring is unchanged.

The public Host interface has no abort port. Owner-detected errors retain the
previous Down drain rules, including accepted seed retirement after Matrix
done. A failed partially overwritten prefix is not a restart checkpoint.
Reset must coordinate Host, DMA, service and retained leaves; resetting only
the parser does not certify that stale external traffic disappeared. Neither
this model nor the generation field proves freshness against arbitrary
unsolicited cross-job responses from a backend violating its port contract.

## Evidence and limits

`check_frontend.py` composes exact frozen source and patches, checks all 87
locked jars and pinned HardFloat, and typechecks 85 actual Scala sources,
including the complete Host top and Qwen owner kernel. Six small CHIRRTL
cases elaborate the real command parser and metadata readers. Ordinary and
QKV disabled cases exactly match the normalized frozen baseline. No complete
top is elaborated, and no RTL, simulator or floating-point hardware runs.

The bounded parser uses eventSlots32/maxCommands21. Its enabled and disabled
register inventories match: HostBlockCommands 131/35226 bits,
Record128Reader 6/334 and TypedTensorReader 7/1278. The existing 833-bit cfg is
reused. This proves zero added registers for these configurations, not zero
area: address arithmetic/comparators, permission selection and poison gates
are new combinational logic. The prior Down resource ledger remains fixed:
768 KiB in 32 physical banks, one 4096-MAC array and five accumulator contexts.

`model.py` models the changed admission/publication slice after existing
typed-policy decoding, reusing the SHA-pinned physical Down port model.
It does not decode the whole Command128 table or model Matrix arithmetic.
Seventeen tests cover old empty/fourth-region behavior, bounds/alias/permission,
snapshot and epoch, same-owner two-command actual ACK-backed memory reads,
last-ACK/completion backpressure, prefix-error seed drain, late seed ACK,
poison and coordinated reset, successful relaunch with a different lease,
epoch zero, and changes to every region-3 input while busy. The executable
Host model covers plain FP32 A/D; native V/QKV has source/parser checks only.
The late seed test injects into the owner model to check Host poison admission;
it does not prove physical late-ACK routing through an inactive kernel.
Matrix values in these control tests are opaque
finite wire tokens. Decoded-job rejection is labelled `Rejected`, without
claiming bit-exact decoder error-code precedence. Eleven source/frontend
tests protect the real source composition, interface and resource contracts.

The full Down numerical model from commit
`eaed93d8b200d9e3d059a00678a07b2fcb7076b6` remains separate, unchanged evidence:
M128/K8960/N1536, 196608 FP32 outputs, exact independent increasing-K and
saved full-graph comparison. This Host layer has not rerun or inherited an
end-to-end Host numerical pass. Full Host/owner/iDMA handshake execution,
FFN shared residency, whole-block M128 and native quality acceptance remain
open. The original native M128 and FP32 terminal failures are unchanged.

Three prefix sweeps reuse the same 786432-byte external allocation. The
prior full Down model counted 2359296 bytes each of prefix reads and writes;
those bytes remain in real shared iDMA bandwidth and full-wall-cycle cost.
The full-graph 131727360-byte ideal traffic bound, 71.3456%, is still an upper
bound before other costs. It is not measured utilization or a feasible cycle
prediction. The fixed denominator remains 4096 times all accepted-to-terminal
cycles, including wait, Scalar, memory and fault handling as separately scoped.

## Reproduce the bounded gate

Run `python -m unittest discover -s candidates/qwen2_resident_matrix/transposed_host
-p 'test_*.py' -v`, then run `check_frontend.py --out NEW_DIRECTORY --cache
PINNED_JAR_CACHE --hardfloat PINNED_HARDFLOAT_CHECKOUT`.
The source checker never downloads missing dependencies. The existing CI
preparation supplies them. All source/patch/postimage hashes and compact
validation receipts are in `source_pins.json` and `delivery_manifest.json`.
Raw captures, generated IR, jars, binaries and weights are not committed.
