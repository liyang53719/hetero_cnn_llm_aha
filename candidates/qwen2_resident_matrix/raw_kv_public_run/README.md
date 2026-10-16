# Fresh linked M16 public-chain run

## 中文计划

- 已完成：独立资产验证器与 setup-v1 监督器的冷测试和来源审查；真实生产器尚未执行。
- 已完成：SETUP/资产双凭据准入、原始 M16 入口连接及 39 个普通 / -O 冷测试。
- 进行中：独立启动合同、来源组合及工作流的最终审查。
- 下一步：短测试和独立审查通过后，由一次工作流进行实际重建及 M16 数值运行。
- 未运行：本批没有安装包、下载权重、运行原生生产器或完整数值链；没有新的数值 PASS。

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

## Reproduce the bounded checks

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_run.test_admission candidates.qwen2_resident_matrix.raw_kv_public_run.test_run_ci -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_run.test_admission candidates.qwen2_resident_matrix.raw_kv_public_run.test_run_ci -q
```

These 39 tests use metadata/control fixtures and short local child processes.
They do not invoke package installation, native model services or reference
producers. The new launch contract freezes 193 clean source inputs and the eight
reviewed generated overlay identities; its own bytes are separately bound to
the event commit. The original setup still uses its separate187/183 source maps.
