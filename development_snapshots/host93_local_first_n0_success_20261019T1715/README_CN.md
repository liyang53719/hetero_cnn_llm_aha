# 本地首个 M128 N0：完整读回与原容差数值通过

原单次本地执行报告 PASS_FIRST_N0_LIMITED_TOLERANCE_ONLY，outer 退出 0；独立 actual 审查已接受首个 M128 N0 限定容差通过及本次 exact 捕获事实。源提交 7cc11def3e4e1bb2d6bf6ff15bc1506c607cad6c。summary.json 是七件冻结证据的安全字段投影，不是私有 RESULT 原文。

## 本次实际结果

- 16 个 native 阶段全部自然退出 0、未超时、cleanup_confirmed=true，原 waitid code/status 全部为 1/0。包含 fresh backend 构建与 tiny、iDMA/retained13 配置、Host C++ 生成/编译、首 N0 模拟及原比较器；没有将此前缓存收据算作新的 native 采集资格。
- 单 RTL、单 RAM 桥完成 1 次 launch/任务，12,288 次成功 B 退休，ACK0=1；在 ACK0 后停止进一步 eval，完整写回并读出 786,432 B、196,608 个 FP32 值，形状 [1,128,1536]。实际 2,956,951 cycles，原 8,000,000 探索帽未耗尽；2,428,928 仍只是源级归约下界，不是总周期上界或完整运行成本。
- 原容差 max_abs≤0.03125、mean_abs≤0.005 未改；全值有限，本次 max_abs=0、mean_abs=0、different_elements=0。容差数值 PASS 与本次 bit_exact=true、hash_exact=true 分列；actual 与原参考 FP32 SHA256 均为 3c25077e0b7aa5819df6fb93cbaba6a0d5379ac06b9df468beecd0f259b5cc3f。只对本次完整首 N0 捕获成立。
- 生成日志完整扫描 2,285 B，warning/error/unparsed 均 0，partial=false。cluster wrapper 为 18 入/2 出，匹配单 library target；root header 5,296,945 B，首次 SIZE_LIMIT 后有界重读成功，但语法仍 UNRECOGNIZED_SYNTAX，256 handle 身份仍 UNKNOWN，依赖结论仍 NOT_ESTABLISHED。数值成功不补填该未知结构观察。
- 外层 3,697.674051 秒，协调器 3,697.613124 秒；backend make 486.030968 秒、Host 生成 203.968410 秒、Host 编译 66.464959 秒、N0 模拟 2,904.533148 秒、比较 8.378398 秒。嵌套计时分别列示，不相加冒作总耗时；累计 child maxrss 不当作每阶段独立峰值。

## 复用与资格边界

16 输入共 94,920,448 B 与固定 473 源码共 11,747,893 B 是本次父数据复制/重验，未重新下载或转换，旧清理收据不充作新 native 资格。SV 为固定同字节复用，未重新执行 Scala/FIR 发射。原 historical 参考的既有双 SHA 收据与文件身份经前置核对，本次没有重新运行参考 forward；原参考能力观察槽仍 NOT_COLLECTED/UNKNOWN，不把既有参考事实改写成本次重新采集的能力资格。比较器使用已审 historical 绑定及原数值算法。

FIFO 的 4 cases/5,180 比较来自 39232100796 的精确同源历史前提，本地 FIFO 明确 NOT_RUN；既有五工具资格同样继承前提。本次 full_block_pass=false、baseline_adopted=false；仅首个 M128 N0，后续数值阶段、完整 block 与三模型五 block 尚未通过。

证据：MANIFEST.json 1005 B / SHA256 02be7877f6a10dbb08ebd5e6e2d565366278db9642aacb3f5d24240595e18ad8；RESULT.json 37258 B / SHA256 3b41e48ddcc58f109c0bf8b58cdd9777a0573c47617d462e0e49d4957e56c13d。独审 review_local_objcache_resume_actual_20261019T1818：MANIFEST.json 613 B / SHA256 fa5e5b952a92fb1fe6604237c04221279c26a76990e8c5bc0153b59e434a8b22；SUMMARY.json 20581 B / SHA256 af34169bb8291ee49510be82ea6332d9aed928a707f010b0fc990a2ba1ee0fe7，结论 ACCEPT_ACTUAL_FIRST_N0_M128_LIMITED_TOLERANCE_PASS_WITH_EXACT_CAPTURE。

独审只读核对了完整 196,608 个 FP32 字（786,432 B）与原参考逐字节一致，零差异、零非有限值、零尾随字节；所有字低 16 位为零，上 16 位按小端反投影的 393,216 B BF16 布局 SHA256 为 bd41672e6ea7d12746b41e56d21b3309369ecfd87cc26319ae6adbf0874e5cf2，与原 native BF16 参考身份相同。此为保存现物的只读字节/布局核验，没有重新计算参考或重跑模型，也不声称另存了本轮 native BF16 文件。

2,956,951 cycles 的单位是 scheduler 每次主高沿的 observe_counts：包括工作 edge0 空闲、edge1 launch 直到 ACK0 终末高沿，排除 4 个复位断言和 4 个复位释放高沿；128 项 core-state histogram 之和恰为该数。各 AXI stall 是同一已观察高沿的 pre-edge valid&&!ready 分通道计数，通道可重叠，不能相加称额外周期。尚无已建立的 useful-MAC 分子，不报利用率或完整 block 周期。单 RAM 完整写回、resident 检查先于 B 提交、首 ACK0 后立即停机，由绑定的冻结源门和成功执行记录支持，未进行独立模型回放。此前 session8356 的原失败保留。

本批只有安全 summary、本文及中文计划三路径；数组、机器路径、逐文件私有库存、raw logs、ELF/生成源码/runtime 全部保留本地。没有 workflow 或执行源码变动，不触发新的 Host/native 作业。
