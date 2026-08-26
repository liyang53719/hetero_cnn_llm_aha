# L5 q384 OProj, residual1 and norm2 batches0-23

Status: PASS; q384 MLP/down remain pending.

One runtime-configured binary executes24 q384 batches then q128 batch0 without
recompilation. Every batch measures73,728 OProj steps,1,536 residual chunks and
16 norm2 operations. Aggregates are1,769,472 steps and7,264,512 cycles:
7,077,888 Matrix,36,864 residual and149,760 norm2.

OProj/residual/norm2 hashes are `0e288e73...`,`1313dd03...`,`8f5aff5b...`.
Shared binary SHA256 is `61d09d58...`; q128 hashes reproduce. Build allocation
was1,288 MB and each simulation99 MB, with no OOM.
