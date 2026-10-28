# TEMP：共同 Dense 的实际 MoE groupRows 准入修复

**只改同一个 `TransposedDenseOwner.scala` 的两个普通 DDR-backed `TransposedDenseDownOwner` 行数准入谓词：M16/M128 → M1..128。** 反向替换后全文件与精确原源逐字相同。不是新增资格外壳、调度器或第二套 Dense；专用 FFN window/drain 及该文件其他旧普通/Seed owner 的 M16/M128 资格和特化索引均不动。

## 实际编译与证据

本次一次真实增量 Scala 编译 **1 源 +993 baseline →8 新类**，native exit0、空日志、wall33.567秒、CPU26.86秒、RSS351899648B、tree18624151B，前后各3602严格pin一致。前代950+51=1001类，整SourceFile族移除8旧类后再编译，不留旧class阴影或stub。

最终 **31源159类 =30继承源151类 +1新编译源8类**，并非31源全重编。993baseline=(855−旧RMS3−旧Router2−旧Dense8)+151=842+151。`SOURCE_PINS.json`列1新源、24公开继承源、6 requires-parent；`CLASS_LINEAGE.json`保留精确摘要，字节恰好相同的重新编译类仍按实际来源归类。

普通Python与`-O`通过7680整数调度/地址/计数案例、5类源码破坏负控；独审另1536行/地址案例，4项当前只读准备metadata测试也通过。它们是源码/整数模型，不是DUT协议或数值证据。实际class/source/pin闭包另独审，`EVIDENCE_PINS.json`绑定原始receipt、独审及最终51项冻结证据。

## 真正保持的数据路径和成本

- 普通A DDR只读实际m行，终止使用加宽`+&`比较覆盖m=128。
- 每Kchunk仍清全部128物理行；最大clearWords1280不超过既有1376容量。发射前另显式mask inactive行。
- usefulMAC只按实际m×N×K；4096物理MAC及完整physical成本保留，不能把padding或物理空算计为有效工作。
- 原K顺序、chunk FP32 prefix、完整16KiB/context存取、最终BF16舍入及Qwen2 FP32存储不变。输出只写实际m行，真实ACK才累计m×N×dtypeBytes。
- 不增加Module、数值寄存器、FPU、Matrix、formatter、DMA、bank或接口位宽。原32 SRAM banks/786432B与4096MAC仍是同一硬件定义；准入比较逻辑改变不等于综合面积/时序零变化。
- 小groupRows仍支付完整物理阵列/前缀成本，scratch不随m缩小；没有90%利用率、性能增益或QoR实测。

## 既有入口与未关闭门

现有实际postNorm→Guard物理退休→allocator→router/routed/shared FFN→sigmoid→merge→residual的身份接线已经源码独审，不重复添加wrapper。三个既有MoE job builder将完整当前bundle清零，未设public21Reduction，因此保持false；这不是elaboration/DUT执行证明。

本批仅关闭普通生产Down的动态行准入限制，**不等于整MoE或任意M整链验收**。原路由、官方expert IDs、tie policy未改；专家同分契约仍待定。非零profile最终launch seal、Host finalACK及cache/state双根fence未开放。

原Dense可读source92重建与当前baseline整族身份已核，**缺失历史原compile receipt未重查**，不伪造路径或继承为完整档案PASS。本次整族新编译建立独立当前证据；历史missing/budget-skipped边界仍保留，active输入闭包PASS不是完整历史JSON图PASS。

`REPRODUCTION.json`为精确argv占位配方/caps，仍需父级完整source/build/class闭包、106 jars、314-file JDK及原严格有界supervisor。无二进制/权重payload，不是fresh-checkout自包含复现或新启动许可。

从包目录复核（原Dense源必须精确匹配`SOURCE_PINS.json`）：

```sh
python -B verify_package.py
python -B check_dense_rows.py --original-dense-source /path/to/original/TransposedDenseOwner.scala
python -B -O verify_package.py
python -B -O check_dense_rows.py --original-dense-source /path/to/original/TransposedDenseOwner.scala
```

**没有Chisel elaboration、IR/RTL生成、DUT数值/协议仿真或QoR；完整五profile M128 Chisel及同RTL验收仍0/5。** 下一门仍是同一Top初始化/位宽/组合环/物理实例资源检查、完整128-token数值、同刺激RTL与最终ACK双根fence；不以此TEMP源码/编译结果替代。
