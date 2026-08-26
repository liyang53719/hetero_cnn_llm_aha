# L5 target integrated trace controller

Status: PASS as cycle-accurate trace/count evidence; no payload arithmetic is
performed in this gate.

One synthesizable ready/done controller emits the 23-command target order from
the measured payload receipts. The harness replays each measured command
latency, while the controller itself counts accepted commands, active busy
cycles and Matrix steps. It never emits a score-matrix operation.

The trace reports 23 commands, 1,486,848 Matrix steps and 6,036,046 active
busy cycles. Wall time is 6,036,094 cycles including start/issue handshakes.
The command-order FNV64 is `8f1e5605d8f25e68`; score-matrix command count is
zero. Strict lint/build allocations were about 26/354 MB and simulation 7 MB,
with no OOM.

This is cycle-accurate trace replay, kept separate from the segmented RTL
numerical payload evidence.
