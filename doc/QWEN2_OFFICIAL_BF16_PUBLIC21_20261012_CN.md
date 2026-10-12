# Qwen2 完整公开21命令的官方 BF16 物化接入

2026-10-12 10:50:23 UTC 用户选择按官方 BF16 的舍入和中间精度修改当前完整链。该决定授权物化规则修改；原逐算子 max_abs≤0.03125、mean_abs≤0.005 和末输出 max_abs≤0.05、mean_abs≤0.01 均不变。FP32 为误差诊断，原 v0 失败保留。Q21.3/U00.2 ongoing、U01 todo、C02.2 OPEN。

## 已执行的完整 M16 软件链

从固定 Qwen2-1.5B L0 的16个 raw embedding、原权重/常量开始，使用同一个公开 Command128/descriptor frontend、同一物理地址内存、Matrix/Scalar、FFN A/B banks、prefix workspace 与原写 ACK/公开完成路径。raw QKV、KV、Attention、O、residual、postNorm、Gate/Up、SiLU×Up、Down、final residual 都由本次实际前驱写回消费。预载中间张量为零，参考数据在唯一整链终态后才允许读取。

11:27:13 UTC 到达21个公开完成、17个owner返回和唯一一次launch完成。全部原地址范围/哨兵/旧输出共存、末 ACK 与公开发布栅栏通过。主机运行532.523秒、CPU532.435秒，峰值270.4MiB；这是 Python/C++源对应的事务模型，未执行Chisel硬件仿真或RTL。3,798,010模型tick不是硬件周期。

- 15个主输出（含Gate/Up）以及实际内部score/logit/softmax/probability/PV/SiLU六项，与冻结独立BF16算术逐bit一致。19个实际输出（另含raw QKV/KV）均封存字节数和SHA；raw QKV/KV的封存不等于额外独立算术比较。
- 原执行快照84源SHA `88cc7fe74bbe0a982490f138c99928314c325ded5de73fc50296d5c0cf5c17e2`；原终态摘要SHA `1543618fb894864d1e8a97605b69b424518e9d209ee38de3aa4064ba3367b3bd`；实际共享算术ELF SHA `bcab4d36ae7990bf6b40c08866066b563d8c6c09fb134a2393d8268505c89c7f`。
- 首次官方比较仅Q/K报大差。独立读回发现历史M16参考Q/K保存为token-major，M128保存为head-major。原native元数据、8份归档hash、logical hash及cold K/cache恒等关系分别证明布局；不能按误差大小猜转置。新的读取器按固定case/文件hash读取，并保留原错误比较。
- 对同一次封存实际结果重新比较后，两来源所有已观测BF16节点都过原门：官方Q max=0.00048828125、mean=3.50798e-8，K逐bit相同；独立Q/K max均0.0001220703125。没有重跑实际链或官方forward，没有改阈值。原始参考producer SHA `917d56f038c646606e9dc67d1d36752f70097adec9748db55b2a915af8147c85`；native RESULT M16/M128 SHA分别`b6206444a95453770ce3131998000aece244e182e45bebeef841038dd8b2d6a6`/`10ad341ee67fc12f1c619c60716647f29110fa49cd8f17163136059f78cb5315`。
- 后处理第一次未固定原OpenBLAS/OMP单线程，极低位cosine元数据与原回执不等，被“除Q/K外完整比较必须相同”守卫拒绝；固定原单线程后通过。现在入口显式要求这两个环境变量为1。原失败与两次后处理来源分别记录。

此结果不关闭完整29节点门：实际owner没有执行future score，presence保持缺失；显式mask tensor没有物化，FP32 softmax逐元素门尚无批准容差。它也不是M128、carried prefill或硬件数值通过。历史M128 QK全形状后端差异仍保留，不能用M16改写它。

## 本次精度和实际源码对应

- RMS1536按冻结Torch CPU归约顺序 V8/ILP4：8 lane、4 residue、每组3个512区间、每区16项；平方、归约、mean/epsilon、sqrt/reciprocal用FP32，归一化及乘直接gamma分别BF16 RNE。当前Qwen2 gamma没有GDN的1+weight含义。
- Q/K/V的Dense+bias之间保留FP32原始投影，bias之后BF16；Dense O/Gate/Up/Down在完整K末端BF16。Down的2560/5120/7680 prefix继续FP32，8960才物化BF16。
- RoPE按原split-half布局，trig、乘积及和分别BF16；完整存储容器仍是4B FP32展开值。不能误用packed BF16 descriptor改变stride/writeBytes。
- QK仍为原16条带FMA归约，完整dot及scale后BF16；原softmax近似与次序保持，prob和PV末端BF16。SiLU原16-lane阶段图不变，阶段4及与Up相乘阶段5物化BF16。残差相加后BF16，原全tile先计算再store和异常拒绝不变。
- 显式`Qwen2OfficialBf16V2` Chisel策略在原resident/group源码链组合，原默认`LegacyV0`保留。公开命令仍走原角色/shape/地址检查；内部job新增独立materializeDenseOutput位，不借packed dtype别名，也不为raw QKV提前舍入。

实际对应patch为[同目录候选](../candidates/qwen2_resident_matrix/official_bf16/)。8个生产源码postimage在隔离目录组合；历史20份Qwen3.5/stack未提交候选没有改动或混入本次提交。候选必须显式启用；当前未声称默认生产RTL已切换。

## Chisel前端与资源证据

90份Scala（66实际生产源码、20固定HardFloat、3个更名前patch叶基线和harness）已类型检查；Host parser、1lane SiLU、缩小SRAM深度的实际16-ALU Elementwise各4模式共12份CHIRRTL通过，68.38秒。没有调用firtool/Verilator，也没有完整Host/core/Matrix elaboration或硬件数值回放。

- 三个叶的默认参数与显式LegacyV0正规化IR完全相同；prepatch Elementwise相同。
- prepatch Host/SiLU的差异是未优化的false策略布尔项、恒真role guard和新增内部job位的false赋值。Host比较两侧使用同一扩展job bundle，因此不据此宣称历史内部ABI等价。
- 官方Host模式声明1424个额外metadata寄存器bit；SiLU/Elementwise寄存器、模块实例、SRAM声明和端口没有增加。完整RMS源码另有3个FP32 partial寄存器，但未在本次叶IR测量。没有增加Matrix/Vector/SFU阵列；面积、时序、功耗及完整top资源仍需后续验证。
- 原frontend摘要SHA `c5ea6276caf2d6ff4aa90fc9b92b19d352f80e5cb69427bbac2e45f097160b5b`，紧凑回执SHA `6c48669cef66fe23468d10764e8e6457de3d90dd5b00684fb165af6ec575294f`。

## 只读观测和下一门

原M16采用CPython settrace读取真实因果节点。为避免观察器主机开销淹没M128的原1200秒预算，新增CPython3.12局部sys.monitoring传输，仅选择同三个实际code object、同语句点和真实tick返回值。15小门及原10观测门证明M1/M2全部输出、每条握手、服务计数、10字段的bits/presence/次数完全相同。独立review发现并修复wrong-thread退出和外部替换local mask的清理问题；不能夺取其他工具的注册。

这些主机小门不能证明M128完成预算，更不代表硬件加速。M128先验将分别绑定同算术/物理链M16实值、诊断布局修正和传输等价门，新增诊断源独立冻结；绝不将新源码悄悄绑定到旧全源PASS。

- done（局部）：官方BF16完整cold M16公开事务模型、原门下已观测节点、独立review、Chisel类型/有界前端。
- done（发布）：8a3e2fc 精确远端源码与本轮三个 CI、工件已核验；详见下节。
- done（实现正确性局部）：cold M128公开软件链完整终态、15+6固定算术逐bit一致及935项独立读回审查；原1200秒失败保留。
- ongoing（模型质量）：官方scores/logits仍超原门，独立BF16另有gate/prob超门，不能关闭整块数值验收。
- todo：真实carried/更长prefill、完整29节点和原质量门、完整Chisel/RTL冻结刺激回放。
- 五block M128总体：Qwen2 L0正推进；0.8B L0/L3仅先前两个M1实际RTL范围；35B-A3B L0/L3尚无完整数值执行。均不能称五块M128通过。

当前物理映射与资源没有因这次数值修正改变。旧v0 M128对应有效MAC/4096固定资源的issue上界48.19%、共享64B流量假设上界40.34%保留其原source/workload身份；尚无本次whole-wall硬件周期，不能把软件tick或观测器速度换算MAC利用率。

发布前另在全新纯源码checkout按新增workflow步骤顺序现编共享库、完成67软件测试及33源码/前端守卫，再真实编译90Scala、生成12叶CHIRRTL并按CI glob收集29项工件。新增frontend72.482秒，12份正规化IR与首轮完全相同；旧778测试/131IR本地未重复，后续CI会按原workflow执行。纯源码首次clone未携带不可达baseline，被source测试在编译前拒绝；显式补齐原workflow已规定的7个固定fetch/probe后续行，保留失败记录。独立review还补上两个tee步骤的显式bash/pipefail和2个失败传播小门，未改数值或预算。冷门摘要SHA `e5c1a8fb58e230e3b19cd0586661d101623a4e0d9c66c7b77a1fc0b893200e62`。


## 8a3e2fc 远端终态与 M128 预算诊断

[源码提交](https://github.com/liyang53719/hetero_cnn_llm_aha/commit/8a3e2fcff27f869e284da2f736fad38322858f13) 的三个原 CI 均成功，未重启：

- [model-contract 38245601441](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38245601441)：441 tests。ZIP 283805 B，SHA `e2267d61b59ee75262b9c96d07129b48a5efc372102967fe4bfe73fa8c9a4efd`，共享旧 Matrix/SiLU 库的三源与编译 receipt 已核验；该库不能冒充新官方物化库。
- [frontend 38245601426](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38245601426)：811 tests、143份CHIRRTL；新增90 Scala及12叶IR。ZIP 50305334 B，SHA `075bad9a6229c829ab0807233004ffb99bdd35e823d5608b2cbd32106c4e2c6c`。96项编译源身份与本地冻结来源相同；下载后的新增12原始IR长度/hash正确，规范化后与本地逐字相同。工件不包含这96源的原文，另从保留的本地冻结源逐项复核。此处仍是前端证据，没有RTL执行。
- payload guard成功。未向Git上传输入、权重或NPZ。

第一次实际M128在1200.080849秒抛出 `full group host budget exceeded`：pc0–15已完成，FFN54/56窗，Act ACK 4423680 B，whole terminal=0；Down和最后残差尚未执行，官方节点比较未开始。这是本轮软件预算失败，不能报整块或数值通过。原摘要SHA `45b925ebfc17760b00e37b7408038d4d1898c3d2831a24650454aae4690cddab`、86源快照SHA `22617b51a058b105989ecc0915f77245602d7ed0a967cc83584cc33b1b25e9de`及原日志保留。

完成记录的文件时间显示FFN稳定窗口平均6.4886秒；剩两窗约13秒。已完成M16的Down实测137.835秒，M16也走128物理行，不能简单乘8。根据已完成Dense/FFN比率估计M128 Down约200–285秒，再留10–25秒给末Add、封存和比较，完整软件运行规划值1423–1523秒；这些是主机时间估计，不是硬件周期或利用率。本次将默认1200秒保留，并允许明确指定一次1800秒上限；进程外1860秒看门狗独立保留。

旧进程没有可恢复的Python生成器/Matrix bank checkpoint；保留回执不足以续算。旧runner在全suffix成功后才保存Attention十字段，因此本次超时也丢失了其内存中的实际数组，不能用reference补回。新runner仅在错误退出路径复制已发布、完整ACK并有terminal的普通物理输出，排除权重、未发布Act、workspace和虚拟区，并保存关闭后的原始Attention观测。观测的INCOMPLETE状态及已接受的局部terminal原样保留；保存不发布、不打开reference gate、不宣称block成功或可续跑。诊断写盘失败也保留原错误。

12个小守卫在不含历史work目录的纯源码导出中通过；独立review还发现并修复了AST白名单可被移到成功路径的缺口，现只允许诊断块位于原错误handler的指定位置，原raise/终态/算术变化均拒绝。原M16封存实际数据重新比较约1秒，固定算术和原BF16已观测门保持通过，没有再跑M16或官方forward。新的M128快照SHA `5b9247588ddddcada1e669034c3e8e0a17ffb39c6c6aef3ffd1bb5e49c6924ab` 仅runner与上一快照不同，全部算术、物理驱动、原始输入和ELF相同。2026-10-12 12:13 UTC启动的唯一1800秒运行在本次记录时仍进行中，不提前登记PASS。


## cold M128 完整终态与仍开放的官方差异

上述唯一1800秒运行于12:36:14 UTC成功退出，主机1369.129秒、whole terminal1367.008秒，Down实测156.737秒（早先200–285秒是规划估计）。公开21命令、17 owner、唯一最终结果、所有实际ACK与workspace三次prefix续算均完成。19实际输出及10组内部观测已封存；15主阶段+6观测节点逐bit对冻结算术通过。另一检查器完成935项来源/字节/覆盖/ACK复核。[紧凑结果与可复现脚本](../reports/execution/QWEN2_OFFICIAL_PUBLIC21_20261012/README.md)。

原官方门仍FAIL：99,072个实际causal scores/logits有11差，max8/mean0.000565245；独立BF16 scores/logits max2、gate max0.041015625、prob max0.031494140625。原max0.03125/mean0.005不变；97,536未执行future位置没有填数，显式mask和完整29节点门仍不闭合。

本次实际n0与官方逐bit一致，K也相同，QR有40个、RoPE后Q有19个bit差（max0.0078125）。对真实Q/K的完整形状孤立官方QK重放，全部99,072个实际causal值与owner逐bit相同；换回官方Q/K才出现上述11差，全部来自head9/query102。官方自身Q/K重放全部196,608 scores等于保存参考，确保没有用小形状算子代替全形状。当前cold问题定位到上游Q投影，不能继续误改QK、scale、RMS或mask。

全部40个不同QR位置的独立有理数1536项计算精确复现当前顺序FP32 FMA与实际qraw；用精确点积再舍入仅27/40匹配官方。因此后续研究通用、Chisel可实现的归约规则及其寄存器/端口/周期代价，区分BF16物化语义和固定CPU实现，不按单点硬编码，也不宣称增加精度免费解决。未采用新累加器、资源扩容或放宽门限。

f1d1324对应model CI445tests、frontend811tests/143IR及payload三门全成功；model/frontend两份工件已下载、hash核验，143IR原始字节全部与上一8a3e2fc相同。此次主机17,010,491 tick不代表硬件cycle；有效MAC6,014,828,544、执行MAC6,801,063,936、writeBytes13,369,344均来自实际owner汇总。五个block M128的总体验收仍未通过。
