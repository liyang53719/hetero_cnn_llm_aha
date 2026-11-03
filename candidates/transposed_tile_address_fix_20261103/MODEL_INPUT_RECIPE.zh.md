# 原始 159 源模型的地址修复选择契约

本目录是新的硬件源码候选，尚未构建或启动。`--hardware-source transposed-tile-address-v1` 只选择源输入，不能授予数值执行、完整 block 通过或最终 RTL 接受。省略该参数仍选择 `legacy`，即原 `model_candidate_build_20261101` 的 159 源与生成合同。

## 固定边界

- 保留原 fixed155 overlay、原 159 源 overlay、原生成合同、原 preconditions、first-fault / terminal SAME-SV 合同与旧 nonce 的全部字节。
- 新 overlay 相对原 fixed155 为 8 个替换、147 个保留、原 4 个新增，总计仍为 159；相对原 159 源仅替换 `TransposedDenseBanks.scala` 一项。
- 矩阵 4096 MAC、共享 Vector32、128 tokens、五个 profile、122 个完整 typed ports 及原固定资源/容量约束不变。这里是源级要求，不是实际新 RTL 的实现证明。
- 原 preconditions 的历史参考集合不刷新。`TransposedDownDenseBanks` 虽在完整历史参考集合中，却不属于固定 15 模块列表，也不属于实际共享 Vector32 子树。后续仍必须用真实生成层次、资源及完整接口重新核验。
- 修复属于新硬件，允许产生新 HIGH/LOW/SV 身份。不得把新 SV 冒充旧 raw-SV，也不得沿原 first-fault / terminal SAME-SV 模式运行。选择新源与任何旧只读模式组合，会在输入准备前拒绝。

## 新身份

- `MODEL_SOURCE_OVERLAY.json` SHA-256：`5ff6c6ee4887700b79f8bd3982250743575c3e3624d294d240b7bd92378bfc02`。
- `GENERATION_CONTRACT.json` SHA-256：`0a5e09a27a447b028697a631e5207fc0af6cae15d4c324a55524f9d41a46a753`。
- 选择的 Scala SHA-256：`c23f36805d78671e6fa8736668a0a837003cc620a413488fb3db530690e1bb53`。
- 新生成合同只改变 source-overlay SHA，其余配置、接口、preconditions、普通 driver 与“不授权执行”的字段全部继承原合同。
- gate 仅接受两个显式选择名及固定 repo 路径、固定合同 SHA，不支持任意路径、从观测结果学习 hash 或覆盖接受基线。

## 已接通的源码路径

`prepare_model_build.py → bootstrap_model_candidate.py → restore_model_inputs.py / materialize_model_binding.py → candidate_generation_gate.py → 实际 compile_model_sources`。

选择名在 restore 与 binding 两支都显式传递。新 binding 必须包含 159 个实际源文件、新 overlay、新合同、固定 preconditions 与完整 SOURCE_PINS catalog 的逐字节绑定；所有选中源必须已受审并被 Git 跟踪。catalog 未刷新、任何源缺失或改变时均拒绝。

pack 对新 generation / overlay 做精确配对，并核原始与 admitted binding、实际 observation、catalog、保留 overlay 文本、159 项生成输入 pin。producer verifier 使用独立、完整、固定的 selector-aware implementation map；所有历史 implementation map 保留。当前 selector-aware 普通、V1、V2 三种 producer 表分别绑定实际当前实现；V1 仍必须满足旧 host-helper 等源角色合同，不因实现表更新而取得执行资格。普通新硬件产物仍使用原未接受模型 artifact schema，不能携带旧只读诊断证据。

## 本阶段可执行的轻测

在仓库根目录，仅检查源码及 JAR 清单，不下载、不编译：

```sh
python3 -B candidates/model_candidate_build_20261101/restore_model_inputs.py --verify-only
python3 -B candidates/model_candidate_build_20261101/restore_model_inputs.py --verify-only --hardware-source transposed-tile-address-v1
python3 -B -m unittest discover -s candidates/model_candidate_build_20261101 -p 'test_*.py'
python3 -B -O -m unittest discover -s candidates/model_candidate_build_20261101 -p 'test_*.py'
python3 -B -m unittest discover -s candidates/same_job_execution_20261030 -p 'test_common_observer_integration.py'
```

最后一组必须在发布者统一刷新 SOURCE_PINS 后执行。两个依赖明确提供历史 SV/metadata 的端到端测试在没有 fixture 环境变量时跳过，不能据此声称真实七件新构建通过。

## 仍待独立审查与执行

1. 完成真实 banks Chisel 修复回归，审查新 Scala 与此处全部固定 source pins；本接线任务不修改 Scala。
2. 发布者统一刷新 SOURCE_PINS，对最终代码运行普通与 `-O` 轻测，并验证远端源码及相关轻量 CI。本接线任务不 push。
3. 另行审查新的普通模型构建入口与新的一次性启动身份。原 workflow/旧 nonce 完全不改，不利用其 terminal 模式启动新硬件。
4. 获准后从干净受审 checkout 使用显式新 selector，保持原预算与 20 个严格阶段，生成新的单份 SV/ELF 和七件包。不得自填 observed hash 为 accepted baseline。
5. 独立审查真实新 HIGH/LOW/SV、接口、物理资源/容量与编译 provenance 后，另行授予数值评价。五块必须使用完全相同的新硬件定义、同一 SV 哈希及同一固定物理资源，只切换运行配置/权重，并全部重新测试。旧 16-lane PASS 不迁移；旧统一硬件测试结果也不替代新硬件重测。

本阶段没有新的 long build、EDA、DUT、权重读取、nonce、CI 启动或数值授权。
