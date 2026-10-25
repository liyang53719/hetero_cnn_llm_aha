# 真实四源编译与 selected-on CHIRRTL：严格分阶段证据

本片只确认两项实际结果：**PASS_ACTUAL_FOUR_SOURCE_SCALA_COMPILE_ONLY** 和 **PASS_ACTUAL_SELECTED_ON_CHIRRTL_STRUCTURE_ONLY**。不是 M1 行为/数值 PASS，不是 SystemVerilog/RTL 仿真、full29/fullblock 或硬件利用率验收。整体主任务不置 done；原完整 M128 软件终态/观测域及离线 packet 证据保持，所有历史 FAIL/TEMP 保留。

## 已实际执行并独审

1. **4 个 Scala 源的增量编译**：一次 JVM 编译 exit 0，生成 20 classes、670,644 B；Qwen2Block 11 类，其余三个源各 3 类。独立实际审查 7,649 条，按完整 class 容器、内部类名与 SourceFile 关联复核；不是只看文件存在。复用原 92 源编译的 550 类，不重编它们；原 PackedAttentionStreamClient 的源码/类不变，也不被新输出覆盖。
2. **仅 selected-on 的真实 Chisel 构造/CHIRRTL 生成**：一次 exit 0，生成 `ordered_on.fir` 13,164,852 B、112,270 行，SHA256 `908602bb6ed83012f5b37628108832f7d9f81ae72767308c52a9dff90dc3fc8c`。独立源知情文本结构审查记录 499,526 条条件，345 个模块全部可达、344 个实例、层次深度 5、164 个寄存器声明、34 个 memory 声明；未发现 blackbox/extmodule/intmodule 或未解析实例。另有元数据独审 9,514 条及最终补充 14 条；计数不是独立数值测试数。

真实 top 直接包含原 16 个 HeteroFP32Alu、1 个 BlockScalarFloat、1 个 PackedAttentionStreamClient、1 个 SharedL2Fabric、1 个 ElementwiseMemoryEngine、1 个 BlockWritebackFence。结构检查核对 9 对 client 无条件端口连接、原 SRAM/score/prob memory、ordered 状态与观察端口。该层级是源知情文本结构核验，**不是完整 FIRRTL 类型/语义/低级降低/逻辑等价证明**。

原 **4 条 W005 警告全部保留**：Qwen2Block.scala 629:57 的 4/5/6/7-bit 动态索引用于 Vec256，预期 8-bit；不能以结构通过把警告认作行为无害。未执行 selected-off 构造；源中有该入口不等于已验证。

## 独立探针副本与未来行为边界

`source/Qwen2Block.scala` 是独立测试副本，**不是原核心同字节文件**。三处只读探针插入增加 valid/index/data 输出并绑定两处真实 scores.write；`probe/score_write_probe.patch` 只改了公开 diff 标签，hunks 原字节不变。逆向移除恢复原 92-source pin 中的 Qwen2Block 每个字节。`OrderedQkBehaviorCore` 另加只读 observation。

实际 CHIRRTL 的两写点/探针静态绑定已核对：相同 guard/data；逻辑 probe index 为 16-bit，1024-entry scores 物理地址只取低 10-bit。**不能在有效范围之外宣称完整地址恒等，也不是全设计形式化 noninterference 证明。**

`OrderedQkBehaviorSpec.scala` 已编译，但本包没有它的实际执行成果。其 Memory/Matrix 是合成脚本端点，Memory 返回零 Q/K/V，QK 结果 tile/PV 结果由脚本提供，不验证真实 Matrix FMA、DDR/iDMA/Host 或原 M128 tile。原形状保持 H1536/FFN8960/12Q/2KV/headDim128/maxTokens1024，未来 job.m 1/2/3 不表示缩小 DUT 阵列。`accounting512Steps` 是人工输入账目，不是实测 MAC、周期或占空比。M1 以及其余 10 个预备 case 只能按新的独立准入单独执行；本片不把下一阶段结果预记 PASS。

## 历史错误不抹去

- 行为准备 r1/r2/r3 均保留冻结 hash：r2 修正受阻 early-done 的 tag/error 稳定性，明确 foreign 单拍撤回是 adversarial 非法 offer，而非合法 held terminal；增加独立 owner/PV/请求保持计数。r3 只修测试预算：框架自动 reset 1＋显式 reset 2＋body 99,997 ≤ 100,000 clocks。不是改原 DUT 时序。
- 原 16:13 结构 checker 把 child 的 `Reset` 误作 top 默认 reset。独审 STOP 后**从未执行该候选**，旧 source-only 可准入判断已被 STOP 替代。新 r2 通过固定 Chisel 字节码/旧 top-vs-child 序列化证据，严格要求 top `UInt<1>`，不接受两种类型兜底；Scala/classes/argv/阶段资源保持。后来的实际成功只属于新 r2，不能把旧 STOP 改写为通过。

## 资源、复现与安全发布

编译实测 aggregate CPU 24.605639536 s / engine wall 24.661326156987343 s / outer 24.737272515019868 s，采样 RSS 高水位 342,331,392 B。CHIRRTL 实测 aggregate CPU 10.688666565 s / engine wall 10.737593911006115 s / outer 10.797524068970233 s，采样 RSS 高水位 322,498,560 B。这些不是连续全树峰值或未来行为运行预算保证。

实际两阶段采用 CPU120/work120/total150 s，单 CPU、child AS4GiB、采样 RSS2GiB、log2MiB、单文件48MiB、输出树采样64MiB。CHIRRTL 的 cleanup 到130 s、postflight 到150 s，外层180 s；与更早 PLAN 的60秒结构提案**不是同一已执行配置**。子进程 CPU/AS/单文件是硬限制；aggregate CPU/RSS/树大小是采样门，不是 cgroup/全盘配额。清理只证明受锚定原进程组及已观察身份；不声称任意逃逸进程隔离。原始 receipts、资源边界、预后检与清理结论均单独绑定。

依赖 pin 固定官方 Maven 106 JAR / 77,940,074 B；原缺25项19,329,566 B已恢复。条目存在于 classpath 不等于全部实际加载，也不证明 Treadle 兼容；`chisel-plugin_2.13.16:6.7.0` 必须显式 `-Xplugin`。源/复现入口见 [REPRODUCE_ZH.md](REPRODUCE_ZH.md)。公开的是 4 Scala 源、小结构 checker/合成测试、pins、角色化参数及必要摘要；不含 JAR/class、13MB FIRRTL、大日志、私有 supervisor/config/路径/进程身份、模型权重或输入。**本片不含真实执行授权或可强制资源的 launcher。**
