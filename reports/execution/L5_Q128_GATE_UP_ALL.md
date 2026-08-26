# L5 q128 gate/up numerical batches0-7

Status: PASS; q128 SiLU/product/down phases remain `IN_PROGRESS`.

Eight restartable16-token batches use exact four-thread k-ordered fmaf goldens
and one unchanged RTL binary. Verilator `--threads 4` was accepted only after
batch0 reproduced the single-thread hash and 430,080-step count exactly.

Each gate and up phase measures430,080 steps and1,720,320 cycles. Aggregated
gate/up steps are6,881,280 and cycles27,525,120. Concatenated gate/up SHA256
values are `6a2d13e4...` and `4852e5bc...`.

The four-thread simulation allocates118 MB; its build allocated about1,018 MB.
No OOM occurred and CPU use remained limited to four cores.
