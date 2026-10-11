# Qwen2 M128 全图数据流：实际数值闭包与生产接线边界

本轮在同一转置 Dense 候选内完成 down 的 K 外循环/真实地址 DDR-prefix，以及
FFN gate→up→SiLU 的真实 SRAM tile 依赖。原始 layer0 输入和权重不变，cold M16
一次 98.9516 秒、cold M128 一次 159.9114 秒，全部 15 阶段合计 5,971,968 个
FP32 值逐位等于冻结 v0 基线。M128 单例为 5,308,416 值。独立复核重新读取全部
30 个文件，核对 CPP/ELF/header/input/日志/收据，并重算所有 19 个 owner 流量。
[执行身份和摘要](../reports/execution/QWEN2_FULLGRAPH_DATAFLOW_20261011/SUMMARY.json)
保存旧 work driver 的真实运行身份；后续打包入口没有继承一次未执行的运行。

这是普通 C++ 软件模型。没有执行 Chisel、RTL、真实 iDMA 或 leaf 流水线；原
M128 官方 BF16 阶段门和 FP32 最终门继续 FAIL，数值政策决定仍 open。有限数域、
+0 初始化、递增 K 的 FP32 FMA、终值 bias、SiLU 运算顺序及门限均未修改。

## M16 为何仍接近百秒

计时仅覆盖 R.execute 的子进程墙钟，包括原 arena 加载、算术、观测输出写盘和
stdout；不包含编译、父进程输入哈希或阶段比较。两个 M 都执行相同的物理 M128
Dense 布局：1,462,272 次 wide issue × 4096 = 5,989,466,112 次 std::fma。
M16 只有 748,683,264 次有用 Dense MAC，另 5,240,782,848 次是 padding，占
87.5%；padding 仍执行 FMA，只省略无效 M 的 A 读/解码。Attention 的实际模型
FMA 数分别为 1,179,648 / 29,884,416。M16 的搬运、SiLU 和 Attention 标量工作
较少，所以更快，但它并非 M128 的八分之一工作量。CPU 秒数不用于推算硬件周期。

## 当前选择的同资源数据流

down 的 K 分块为 2560/2560/2560/1280，K 外循环保证 A 和权重各读一次。
每个 N32 context 在独立 DDR prefix 区占 16,384 B，48 个 context 共 786,432 B。
三个块边界合计每方向 2,359,296 B。地址由 context 和真实物理 row/column 推导，
明确转换 C++ slice-major 索引与接口 row-major 顺序；只增加一个 64 B seed hold，
没有隐藏整 tile 缓冲。M128 实际执行得到 144 个 prefix ACK、48 个最终 ACK，
全量输出和终态 ACK 到齐后才发布。

FFN 保留 postNorm 的 M128×K1536 BF16 输入，占 A 的 393,216 B；三个 FP32
M128×N160 槽各 81,920 B，依次存 gate、up、act。A 总占用 638,976/704,512 B，
剩 65,536 B，B 仍为 81,920 B。gate/up 由 Matrix 结果写真实 bank 坐标，SiLU
只读这些实际写入，act 写真实模型 DDR，down 读取实际 act。gate/up 的两个完整
观测副本仅供 host 导出；算术 get/put 对其 DDR 地址及别名都显式拒绝。

保留原 4096 FMA、五个累加 context、八个 metadata、两 result slot、finalValue
及 leaf 原有五组内部 result。所有 refill/compute/transfer 串行，不计免费重叠。
新的 FFN FP32 写需要 32-bit mask 或 RMW；A 的 16-bank refill 需要实际写路由，
不得把原单 bank DMA 写口说成已具备。RMW 响应若允许停顿，需另列 512 B hold。
原 688/80 KiB 容量保持不等于 mux、布线、寄存器和频率免费。

## 流量变化与 MAC 口径

| 同一 M128 全图映射 | 外部读写总 B | 理想互斥 64 B/拍下的乐观 MAC 上界 |
|---|---:|---:|
| 全转置、down 每 N160 重读 A | 187,432,960 | 50.1415% |
| down K 外循环＋DDR-prefix | 150,863,872 | 62.2957% |
| 本轮再接 FFN SRAM tile | 131,727,360 | 71.3456% |

本轮读 115,998,720 B、写 15,728,640 B，共 2,058,240 个理想 64 B 传输。
相对全转置、down 重读 A 方案节省 55,705,600 B；FFN 融合部分独立节省 19,136,512 B，来自
9,175,040 B gate/up 写、9,175,040 B SiLU 读和 786,432 B 重复 postNorm 读。

8 个修改路径使用实际软件传输计数，11 个未改 owner 使用既有源码事件公式。
因此这是混合模型账本，不是真实 iDMA trace。公式仍为完整有用 MAC
6,014,828,544 / (4096 × 完整周期下界)，保留原互斥读写 adapter 和 64 B/拍条件。
还没计入命令/描述符、真实 ACK/DDR 等待、SFU、仲裁和路由时序，71.3456% 不是
实测值或可行周期预测，也尚未达到用户 80%/90% 目标。

最近的局部流量机会是 postNorm 直接写 FFN 保留 A，省去 786,432 B 写和同量读，
理论总数可到 130,154,496 B；尚未实现或验真。仅上述 payload 条件下，80% 要求
总流量不超过 117,477,120 B，当前还差 14,250,240 B，故这个局部机会不足以达标。
更大的 act→down 往返为 9,175,040 B，但 FFN A 只余 65,536 B，down K2560 的
BF16 A 块需要 655,360 B，不能直接宣称可省；须重新排共享 A/FMA/context 生命周期。
现有 Norm 只走 DDR write/ACK，A DMA 只选单 bank，16-bank scatter/RMW、保留 A
跨 owner 提交和故障失效都待实接。优先做当前方案的 Chisel 增量，不先假设重叠。

## 下一条真正 Chisel 依赖

选定“前六个 K1536 全 A 驻留、down K 外循环 prefix、FFN tile”作为当前模型实现
基线，停止并行造新的映射分支。下一源码增量先把两组 weight A16 与 M128 activation
的路由接进原 MatrixPipelineService：原八片 retained endpoint、固定运算和旧模式
保持，新增显式模式的 group 锁存及输入解码；不能仅做脱离 service 的新阵列。
之后接实际 bank 地址/写权限和 StreamingDense owner，再接 prefix seed/ACK、
FFN SRAM scalar consumer 与原 Host 生命周期。生产 dispatch 尚未实现融合。

先复用锁定 Scala/Chisel 前端验证默认模式结构和新分组/资源，配合真实地址/共享
端口模型反例，再做必要的小接口时序门。原 native 失败不因此关闭，最终完整硬件
验收仍需冻结输入回放。不可把局部 frontend 或本轮软件位精确当作整 block 通过。

## 验证和清单

合成小闭包 39,680 个 down 值及 185,856 个整图值精确；检查 8,192 个不对称
物理 prefix 坐标、48 个 context、高半 ACK bitmap、最后地址、43 个协议拒绝、
10 个 FFN 生命周期拒绝、9 个数值域拒绝及18个禁止DDR访问。直接修改实际 DDR
或 SRAM producer 能影响相应 consumer，排除了从观测副本取结果。首次 source
抽取失败和两轮早期小门保留；最终第04轮补齐 tags、发布范围和物理覆盖后才跑
M16/M128，两例均一次成功，无超时或重试。

- done（软件局部）：同一真实输入 cold M16/M128 全 15 阶段数据流/存储位精确。
- done（软件局部）：prefix/FFN 生命周期和禁止中间 DDR 读取的小门。
- ongoing：具体 Chisel 路由、实际共享端口、seed/ACK 与 Host 融合接线。
- ongoing：全周期预测、原 native/FP32-final FAIL 和数值政策决定。
- to do：carried、更长 prefill、真实控制时序及最终完整硬件门。
- 保持 Q21.3/U00.2 ongoing、U01 to do、C02.2 OPEN。

打包入口另外完成 67 项新小测试与 27 项既有转置回归，共94项；其中 tiny C++
实际执行 H32/F224/M16 的15阶段、16,896值，不能作为完整small准入。再顺序实跑
新入口完整 bounded-small（3个合成整图＋10个down用例），核对225,536值位精确。
原先缺少small证明日志字段和执行后产物身份复核的问题已修，并增加负测；上述
检查不重新执行实际形状M16/M128，不追认新runner具有旧runner的完整运行结果。
