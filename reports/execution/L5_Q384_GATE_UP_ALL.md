# L5 q384 gate/up batches 0-23

Status: PASS; q384 SiLU/product and down/final remain pending.

One runtime-configured RTL binary executes both gate and up modes for all 24
q384 16-token batches. The same binary then re-runs q128 batch 0 without
recompilation. All 48 q384 phases pass exact C++ `fmaf` comparison.

Each projection phase measures 430,080 physical 16x32 array steps and
1,720,320 cycles. The aggregate is 20,643,840 steps and 82,575,360 cycles.
Concatenated gate/up SHA256 values are
`59f1899fbd871ed2f30c618649bd7b406deec3e03d91c110298ed9f83b397527`
and `3a4b0dbaa9cce3be612239521afc91500500c841ab5db0b59dd4baecf8e52ed9`.

The shared binary SHA256 is
`44be7241201e11d44c86d9b42f8ee1668e98966c1179676da0217b4fce248c2d`.
Every simulation used four Verilator threads; gate and up ran concurrently for
eight active threads total. Reported allocation was about 118 MB per process,
with zero OOM events.
