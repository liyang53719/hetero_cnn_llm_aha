# TEMP：真实 Residual1 → postNorm → FFN 输入收据

本批是 `host_runtime_output` 的小步实际接线延续，不是完整模型完成或新调度器。**5 份真实源码已做一次增量 Scala 类型编译：961 baseline → 39 新类；最终 29 源 / 148 类 = 5 新源 39 类 + 24 继承源 109 类。并未重编全部 29 源。** native exit 0、日志为空，59.210 秒，前后各 3347 项严格 pin 检查一致。

## 已接入的真实路径

- Prefix 保存实际 Elementwise Add0 Residual1 完成握手的完整 Host、transaction64、物理 job/result、真实 ACK 与服务计数。readonly 预加载、inputNorm 或 DenseO 成功不能代替生产者。
- 复用同一个 RMS owner 和原 Guard/Kernel/Top：mode8、kind1/stage69、Scalar8/Format9，保留 phase0=inputNorm、phase3=postNorm；没有新 kind10/stage78。物理接受核完整身份、严格 P<C、非 sentinel、不可重放。
- 专用 RMS accepted/result 与真实 done.fire、内存/scalar/format 六计数、写 ACK、adapter lease 和 drained 一致后才产生独立私有 postNorm proof。Top 将 proof 实接 Commands，非 Host 授权位。
- 两个 Commands done handler 在首次暴露 completion 前拒绝缺失/不匹配 proof。runtime postNorm 的原 done 只保留 pending；只有 **completion.fire** 时 proof/typed input、gamma、output/Host/txn 不变且无 fault，才提交 FFN 输入。late fault 不改 held completion；已提交结构快照保留以免撤回 held MoE intent，但资格输出立即 mask。
- GDN profiles1/3 为 M16/M128，Attention2/4 为 M128，cold generation0。RMS 叶子的 1..128 行支持不等于整链支持。

## 数值与资源边界

保留原 lane8/residue4/512-block reduction 的 FP32 primitive 次序及所有 +0 节点、epsilon1e-6、sqrt/inverse、normalize→(1+gamma)→weighted→一次 BF16 formatter。H1024/2048 的 M128 合同分别为 Scalar 669184/1332736、formatter 131072/262144、memory 16384/32768、output ACK 262144/524288 字节。这里是源码/计数合同，**不是 DUT 数值实测**；Qwen2 FP32 存储分支不变。

原 RMS 的三组 32×512-bit 缓存共 49152 bits，加四个 FP32 工作寄存器 128 bits，共 **49280 bits 数值存储保持不变**，不是新分配。新增五个32-bit计数寄存器160 bits；memoryReturned复用原sequence。phase/full accepted/result、Host/txn/producer/pending 等控制元数据另增，非零面积、没有综合总面积结论。仍为原17-client hub/client1、32-lane shared bank、4096-MAC Matrix；不新增 FPU/Matrix/DMA/formatter。

已公开未接受请求保持 held；未公开 intent 不误记外部债。mode8 仅对 adapter 已接受的 registered Scalar debt 越过 leaf poison，不能越过 Core/physical/quarantine/conflict。未知回复或 poisoned service 仍可能需要 joint isolation/reset；不退款、不伪造 drain、不承诺无条件有限排空。FFN receipt 不替代原 allocator 的真实资源 retirement/drain。

## 可复核材料与未完成门

`SOURCE_PINS.json`：5 新源、18 已公开继承源、6 requires-parent 源。`CLASS_LINEAGE.json`：996−35=961，其中原855祖先去掉旧RMS3类，故 **852+109=961**；前代141类去掉32类后继承109类。原 RMS source/三旧 class 的精确 ancestry 见 `SOURCE_PROVENANCE.json`。

`REPRODUCTION.json` 只提供精确 argv 占位配方与 caps；仍需父级完整源码/build/class 闭包、106 jars、314-file JDK 及原严格有界 supervisor。未提供这些二进制，不宣称 fresh-checkout 自包含复现，也不是新启动授权。当前实际输入闭包 PASS 不代表历史 JSON 全图 PASS：旧 missing/budget-skipped 引用仍未补齐，历史诊断不是本批新扫描。

小检查（普通 Python 和 `-O` 均通过）：79 个当前功能模型（RMS19、Prefix24、Commands36），源码防线/突变；另15个真正独立 reviewer 检查、47合同/31突变和实际 class/pin 独审。历史作者87模型包含8个准备前提测试，其中“actual目录不存在”仅编译前成立，**不把编译后重跑称 PASS**。保留初始 checker 断言/突变作用域修正及独审 MUTF8/section-selector harness 错误；它们不是 compiler/DUT 失败。一次真实类型编译首轮通过。保存的 owned-cleanup proof 由原 runner 当时验证；后审仅复核保存身份/时序/scan 摘要，未重观察已结束 handle、未声称保留 raw scans。

从包目录运行（外部原 RMS 必须与 `SOURCE_PINS.json` 完全匹配）：

```sh
python -B verify_package.py
python -B check_commands_postnorm.py
python -B check_postnorm_prefix.py
python -B check_rms_kernel.py --original-rms-source /path/to/original/GdnRuntimeRmsNormOwnerV3.scala
python -B tests/test_commands_postnorm.py
python -B tests/test_postnorm_prefix.py
python -B tests/test_rms_kernel.py --original-rms-source /path/to/original/GdnRuntimeRmsNormOwnerV3.scala
```

把 `python -B` 换为 `python -B -O` 可复核优化模式。源码基线检查还需要相邻已发布 `host_runtime_output`。

**未运行 Chisel elaboration、RTL、DUT、primitive 数值/协议仿真、QoR；完整五 profile M128 与同一 RTL 验收仍 0/5。** profiles1..4 最终 launch seal 与 cache/state 双根 fence 未开放。下一门是实际 Dense FFN / MoE 全链、Residual2、原 Host final ACK/双根 fence，再做同一 Top 的初始化/组合环/实例资源/协议数值与同 RTL 验收；本收据不替代这些门。
