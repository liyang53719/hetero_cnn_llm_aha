# L2 descriptor-fetch BLOCKED_DECISION

The frozen command and descriptor schemas define 24-bit record indices,
128-bit records, null index `0xFFFFFF`, immutable in-flight records, acyclic
chains, and a maximum of 16 records. They do not define the RTL fetch
transport, index-to-storage mapping, response/error signaling, or outstanding
policy. Choosing these changes the production matrix-wrapper interface and is
therefore outside autonomous implementation authority.

Recommended contract: a read-only descriptor port backed by Shared L2, with a
24-bit record-index request and a 128-bit record plus error response, both
ready/valid; one outstanding request in L2; deterministic
`byte_address = descriptor_base + index*16`; descriptor base frozen per
context; missing/uncorrectable responses reject the whole command before any
CUSTOM_3 issue. This keeps descriptors in the planned Shared L2 capacity and
does not introduce an AXI master at the matrix wrapper.

Rejected shortcut: host-prelowered micro-op FIFO as the only production path.
It bypasses the frozen requirement that the matrix engine consume typed
descriptors and cannot close L2.

Decision required: approve the recommended Shared-L2 read-only descriptor
port, or provide the intended fetch/storage interface.

Independent work completed while waiting: software legality golden parses
128-bit records and rejects null-required, missing, cyclic, over-16-record,
and out-of-range chains before lowering.
