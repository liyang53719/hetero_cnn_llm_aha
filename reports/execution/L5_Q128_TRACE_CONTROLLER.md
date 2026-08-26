# L5 q128 measured-latency trace controller

Status: PASS as cycle-accurate sequencing evidence.

The measured-latency controller wraps the previously frozen24-command count
controller, preserving all work counts while replaying latencies from passed
numerical receipts. It reports11,698,176 Matrix steps,61,101,824 busy cycles
and61,101,874 wall cycles. Score-matrix commands are zero and command-order
FNV64 is `29012cbdbd1b3252`.

This trace is separate from segmented numerical payload. Build allocation was
about362 MB and simulation7 MB, with no OOM.
