# Host Command128 / 共享原始 iDMA：real16 前驱链验收

## 已通过的对象，不扩大结论

被测代码：`536d68cb8f903cbc0959da8b2345ae30ca57740d`；完整硬件执行为 GitHub Actions run `34055833122` 的 `actual-dut`，没有本地 agent 参与编码或提供算子结果。开发沙箱重新执行了组件、真实 iDMA 和错误恢复测试，并独立重新读取完整 CI 二进制和逐元素 CSV。新增校验工具不修改 Chisel 或生成 RTL。

验收链为：显式启动的真实尺寸 Qwen2 单 block（原 512-MAC 阵列）→实际 DDR 输出 Y→三条从 DDR 读取、硬件译码的 Host `SFU_VECTOR` Add 命令。三条 Add 是生产入口集成测试，不是 Qwen2 模型新增的三个算子，也不代表完整 block 已由 Host 的原21条命令驱动。

参数：16 tokens、H=1536、FFN=8960、12 Q heads、2 KV heads、head_dim=128。权重为确定性合成权重；数值合同为固定 BF16/FP32 有序配方。官方权重、整网 q1024、全部21/588条原始命令和800MHz时序签核仍未通过。

## 完整数值结果

- 单 block：15阶段、663,552个FP32输出逐字一致；最后一阶段Y含24,576个值。
- Host命令：3条、73,728个FP32输出逐字一致。
- 总比较量：737,280个值；保存39个tensor/命令表文件和737,280行逐元素CSV。
- 同一个DUT和DDR，不在block与Host命令之间reset，不进行Host中间数据复制。
- 生成层级为一套原Matrix endpoint和一套原pinned-iDMA backend。没有替代DMA、算子回调或completion echo。

| Host PC | opcode / engine | wait → signal | A（实际前驱） | B | D |
|---:|---|---|---|---|---|
| 0 | 0x30 / 3 | 0 → 1 | 0x115505000（Y） | 0x10b305000（X） | 0x115b06000（Z0） |
| 1 | 0x30 / 3 | 1 → 2 | 0x115b06000（Z0） | 0x10b305000（X） | 0x115b1e000（Z1） |
| 2 | 0x30 / 3 | 2 → 3 | 0x115b1e000（Z1） | 0x10b305000（X） | 0x115b36000（Z2） |

每条命令shape为16×1536、FP32，成功写响应确认98,304 bytes。实现 Z0=Y+X、Z1=Z0+X、Z2=Z1+X。Python独立复核实际前驱二进制，不只比较C++参考的hash。

Host路径实际读取33个metadata beat（3个Command128和30个typed descriptor记录，当前无记录缓存），9,216个payload read beat、4,608个write ACK；全部经同一iDMA，共13,857次搬运。block本身3,045,760次；总计3,059,617次，三个arbiter客户端的accepted/returned与backend计数守恒。

block计数为68,502,384 DUT cycles、749,101,056 useful MAC、762,052,608 executed MAC。这不是整个Host请求的性能报告，也不是800MHz DC签核。

## 通过的测试与证据来源

| 检查 | 结果 |
|---|---|
| Chisel frontend/typed tensor/arbiter DUT测试 | 14/14；CI与沙箱分别执行 |
| 真实iDMA Host数值链 | BF16/FP32各11个长度，22组、66条命令、166,758个值；CI与沙箱通过 |
| 真实iDMA非法输入/错误响应 | 8组拒绝；CI与沙箱通过 |
| 第0/1/2条命令的4种故障位置 | 12组，包含metadata读、payload读、首写和末写失败 |
| 每组故障后的reset与全链恢复 | 12组，1,188个值；失败前合法前缀另检查396个值 |
| real16 block→Host3命令 | CI完整执行通过，沙箱重读全部输出/CSV再次通过 |
| 冻结公共ISA parser交叉解析 | 3条Command128、30个descriptor、9条tensor chain全量roundtrip |
| 公共ABI校验器负向测试 | 29项变异均拒绝，普通Python与`-O`一致 |

失败路径仅发布一次非零completion，停止消费者。末写失败时可有128 bytes已经物理写入，但失败tensor不被发布；不宣称物理内存自动回滚。复位前不得接受新工作。

沙箱还启动了一次重复完整block回放，前10阶段与CI逐字一致；完整CI证据已取得后主动停止了重复长回放，该重复运行不计作完整PASS。所有日志均保留。

## 永久Git证据，而不只是临时CI artifact

证据目录：`reports/execution/HOST_COMMAND_SHARED_IDMA_536D68C_CI/`。

核心文件是`ACCEPTANCE.json`、`real16/run.log`、`real16/all_shared_elements.csv.gz`、`real16/tensors/`、`commands/`、`partial_failure/`、`unit/`、`PUBLISHED_SHA256.json`和`DURABLE_PUBLICATION_RECHECK.json`。

首次自动归档受仓库忽略规则影响，24份.log未进入Git索引（二进制和CSV此前已经提交）。归档修复只对固定manifest列出的文件使用`git add -f`，逐一从Git INDEX读回104项内容核对SHA-256，不改写原日志空白、二进制、生成SV或数值阈值。必须以完成该索引校验后的提交验收。

## 本地只复核或执行，不修改代码

先固定到包含本文和完整证据的提交。只复核现有结果时：

```bash
PROOF=reports/execution/HOST_COMMAND_SHARED_IDMA_536D68C_CI
python3 chisel/continuous_prefill/scripts/seal_host_command_delivery.py \
  --unit "$PROOF/unit" --commands "$PROOF/commands" --real "$PROOF/real16" \
  --repo "$PWD" --source-base 536d68cb8f903cbc0959da8b2345ae30ca57740d \
  --output /absolute/new/host_recheck.json
python3 chisel/continuous_prefill/scripts/audit_host_public_abi.py \
  --repo "$PWD" --evidence "$PROOF/real16" --output /absolute/new/public_abi.json
```

重新执行完整固定硬件门禁时：

```bash
export IDMA_EXPORT=/absolute/path/to/verified/idma_export
bash chisel/continuous_prefill/scripts/run_host_command_acceptance.sh /absolute/new/host_acceptance
```

要求Java17、sbt、Verilator、g++、Python3和已锁定的iDMA源包；支持已校验的OFFLINE_TOOLS。输出目录不得已存在。成功必须有`acceptance.exit=0`和`PASS_HOST_COMMAND_SHARED_IDMA_DELIVERY`，全部预期字数与错误门禁不能减少。缺工具为BLOCKED，不是PASS。失败保留目录并返回命令、版本和首次错误；执行agent不改Chisel、RTL、参考、阈值或脚本。

下一开发门槛仍是把现有block各owner接到原始Host算子命令与descriptor，不能以本次3条测试Add替代完整21条命令图；完成后再扩大token数、层数和模型范围。
