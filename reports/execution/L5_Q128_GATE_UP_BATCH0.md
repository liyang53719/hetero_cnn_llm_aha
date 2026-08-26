# L5 q128 gate/up numerical row batch0

Status: PASS for tokens0-15; q128 gate/up batches1-7 remain pending.

A four-thread C++ golden preserves k-ordered `fmaf` for all16x8960 outputs and
does not use matrix-library multiplication. One unchanged physical16x32 array
then runs complete gate and up projections in separate phases.

Each phase measures 430,080 steps and 1,720,320 cycles; combined steps are
860,160. Gate/up FNV64 values are `eab5299b488824e8` and
`2f1112460a333c50`; SHA256 values are `3f93989b...` and `836b4d07...`.

Lint/build allocations were about497/749 MB and each simulation46 MB. No OOM
occurred.
