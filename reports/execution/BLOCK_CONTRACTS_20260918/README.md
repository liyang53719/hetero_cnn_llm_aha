# C04.1 → C02.1 → C07.1 沙箱执行记录（2026-09-18）

## 已交付范围

仅关闭 E0 软件合同子项，不升级其父项或真实模型/RTL 验收等级。

| 子项 | 本次结果 | 普通 Python | Python -O |
|---|---|---:|---:|
| C04.1 既有 ABI 整数/字节合同 | 保持 done；复核 65 个旧合法字节向量 | 359 passed | 359 passed |
| C02.1 来源绑定精度比较器 | 修复 producer index/policy 集合隐式类型转换；ongoing → done | 128 passed | 128 passed |
| C07.1 多状态域事务参考合同 | 修复 stale generation 先写后报错；新增 owner/ACK/reset 模型；ongoing → done | 136 passed，3 deselected | 136 passed，3 deselected |

这些专项测试有重叠，不相加当作独立覆盖。额外联合回归分成 815 + 76 两组，普通/优化模式均为 891 passed，原始输出及命令见 `combined_regression.json`。此前未拆分的调用因沙箱超时中断，不计通过。

C07.1 的 3 个 deselected 是导出源码范围之外的既有完整控制平面/quant RTL/state RTL 检查，不是本次新增测试；逐项原因见 `C07_result.json`。没有跑完整仓库回归，也没有执行 Chisel/RTL。

## 实际修复

C02.1：旧 producer index 经 int() 转换，bool/float/字符串可能误命中 FP32 policy。新增严格类型门禁；38 个新增边界测试在修复前 18 failed、20 passed，修复后全部通过。离散 route/index/selection/counter 保持 bit-exact。公式必须绑定调用方固定的来源哈希，不能由待验回执自选阈值；没有杜撰官方 0.002 公式。

C07.1：原 StateCommitModel.commit 在检查 generation 前已经改写提交态。非零旧值 11 被旧事务写成 99 后才抛 stale txn；十个 StateDomain 的复现均失败。现在先拒绝 stale generation，再发布任何状态。旧 rollback() 仍推进 generation，新 discard() 只丢弃未发布 shadow，必须搭配新模型的 owner ticket/epoch 过滤。

新 word 事件模型覆盖 request/layer/epoch/generation/txn_id/ticket 隔离、乱序 ACK、accepted-prefix 原子发布、最后 ACK 错误、poison 后成功 ACK 计数、reset 迟到响应和相同外部事务 ID 重试。

## 独立压力校验

```sh
python scripts/block_state_stress_oracle.py --transactions 4000
python -O scripts/block_state_stress_oracle.py --transactions 4000
python scripts/block_checklist.py validate
python scripts/block_checklist.py next --executor sandbox
```

每种解释器模式：4,000 个 word 事务（成功/最后 ACK 错误/poison/reset 各 1,000）及 4,000 个既有 barrier 事务。word oracle 最终状态 SHA256 为 `5ef6b95fe95e7d3d5ee26652ca226d017d1d35c9a99de6ede14d82b9ebc90e6d`；普通/优化模式报告字节一致。

273,320 成功 ACK 字节是此四字节 word 模型的观测总量，**不是硬件测量或已提交字节**。需要继续验证真实 state-memory owner 的 shadow 隔离、有限宽度 tag/epoch 回绕、真实 AXI burst/错误语义、DUT 完整状态回执及数值状态消费；不得据此关闭 C07.2/C08.2。

## 取源与复现

初始 main 为 9270cafab41cbdf04caa7f1e9edfce43339ba289。通过仓库原有 export-block-source 流程取回 c689eff314955534851848efc52545fa381c7c32 的选定源码归档，校验归档 SHA256 和 Git blob 清单后在沙箱执行。归档只用于传输，GitHub Actions 没有冒充沙箱测试。

C02.1 已发布内容提交为 842a67a9e2cac8f53d3c5923563a25a2ad7db70c；C07.1 以该提交为设计基线，源码、测试和日志哈希保存在 C07_result.json 及唯一 checklist。通过仓库既有 apply_sandbox_contract_patch.py 的 preimage/postimage/清单渲染门禁原子发布，不覆盖不同前像。

## 下一步不依赖本地 agent 的工作

关闭原三项后旧 sandbox 可认领队列为空。已新增 C03.3、C04.3、C08.3 三个独立准备子项，状态均为 to do、未认领；其依赖/边界和建议顺序见 `doc/SANDBOX_NEXT_20260918_CN.yaml`。状态唯一来源仍是 `doc/block_checklist.yaml`，`doc/BLOCK_CHECKLIST.md` 由脚本生成。
