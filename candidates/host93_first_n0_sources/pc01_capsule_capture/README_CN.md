# 单次 fresh PC01 诊断重放调用方 SOURCE

当前为 SOURCE 准备，长 RTL 未由本候选执行。固定入口仅调用已经实际独审接受的 PC01 ELF；不重新 compile/link、backend 构建或 RTL 生成。ELF 13,547,616 字节，SHA256 73a13d020b99fa78087c639629dcbb8984d3dfbf028baf3adb69b60b51774617。既有重链两阶段收据与原数学模型三阶段收据独立固定、逐阶段自然退出0/cleanup校验；SOURCE_PINS 给出内容身份，私有绑定只留本地。

## 一次真正连续执行

一个新进程、一个 Host/context/Syms/RAM，从 fresh reset 实际重跑 PC0，保留该进程 RAM，经 ACK0、私有 PC1 permit、GEMM、ACK1，再完整导出 N0 与 qraw。不能恢复已退出 N0 进程，也不从离线 N0 装载 RAM。原固定驱动在 ACK1 终端后 eval 为0。29生产/44来源、19普通archive依赖和48重链副本完整前后核；16固定 canonical 输入共94,920,448字节仅原bytes读验，无转换、bias或BF16修整。

## 资源与单一截止

外层首行采样本次 t0，早于命令、解释器、SOURCE及资格读取；后续入口沿同一 t0。此次总10620秒，先前独立重链上界180秒，合计授权10800秒。两次执行有各自t0，等待不算仿真耗时。初始30秒；单native phase10410秒（work10395、cleanup5、post10）；比较至多60秒；末尾120秒。完整10410窗口在所有前验前后各核一次，未余完整窗口首停INCOMPLETE。证据截止min(总stop,当前+120)。外层TERM10610+KILL5+shell5处于总10620内，这10秒属于尾储备。

原 supervisor 仅精确常量 SHARED_SECONDS=6600 投影为10620并逆向复原，未改清理/WNOWAIT/监视或阶段逻辑。固定单核、AS6GiB、MemAvailable≥8GiB、可用盘≥3GiB保留，立即native前再核；RSS采用原累计parent-children值，不冒充单phase峰值。8M主周期为cap，未知PC1吞吐下不保证完成。旧N0周期与墙钟只能预算参考。447232是固定状态序粗下界，不能当实际或ETA。

## 输出资格与三轨

只在原监督自然退出0、cleanup及固定argv/cwd/ELF前后身份闭合后读完整capture。固定比较源核freshPC0全196608 N0值SHA，ACK1/完整qraw退休、196608有限值、73728wide/589824slice、2048B/12288W、786432字节覆盖及完整窗口。B2048的descriptor→AXI映射由原 IdmaWeightBurst 和有限源审绑定；不把计数status布尔当native资格。ACK0内部writeback与ACK1 payload由原固定driver成功路径强门，消费者没有新增内部观察探针。

PC1有效MAC301989888；分母4096×(ACK1边沿−PC1接受边沿+1)，覆盖完整PC1主周期窗口。whole-block利用率不在此授值。typed参考196608项逐bit、hash全部一致才能判该轨通过；若不一致，先保留全量FP32/FP64数学诊断，再固定失败码首停。两个数学轨保持独立误差/ULP诊断，不新增application容差；official_raw_numeric_pass与application_accuracy_pass仍null，full_block_pass=false。

原异常优先于落证/恢复异常。私有EXECUTION_RESULT保存原native diagnostics；未知异常固定码null，不投影任意异常文本。冷测只mock，真实长执行必须在此SOURCE、精确私有调用和有界合同独审后由获授权调用方发起一次。

## 胶囊后继的唯一窄差分

新ELF来自已完成独审的capsule driver-only重链，receipt 16702 B / 643258fd6a0255aa068446acdd15dbc2d63f20e3927cc458f264a4cf7c0af513；正式审 ACCEPT_ACTUAL_PC01_CAPSULE_DRIVER_COMPILE_LINK_ONLY，SUMMARY 9281 B / 52f77ba0baff3d7c00ee614334733c216126c6513c81d0fb3f818e6be3a73f3b。29源由24原件、4替换及1固定诊断header组成；19普通archive物件、39系统身份、44上游、16输入和三个参考全部继承。capture本身没有28或47计数硬编码，直接复用已审新relink helper的29+19闭合。其余native监督、比较、资源与预算不变。

原失败进程和原证据只读保留，不能恢复。新fresh工作树/证据树只由私有绑定指定；本SOURCE作者没有执行重放。本次仍实际重跑PC0，不拿旧N0替代。此前PC1_022的具体谓词和调用点仍UNKNOWN；补诊断源码不等于修复RTL或数值通过。

落证仅新增对固定 phases/capture/native.log 的完整文件身份观察。直接调用原已pin support.identity(path, 1MiB)，继承nofollow、同fd完整流式hash、长度及前后stat一致性检查。该文件始终留在原phase目录，既有监督输出的首行与胶囊第二行全部保留，不截尾、不复制、不改写、不新增reader/parser，也不解释胶囊字段。132-byte原错误行与最多8192-byte补证行均在原1MiB cap内；这说明容量足够，不预言下一次一定产生这些行。

观察位于原120秒尾储备内，截止仍min(总stop,落证起点+120)。日志缺失/漂移/读取失败只存固定secondary类型；已有native首异常保持优先，仍在剩余时间内尝试原EXECUTION_RESULT保存。观察之后再次核同一report_stop并安装其剩余timer，不能因捕获alarm重新开120秒；储备已耗尽时停止保存尝试。没有原失败时，观察失败使调用方失败，不伪称日志完整。

执行后的actual独审必须盘点完整phase/work tree、逐核原native.log全文件身份，并对实际出现的两行及capsule字段另作审查。size/SHA本身不授胶囊语义、数值或根因资格。原firstfailure、受监督自然退出/cleanup、三轨比较60秒与末120秒、10610+5+5外层均保留。

若阶段和比较先完成，而尾部日志身份观察或保存/恢复随后失败，RESULT可能仍保留先前完成status及比较字段，outer仍失败。实际资格必须同时核outer自然退出0、原native/cleanup、完整日志身份和前后输入/ELF闭合；不能单独拿RESULT.status或已有数学观察授actual PASS。
