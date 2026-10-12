# Resident act → acknowledged DDR drain

This default-off source increment composes on the published `ffn_window` profile
at c761ec824ce2c027a66c22feb4a2154829f9d545. It adds a separate internal Activation
drain transaction; Gate/Up window results retain their zero-DDR-write meaning.
The successor `ffn_group` is its production Host/coordinator consumer.

## Exact path

The request contains the full Activation job, transaction identity, global ng
and local cols. Slot 2 must already be sealed with matching dimensions and zero
consumed reads. Admission requires M16 or M128, N=K=8960, FP32 A/B/D,
32-aligned ng/cols, 32..160 columns, full-span nonalias/range/alignment checks and
an independent valid workspace. `job.n` remains the global DDR row stride.

One row group is read from the actual tile port in column order and stored in
the existing 16 KiB finalValue registers. At most 16×160×4 = 10 KiB is live.
The same registers are packed into full 64-byte row-major writes at
`dst + (row*N + ng + 16*beat)*4`. Existing cursors and the normal write/data/ACK
machinery are reused. Bursts stop at the row end or the existing physical 1 KiB
boundary. No masked scatter writes or second tensor buffer are introduced.

Bytes are counted only when a matching successful physical write ACK retires.
A row group's hold cannot be overwritten before those ACKs. After all tile reads
and DDR ACKs, slot 2 is released; the next state checks actual release/drain
before publishing an immutable typed result. The retained low A lease remains
valid after success. Ordinary owner/Host done is suppressed during this mode.
The result separately reports consumed tile beats, true DDR bytes and original
owner counters. These counter declarations are not hardware measurements.

Accepted burst data and ACK obligations continue through errors/abort. Raw
unexpected responses gate new read/write/control offers and poison publication
on that same edge. Legitimate external tile responses while the Dense owner is
idle remain legal, including the original SiLU bridge. A held successful result
cannot override the live poison sideband. Recovery requires a coordinated reset
of owner, adapter, Matrix and shared services; a local tag is not freshness proof
across that reset boundary.

## Evidence boundary

The final source typecheck covers 91 actual Scala/HardFloat files, including
Host/kernel. Twenty bounded CHIRRTL outputs cover burst/nonburst paths and
compare original-off, tiles-on and window-on/drain-off profiles. No full root
elaboration, RTL execution or native numerical acceptance is claimed.

Resource audit finds 74 new metadata register bits, no new payload buffer,
SRAM bank, Matrix array or SFU. Existing 32×1R1W banks/768 KiB, 4096 MACs and one
16-lane SiLU are retained. Combinational decode/routing/packing has no measured
area or timing result.

The Python model checks physical tile addresses and actual write/ACK ownership.
It is an event/port model; ticks are not hardware cycles. `ports()` and returned
events expose a pre-input proposal, so consumers also inspect current poison
before accepting a terminal result. Optional ACK byte-count diagnostics in the
harness are not extra fields in the production response.

`check_numeric.py` reuses unchanged window FMA and SiLU recipes. It initializes
only raw n1/weights and sentinel-filled destination DDR; actual bank packets
produce Gate/Up, each SiLU transaction passes through the Python owner tile port,
and act becomes DDR data only on accepted write beats. Comparisons happen after
all real ACKs and terminal poison checks. The full destination outside the
requested window and canaries must remain untouched. Gate/Up DDR output remains
zero. Data, logical DDR traffic, physical SRAM traffic and handshake counts are
reported separately; bank-word RMW commits are not activation handshake counts.

Exact capture/source/tool identities and retained first-run failures are in the
delivery manifest. No weights, tensors or generated hardware are in Git. The
original Qwen2 M128 native and FP32-final FAIL, and pending policy decision,
remain unchanged. A bounded act window is not all 56 windows or a full block.

Run the local source/control guards with `python -m unittest discover -s
candidates/qwen2_resident_matrix/ffn_drain -p 'test_*.py' -v` on one line.
The frontend checker accepts the same SHA-locked jar/HardFloat paths as its
predecessor. Actual numeric captures require the exact local provenance and raw
files in precision_pins; run M16 first, then the bounded M128 window after it
passes. CI runs synthetic/control/frontend checks and does not fresh-capture the
model's actual numerical input.
