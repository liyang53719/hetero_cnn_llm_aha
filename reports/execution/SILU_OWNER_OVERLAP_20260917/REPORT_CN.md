# SiLU owner：数值/异常回归与默认关闭的 Host 接入

起点：`main@7d88efbac6be24fa8c7ecc68ce08933dbcd39ad2`。
本轮实际执行 Chisel 编译、Verilator 数值测试以及两种 Host 配置的 RTL 生成。
未执行完整 Host+iDMA real16 双层 A/B，不改变既有两层性能验收结论。

## 实际修复

`OverlappedSiluOwner` 在数值错误发生后，会继续排空已经发出的访存请求。
旧代码把所有成功响应的处理都放在 `!poisoned` 条件下，导致之前的 store
即使成功返回 ACK，`done.writeBytes` 仍可能漏计。

定向测试先计算一个合法向量，延迟其 store ACK，并在下一向量放入 NaN：
旧 RTL 实际确认 64 bytes，返回 0，测试失败；修复后确认与返回均为 64。
另一项测试让 store offer 先受反压、再遇到数值错误，验证请求不能被撤回。
成功 store ACK 现在始终计数，但错误状态和 reset-required 不被清除，
也不会发布成功完成。失败或错误 tag 的 ACK 不计作成功写入。

修复提交：`07619731ea10f35a943ac4a79b78e5381aa184dd`。
回归测试提交：`5bfa70bd47f4aaa050fd30c3f02f827651d1add6`。

## 实际测试

`run_silu_owner_gate.sh` 最终退出码 0，ScalaTest 4/4 通过。
30 个正常 owner 任务（baseline 13、overlap 17），6 个故障任务，
7 个非法任务拒绝。共比较 4,480 个 owner FP32 输出值（包括故障前合法输出）
及 192 个独立向量 FP32 输出值；不是 4,480 种独立输入分布。

测试覆盖数值逐位比较、随机请求反压与返回延迟、高地址、顺序 tag、
成功 ACK 后才计写入/完成、done 反压稳定、NaN 与在途/受阻写并发、
读 A/读 B/最后写错误、错误 tag、错误后隔离与复位、复位后合法任务，
以及零尺寸、非 16 整数倍、未对齐、越界、输出别名、错误字节数和错误 kind。

另有 18 项 Python 校验器测试，普通与 `python -O` 均通过；
校验器拒绝缺失/重复用例、被改动的计数、未覆盖的晚到 ACK、失败日志和
缺少源码一致性回执。该类测试的合成日志只测试解析器，不冒充 RTL 运行。

## 性能口径

这些周期来自真实 owner RTL，但 memory service 由测试端提供字节存储和响应。
本组件测试不包含实际 pinned iDMA、DRAM bank/refresh 或完整网络。
两种实现使用相同输入和同一种 seeded jitter 算法，不是逐周期相同的 DRAM trace。
`RESULT.json` 保留全部 13 组配对数据，包括没有收益的短任务。

| 元素数/seed | baseline 周期 | overlap 周期 | 加速比 |
|---|---:|---:|---:|
| 16 / 4 | 97 | 123 | 0.789x |
| 64 / 10 | 439 | 308 | 1.425x |
| 256 / 11 | 1797 | 1058 | 1.698x |
| 1024 / 101 | 6935 | 4068 | 1.705x |

1024 元素一项减少 41.34% 周期；小任务不保证加速。
不把这个比值乘到模型 token/s 上，不更新旧 2.198% 整请求 MAC 利用率。
原 Matrix、16-lane SiLU 算术、exp/div/舍入配方及 iDMA 源码均未在本轮修改。

## Host 接入

`QwenOwnerKernel`、`HostBlockTop` 和 emitter 新增 `overlapSilu=false` 参数；
原 `run_host_block_gate.sh` 接收 `OVERLAP_SILU=0|1`，默认 0。
值 1 必须同时选择 pipelined owner。没有新增 Host opcode 或第二份 SiLU 算术。
header 增加 `OWNER_OVERLAP_SILU`，scope 增加 `overlap_silu`。

实际生成了 tiny、4096-MAC、16-beat、pipelined、burst-write 的开关 0/1 两种 RTL。
归一化后的 Host public ABI 完全一致，各有一个 ScheduledSiluOwner，
其内部仅有一个选中的 owner 和一个 SiluVectorUnit。
非法开关值及非 pipelined+overlap 配置在产生工件前被拒绝。
这是完整 top 的 elaboration 检查，不是完整 top 的数值 PASS。

## 复跑及下一验收关

在已配置 Java/sbt/Verilator 的工作区执行；离线环境可设置现有 OFFLINE_TOOLS。
组件不需要 IDMA_EXPORT：

```bash
bash chisel/continuous_prefill/scripts/run_silu_owner_gate.sh \
  "$PWD/work/silu_owner_new"
python3 -m pytest -q chisel/continuous_prefill/tests/test_silu_owner_verifier.py
```

完整两层 A/B 使用已有 verified IDMA_EXPORT、HardFloat/Matrix 工具链，保持不同输出目录。
以下是待执行门禁，不是本轮已经通过的结果：

```bash
export MATRIX_MACS=4096 WEIGHT_READ_BEATS=16 PIPELINED_OWNER=1
export NATIVE_BF16_WEIGHTS=1 BURST_WRITE=1 COMMIT_TAIL_READ=0
for mode in 0 1; do
  OVERLAP_SILU=$mode bash chisel/continuous_prefill/scripts/run_real_two_layer_gate.sh \
    "$PWD/work/silu_real16_two_layer_${mode}_new"
done
```

验收保持 42 completions、38 owner jobs、1,409,024 个输出值零差异、
实际写回 ACK/错误传播、单 iDMA、无 Host 中间态注入；然后比较整请求周期。
未通过前不修改默认开关，不宣称新整机吞吐、官方权重质量或 800 MHz 签核。

`SOURCE_IDENTITY.json` 保存受测关键文件身份、工具链和日志哈希。
源码由已归档 source export 加当前主 Scala 差异恢复，按字节核对；
未运行的其他测试/脚本不被升级为全仓库最新 HEAD 回归。
