# Fresh linked M16 public-chain run

## 中文计划

- 已完成：SETUP/资产双凭据准入、原始 M16 入口连接及首次真实 CI 尝试。
- 已确认：运行 38901691296 的设置阶段通过，原始数值入口返回，包装器的原始结果验证通过；随后 JSON 磁盘结果与内存对象比较失败，整个运行仍为 FAILED。
- 进行中：修复原始报告中 tuple 经 JSON 转为 list 的序列化比较，并补充失败后可保留的有限安全验证证据。
- 下一步：短测试和独立审查通过后，再由根任务决定是否发布并运行一次修正后的工作流。
- 尚无本链新 PASS：首次失败的私有详细结果未上传，不能重建丢失的数值凭据或追认整个运行成功。完整 29 节点验收和本链 M128 仍未完成。

## One existing chain

The numerical target is the executed PV16 ReducedPublicExecution entry with the
published explicit fresh-assets/raw-KV source variants. It uses the existing
Dense owner/banks, Matrix service, scalar policy and Host terminal fence. The
original BF16 MLP library and sequential versus block/pair reference producers
remain distinct. No replacement numerical top or arithmetic policy is introduced.

Original assigned observed gates are preserved. Their success does not establish
full29-node acceptance: explicit mask and complete noncausal observation coverage
remain outside that receipt. Historical observed PASS and synthetic Attention
M128 PASS are not prerequisites or substitutes for this fresh run.

## Independent launch contract

Published asset and setup profiles are immutable. A new launch contract binds the
runner, linked-admission helper, tests, workflow and exact published dependencies.
A private local clone of the exact event commit receives only the reviewed eight
raw-enabled source overlays. There is no network fallback or lazy fetch. The
original checkout stays unchanged; Git HEAD and producer identities remain verifiable.
Unknown changes fail before setup; overlays and launch identities are checked
again afterward.

Numeric admission requires the private SETUP.json commit, its matching successful
safe summary and ASSETS.json. These must agree on source identities, checkout,
workspace device/inode, raw-KV mode, M16 rows, zero past tokens and every completed
setup phase. A standalone READY manifest or copied historical receipt is rejected.
Hash/metadata admission precedes original entry import. Native-dependent checks
run in the setup-created environment, inside the execution deadline.

## Single bounded attempt

The wrapper carries one absolute1680-second ceiling across its private-clone
re-exec. Clone/composition time counts toward it. Setup runs directly in that
process so it retains sole ownership of producer process groups; the later numeric
child has one separately supervised group.

The original setup supervisor owns its600-second deadline, including package
installation, cleanup and final evidence. The M16 external930-second deadline
starts before linked admission and original snapshot preparation; the original
entry retains its900-second internal work limit. The proposed job envelope is
30minutes, reserving two minutes outside the wrapper for checkout, cold checks and
artifact upload. There is no retry, rerun-attempt acceptance, hidden budget override or
M128 execution in this workflow.

The package/backend and input identities remain those reviewed by setup-v1:
Python3.12, Torch2.10.0+cpu, NumPy2.3.5, Transformers4.40.1, reviewed Torch commit,
AVX512 and original thread policy. The collector requests only the pinned13-tensor
layer subset. Successful installation or setup is not numerical success.

## Private data and useful failure evidence

Weights, inputs, activations, reference exports, binaries, detailed receipts and
producer logs remain in the private CI workspace. Uploads are an exact allowlist
of bounded safe summaries/progress and source hashes. No raw detailed execution
summary is uploaded because it may contain private paths or exception text.
Failure evidence uses fixed statuses/phases, bounded timing/counts/hashes,
allowlisted exception classes and verified repository-relative frames only.

Actual acceptance requires successful child exit and the original freshly emitted
observed-gates result, with fixed arithmetic success, source/input revalidation,
whole Host terminal and raw lease retirement. Setup completion alone never yields
PASS. A failure or timeout remains explicit and retains only safe partial evidence.

## First attempt and serialization correction

Run `38901691296`, job `116975226044`, ended FAILED in the numeric phase
at 830.432862 seconds. Its retained artifact SHA-256 is
`bd688b7abc6208d07614e650ffcaece2f29a6c54d809cce497a601d7a2380a39`.
The diagnostic identifies the disk/runtime receipt equality check, after
`entry.run` returned and `validate_actual` completed. No private actual receipt
survives in the three-file artifact, so this is not a retrospective numerical PASS.

The original Host report contains tuple-valued published spans, and the original
profiled Matrix report contains nested tuple-valued ranges. JSON serializes both
as arrays. Comparing parsed JSON directly with the returned Python object rejects
these legitimate reports. The corrected wrapper compares strict JSON-canonical
representations while retaining boolean/integer distinctions and rejecting
nonfinite values. Original source, arithmetic and numerical gates are unchanged.

A validated partial result is diagnostic evidence only. Later receipt, source,
admission or deadline failures still fail the launch; they cannot promote partial
evidence into the successful completion receipt. The explicit workflow revision
permits one corrected attempt under the same deadlines, after review.

## Reproduce the bounded checks

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_run.test_admission candidates.qwen2_resident_matrix.raw_kv_public_run.test_run_ci -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_run.test_admission candidates.qwen2_resident_matrix.raw_kv_public_run.test_run_ci -q
```

These 45 tests use metadata/control fixtures and short local child processes.
They do not invoke package installation, native model services or reference
producers. The new launch contract freezes 193 clean source inputs and the eight
reviewed generated overlay identities; its own bytes are separately bound to
the event commit. The original setup still uses its separate187/183 source maps.
