# 连续 PC01 三轨只读全量比较 SOURCE

状态：SOURCE_ONLY。只执行了合成数据与 mock 冷测；未运行 RTL、未重新计算参考模型、未读取真实完整 capture 或参考数组。

## 固定接口

唯一消费接口为 `compare(capture_root, reference_root, reference_receipt, *, shared_stop) -> observation`。`load_compare(source_root)` 校验固定 compare.py 的 size/SHA，执行同一个已校验 buffer，返回该函数；caller 先按固定 pin 加载 loader。路径全部来自 caller 私有配置，没有公开机器路径，也没有新增 CLI/native child 或文件写出。

capture 固定三件：counts.json、actual_n0.f32le、actual_qraw.f32le。参考固定三份已被 actual 独审接受的完整输出，以及该输出目录的 RESULT.json 原 1249 字节收据。三输出 SHA 在生产中独立固定，不采用收据自述来设定期望。每次文件读取以 O_NOFOLLOW 逐目录走 fd、拒绝特殊文件、限定长度、核稳定前后 stat；数值消费同 buffer，结束后再次复核全部七文件的 size/SHA/bytes。

消费者不安装、取消或扩展 signal timer。局部停止时刻为 min(开始+60秒, caller 已有 shared_stop)，64KiB 读块和每256个数值检查截止，最终观察对象构造后再检查。caller 必须在既有 ≤10800 秒总窗中预留比较与收尾，并保留外层硬截止；不能以此函数创建新资源窗口。原异常直接传播。

## capture 前置与资格边界

严格沿已发布 pc01_main.cpp 的 41 个顶层字段和 15 个 AXI ledger 字段读取；缺失、额外字段、重复 JSON key、NaN/Infinity、把 bool 冒作 uint64 都拒绝。固定 ACK0/ACK1、jobs/dones/launch/post-PC、786432 字节/196608 值、矩阵 wide73728/slice589824、binaryAdd12288 与 MAC301989888；窗口/总周期/利用率/AXI 读写退休交叉核对。qraw B 预期为 2048，不能沿用 N0 的 12288：固定 burstWrites/160列窗口（末尾96列）、qraw 基址模1024为64、最多16beat且不跨1KiB，逐行10窗口的 descriptor 数为 [1,2,1,2,2,1,2,2,1,2]，16×128=2048。完整 W beats 仍为12288，覆盖786432字节。

freshPC0 actual_n0.f32le 必须完整匹配原 3c25077e…SHA；qraw 必须完整且有限。消费者只授数据观察，不能凭 counts 的成功 status 或若干布尔值声称 native/RTL 资格。counts 没有独立打印 N0 B/writeback 或 ACK1 completion payload；这些是已审 driver 成功路径的强门，只能结合 caller 真正关联的固定源、同一 native phase 的自然退出0及 cleanup 证明，不能称为消费者独立观测。caller 另核原参考实际执行收据/三阶段自然退出与 cleanup。新鲜进程、同 RAM、输入来源与控制流资格由 caller 保持。

## 三轨分开

- typed_reference：完整196608个FP32逐bit比较、hash_exact、mismatch计数与首错位置。+0/-0 按位不同。位不匹配仍返回完整观察，不跳过数学诊断，不自动授予或改变阈值。
- mathematical_fp32：actual FP32 对数学 RN-FP32 导出值。
- mathematical_fp64：actual FP32 精确拓宽到FP64，对数学 RN-FP64 导出值。FP64的ULP不能与FP32的ULP混用。

两数学轨均以整数计算导出浮点值之间的完整绝对误差最大值/总和（分别2^-149、2^-1074单位），附FP64近似最大值/均值、完整ULP七分桶、最坏位置、非零参考的精确相对误差比及零参考计数。所有approx字段仅是近似表示，可能下溢为0；精确整数总量仍保留。近似相对误差若溢出则标记overflow并返回null，不输出非法JSON Infinity。ULP映射与原模型一致：+0/-0距离0，bit equality另列。

这些误差相对的是已经 RN-even 导出的数学 FP32/FP64 值，不能冒充对未舍入实数点积的全量精确误差。official_raw_numeric_pass、application_accuracy_pass、typed_recipe_bit_exact_to_rtl 仍为null，full_block_pass=false，new_tolerance=null。后续 caller 只能在原实际监督资格闭合后分别报告 typed 匹配与数学诊断。

## 冷测

普通/-O/搬迁普通/搬迁-O 各48例通过，每模式约3秒。包含完整196608个合成值的正例、末元素差异与非有限数、全ULP分桶、两浮点宽度/次正规/符号零、均值下溢及相对误差溢出、deadline交集及最终构造越界、参考/收据/N0替换、ACK/覆盖/AXI负例、同buffer竞争、symlink/FIFO、source篡改与搬迁。全量合成端到端只在测试进程内替换预期 fixture pins，生产常量和文件字节不改；不据此声称真实 capture 通过。

## B 计数来源独审

qraw 专属 B=2048 的有限源审为 review_pc01_source_cycle_floor_20261019T1934：MANIFEST 168字节/SHA256 373011e9464437afa0181aaf907740d03b99976539b78563fe060fc626403395，SUMMARY 5047字节/SHA256 d5181a15ff32fe62cd1849a67c05f3cbc5156baf1a2f38653f9559cc1ea3c171。B_SOURCE_DERIVATION.json 记录固定配置、descriptor 分窗与原件位置；这只证明该固定源的期望计数，没有新增 actual 结果。

## SOURCE 独立审查

冻结来源 MANIFEST 为 3055 字节 / a77e371a5a927ca1dd4837eff66c7947310faa09a0a9f1ba7de05d6a5a81f9ce，21 个成员、16 项 producer 来源。正式结论 ACCEPT_PC01_THREE_REFERENCE_READONLY_COMPARISON_SOURCE_ONLY：review_pc01_three_compare_source_20261019T1945 的 MANIFEST 为128字节 / 56b6158791820af77740b6691d7e019738be2e0aa682e976339b2c00cdb37e1d，SUMMARY 为2803字节 / bb77658273a04d0ccd1b7794711e99e29f6eb39995045ee2f6ff841101a473ab。作者48例×4模式与独审48+48纯合成冷测通过；独审另核128组Fraction数学诊断与266项FP32拓宽边界。

本内容只持久化已审SOURCE。真实PC01 capture比较尚未执行，native退出/cleanup、同RAM及来源关联仍由caller提供。后续实际长入口在独立重链180秒之后使用10620秒窗口，总预算上界10800秒；本比较的≤60秒完全包含在caller原shared_stop内，不新增窗口。原生产源码、测试与COLD结果逐字不变。
