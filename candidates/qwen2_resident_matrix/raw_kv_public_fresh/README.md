# Fresh M16 public-chain provenance preparation

## 中文计划

- 已完成：原始 Public PV16 默认关闭 KV 数值入口及显式来源合同，见
  `raw_kv_public_numeric`；它没有执行新的完整数值链。
- 已完成：新鲜来源验证器、两个原始入口的显式适配补丁及 40 个冷测试；
  普通 Python 与 -O 均通过。两种 raw KV 模式均通过 183 项来源冻结和零模糊组合。
- 进行中：本批来源、验证器和入口补丁的独立审查。
- 下一步：审查后准备单次、有硬截止时间的 CI 重建及 M16 数值运行。
- 未运行：本批没有下载权重、生成数值参考、编译原生库或执行完整模型/RTL。
  M128 仍需同源码、同模式的新 M16 成功凭据，不能继承历史 PASS。

## Original computation, fresh metadata

The public21 DUT remains the existing executed PV16 ReducedPublicExecution
chain with one original Dense owner, shared Matrix/scalar services and original
Host completion fences. The fresh profile changes provenance admission and
artifact lookup only. It does not create a replacement numerical top.

Historical manifest, archive, layout and reference-builder gates remain intact.
Fresh acquisition timestamps, paths, runtime and build receipts retain their
real identities in a separate manifest. No archived receipt or timestamp is
fabricated. Exact tensor/segment content identities remain bound to the original
immutable model ledger.

The reference producers remain distinct:

1. The unchanged original Qwen2DecoderLayer model gate supplies official and
   independent-self-cache native reference exports.
2. The original sequential BF16 recipe supplies the existing diagnostic outputs.
3. The original QKV block/pair transformation supplies the reduced arithmetic
   reference used by the actual fixed-recipe gate.

The two recipe executables share one verified readonly arena and trig table but
have separate sealed output inventories. They must not alias each other's
outputs. Fresh Q/K layout is bound to actual producer metadata and hashes, then
decoded by the existing layout conversion. Comparison metrics, causal masks,
assigned tolerances and final acceptance gates are unchanged.

The original strict `official_bf16.dense_silu` builder and verifier produce and
check the DUT library. A legacy SiLU library cannot substitute for
`sf_vector_bf16_v1`.

## Proposed bounded setup

Preparation targets M16, past_tokens=0 only. A real verified checkout is required
because the original source regenerator uses `git show HEAD`. Exact reviewed
composition overlays are allowed; unknown consumed-source drift is rejected.
Repository and installed-runtime identities are checked separately. The later setup
supervisor must enforce the reviewed Torch 2.10.0+cpu build/commit, AVX512 backend,
unset ATEN_CPU_CAPABILITY and original four-thread policy; recording an installed
runtime identity alone does not establish that backend profile.

The proposed setup deadline is one absolute 600 seconds, created before package
installation. At most 594 seconds are available for work, with five seconds for
process-group termination/reaping and one second for a final safe receipt.
Per-phase ceilings draw from that same remaining budget and are not additive:
packages 120 seconds, acquisition 420, official forward 60, reference builds /
tables / arena / runs 100, strict library 40, and final hash validation 20.
These are unexecuted limits, not completion estimates. No automatic retry or
budget increase is implied.

A later actual M16 run retains the original 900-second work budget and proposed
930-second external process limit. Setup and execution would use a separate
30-minute job envelope, subject to final review. No workflow is installed here
at this preparation stage.

## Evidence and data handling

Raw weights, inputs, activations, reference exports, detailed producer receipts
and logs stay in the private execution workspace. Public evidence is limited to
fixed status/phase values, bounded counts, hashes, timings and structured failure
diagnostics. Diagnostics may identify a frozen repository source frame and line,
allowlisted exception type, exit code or signal, but omit locals, raw exception
messages, commands, private paths and signed URLs.

Safe progress is atomically replaced. On timeout or interruption the entire
process group must be terminated and reaped, and the last validated safe phase
record retained. Partial cached data is not acceptance and must not cause a
READY or numerical PASS result.

Successful setup means only READY_FOR_ACTUAL_M16. The actual run still must
complete every original transaction and comparison gate. Historical observed
27-gate results and the separate synthetic Attention M128 result do not certify
this fresh complete-chain profile; full 29-node acceptance remains unresolved.

## First preparation slice and reproducibility

This seven-file batch contains `assets.py`, `official_entry.patch`,
`public_entry.patch`, `prepare.py`, `pins.json`, `test_assets.py` and this README.
It adds no setup supervisor or workflow. Run the short checks from repository root:

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_fresh.test_assets -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_fresh.test_assets -q
```

Both composition modes freeze 183 source inputs. Raw-off emits two entry variants;
raw-on emits eight files including the six previously reviewed raw/observer
variants. The two new entry targets are `official_bf16/check_numeric.py` and
`dense_block_reduce/check_public_numeric.py`. Neither is an additional arithmetic
implementation or a replacement reference producer.

The AST historical projection checks the disabled path. Enabled branches require
direct review and exact generated-source pins; the projection alone does not prove
their semantics. Both fresh modes freeze all seven helper files because even the
disabled entry calls canonical mode validation. The full producer closure is
additionally bound when fresh mode is enabled. Cross-mode snapshots and unknown
source drift fail before native prerequisite admission.

The cold tests use clearly synthetic metadata/control fixtures and tiny local
files. They verify schema, hash and path guards, duplicate/nonfinite JSON rejection,
resolved-path/inode non-aliasing, exact source closure, early mode rejection and
unchanged original comparison/publication logic. They do not verify actual model
weights, execute reference producers or certify an authentic ready manifest.
Artifact paths must stay under the selected fresh workspace, with no symlinks,
traversal or nonregular files. Shape/profile admission precedes referenced-file
access; actual bytes are hashed before readiness is admitted.
