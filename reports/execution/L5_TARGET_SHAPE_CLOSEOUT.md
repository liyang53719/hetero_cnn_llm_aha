# L5 Qwen target-shape closeout

Status: PASS for the target-shape subgate; L5 remains `IN_PROGRESS` for q128,
q384 and decode contexts.

The pinned target is Qwen2-1.5B hidden1536/intermediate8960, 12 query heads,
two KV heads and head dimension128. Eight restartable numerical receipts cover
every target node and produce final SHA256
`872ffcab7daf957e1e4caf3db5c8e063e95bfe760ec5060fcb4264f6c66deffe`.
No score matrix is materialized.

Segmented RTL payload measures 1,486,848 Matrix steps, 5,947,392 Matrix cycles
and 6,036,046 total active cycles. A separate synthesizable 23-command trace
controller independently reproduces the exact operation order, Matrix-step
total and active-cycle total with zero score-matrix commands. Controller wall
time is 6,036,094 cycles.

Evidence classification is explicit: numerical values come from segmented RTL
payload; full sequencing/cycles come from cycle-accurate controller trace
replay. No analytical estimate is placed in an RTL-measured field.
