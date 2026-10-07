# Matrix / Norm / RoPE production arithmetic emission

This separate emitter preserves the original frozen RoPE emitter byte for byte.
It compiles the same production FP32 classes plus the unchanged split BF16/FP32
HardFloat FMA used by Revision8B-B. Live top ports prevent constant specialization.

Run `bash scripts/generate_matrix_norm_rope_primitives.sh`, then
`python chisel/matrix_norm_rope_hardware/manifest.py verify "$PWD" "$PWD/work/generated/matrix_norm_rope_candidate"`.

HardFloat, firtool, sbt, Verilator archives and the shared Maven lock retain the
literal pins from `chisel/rope_hardware_oracle`. Build caches stay in ignored
`work/rope_hardware_oracle`; generated RTL stays under ignored `work/generated`.
The new project has its own source inventory and manifest. No generated arithmetic,
weights or full traces are committed. Actual pipeline simulation is a separate
required gate; emission/lint alone does not establish arithmetic equivalence or PPA.
