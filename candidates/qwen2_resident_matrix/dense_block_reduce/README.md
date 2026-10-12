# Explicit QKV block/pair reduction on the existing resident path

This candidate addresses the frozen Qwen2-1.5B L0 native Q-projection discrepancy. It keeps the original public21 Command128/descriptor image and full Dense Job, and changes only Q/K/V dispatch to two independent K partials, an existing shared-vector FP32 Add, and the existing DDR drain. Following Bias owns the BF16 materialization. O/Gate/Up/Down and Attention retain their prior arithmetic policy.

The scoped profile is Torch 2.10 CPU / oneDNN 3.7.1 / AVX512 core BF16 / four threads, cold M16/M128, K1536, Q1536 and K/V256. Profile data selects contiguous K ranges [0,1024) and [1024,1536), high-first within each pair. Those boundaries are not a universal model constant. The generic internal interfaces take explicit even ranges and keep the original K/N row strides. The archived six isolated full-shape Q/K/V cases match the frozen official values exactly. Normal-domain agreement does not prove equivalence to native FTZ/DAZ for subnormal inputs; strict FMA gradual underflow remains unchanged.

## Actual path

1. Public frontend validates the unchanged commands, descriptors, permissions, regions and complete program. Raw input, weights, gamma, bias and RoPE constants are the only preloads.
2. The existing owner loads the complete A tile once into its original banks. Each partial uses the same Matrix service and returns actual FP32 output packets into resident slots 0/1. Local accepted Matrix K ordinals remain distinct from the pair-ordered physical source K.
3. After both real owner/Matrix retirements, an exclusive tile grant runs the shared 16-lane Add. It reads slots 0/1 and RMW-writes slot 2. It instantiates no additional floating-point or SRAM resource.
4. The existing drain issues actual DDR descriptors/data and counts acknowledged bytes. All N windows must finish before A-lease invalidation and the public Dense terminal. The following original Bias command reads that published physical DDR output.
5. The original Attention, residual and FFN suffix consumes these real writes. The read-only observer retains missing future-score positions and cannot publish or substitute tensors.

All Python owner/bank/lease types are obtained from the existing public FFN execution module’s exact pinned authority. Loading another byte-identical module would create different dataclass identities and is rejected. New K-window A-load fence events accumulate in `k_a_fences`; legacy FFN window events retain `a_fences`. Their sum is explicitly named `total_window_a_load_fences` and excludes ordinary Dense/Down A ingress. Neither counter is reset at command boundaries. Physical writes always carry an explicit typed 64-byte mask; the memory receiver’s existing extent/last/mask checks remain strict.

`public_execution.py` is the software dispatch integration. `DenseBlockReductionCoordinator.scala`, the three source patches, `DenseTileSumBridge.scala` and `PublicReductionElaboration.scala` describe the corresponding default-off Chisel interfaces and same-bank composition. Frontend compilation/CHIRRTL is structural evidence; it is not hardware simulation or production Host Chisel activation.

## Resources and failure boundary

The original 688 KiB A banks and 80 KiB B banks are unchanged. M128/K1536 A is stored as 384 KiB BF16; three M128/N160 FP32 slots occupy 240 KiB. FP32 DDR source containers do not enlarge the resident BF16 copy. Each 16-element sum consumes two logical 64-byte reads and one logical write; the existing 512-byte physical bank-word RMW costs three physical reads and one physical write. The bridge retains one 512-bit lhs operand. Full-job/profile registers and counters are accounted separately from payloads; no free area/timing claim is made.

Default-off resource deltas verified by frontend: K policy +66 bits, shared Vector mode +1 bit, Dense-drain admission +0 bits. The sum bridge has 599 bits (512 payload, 70 request fields, 17 control); the coordinator has 1312 metadata bits and the integration wrapper four accepted-obligation bits. The fixed Matrix denominator remains 4096 MAC/cycle. Software model ticks and host seconds are not hardware cycles or measured utilization.

Errors must drain every previously accepted Matrix, DMA and Vector obligation before the unique failed terminal. Failed resident tiles remain poisoned and inaccessible until coordinated reset; an error does not authorize publishing staging bytes. Current faults fence held unaccepted success; accepted old terminal events cannot be retracted. Outgoing aborts use independent external abort or registered poison, avoiding aggregate-reset combinational feedback.

## Validation and reproduction

`run_tests.py --out <fresh-directory>` discovers every small test file and runs each in a separate interpreter, recording counts and exit status. `MATRIX_SERVICE_LIBRARY` must name the actual library built by `scripts/build_shared_matrix_recipe.py`, with its adjacent compile.json; missing dependencies fail, never skip. Test isolation retains the strict loaded-source observer checks.

`check_public_numeric.py` freezes the prior raw workload/native archive, the new source closure and an independent new-arithmetic reference. It reuses the existing official-BF16 Matrix/SiLU ELF. The actual complete public21 terminal and all ACKs must precede any reference tensor read. The unchanged official per-node gates determine the native result; old sequential and independent-native FAILs remain explicit auxiliary diagnostics. A fixed-recipe match alone cannot return the official PASS status. Full 29-node acceptance remains separate because explicit mask storage is absent and future causal positions are not executed.

The independent producer in `reference/` changes only three QKV C++ calls and proves the inverse transform restores every old source byte. Its execution is not actual-chain acceptance. Runtime archives and input identities are explicit; cold small tests require no historical work directory.

See [the Chinese execution record](../../../doc/QWEN2_QKV_BLOCK_REDUCTION_20261012_CN.md) for exact completed and pending gates. No full RTL, M128 rerun or other-model acceptance is implied by the small tests.
