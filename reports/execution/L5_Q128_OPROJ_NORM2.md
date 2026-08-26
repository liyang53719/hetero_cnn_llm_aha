# L5 q128 OProj, residual1 and norm2 batches0-7

Status: PASS; q128 MLP/down phases remain `IN_PROGRESS`.

One unchanged RTL binary processes eight 16-token batches. Each batch runs a
complete 1536x1536 OProj on all physical rows, 1,536 residual chunks and 16
global post-attention RMSNorms. Every OProj, residual1 and norm2 node passes.

Each batch measures 73,728 Matrix steps and 302,688 cycles. Aggregates are
589,824 steps and 2,421,504 cycles: 2,359,296 Matrix, 12,288 residual and
49,920 norm2 cycles. Concatenated OProj/residual1/norm2 hashes are
`2893ed8f...`, `e4e80035...`, `4f1d6a10...`.

Shared lint/build allocations were about 559/877 MB; each simulation allocated
26 MB. No OOM occurred.
