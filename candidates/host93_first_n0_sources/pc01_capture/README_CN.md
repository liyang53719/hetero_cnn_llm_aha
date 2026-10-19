# 单次连续 PC01 执行调用方 SOURCE

当前为 SOURCE 准备，长 RTL 未由本候选执行。固定入口仅调用已经实际独审接受的 PC01 ELF；不重新 compile/link、backend 构建或 RTL 生成。ELF 13,537,744 字节，SHA256 cb64b5cf1d5e9c226b9768fb3fdcbb3305bee894b6d904cb4cf29633d10fe5b1。既有重链两阶段收据与原数学模型三阶段收据独立固定、逐阶段自然退出0/cleanup校验；SOURCE_PINS 给出内容身份，私有绑定只留本地。

## 一次真正连续执行

一个新进程、一个 Host/context/Syms/RAM，从 fresh reset 实际重跑 PC0，保留该进程 RAM，经 ACK0、私有 PC1 permit、GEMM、ACK1，再完整导出 N0 与 qraw。不能恢复已退出 N0 进程，也不从离线 N0 装载 RAM。原固定驱动在 ACK1 终端后 eval 为0。原28生产/44来源、19普通archive依赖和47重链副本完整前后核；16固定 canonical 输入共94,920,448字节仅原bytes读验，无转换、bias或BF16修整。

## 资源与单一截止

外层首行采样本次 t0，早于命令、解释器、SOURCE及资格读取；后续入口沿同一 t0。此次总10620秒，先前独立重链上界180秒，合计授权10800秒。两次执行有各自t0，等待不算仿真耗时。初始30秒；单native phase10410秒（work10395、cleanup5、post10）；比较至多60秒；末尾120秒。完整10410窗口在所有前验前后各核一次，未余完整窗口首停INCOMPLETE。证据截止min(总stop,当前+120)。外层TERM10610+KILL5+shell5处于总10620内，这10秒属于尾储备。

原 supervisor 仅精确常量 SHARED_SECONDS=6600 投影为10620并逆向复原，未改清理/WNOWAIT/监视或阶段逻辑。固定单核、AS6GiB、MemAvailable≥8GiB、可用盘≥3GiB保留，立即native前再核；RSS采用原累计parent-children值，不冒充单phase峰值。8M主周期为cap，未知PC1吞吐下不保证完成。旧N0周期与墙钟只能预算参考。447232是固定状态序粗下界，不能当实际或ETA。

## 输出资格与三轨

只在原监督自然退出0、cleanup及固定argv/cwd/ELF前后身份闭合后读完整capture。固定比较源核freshPC0全196608 N0值SHA，ACK1/完整qraw退休、196608有限值、73728wide/589824slice、2048B/12288W、786432字节覆盖及完整窗口。B2048的descriptor→AXI映射由原 IdmaWeightBurst 和有限源审绑定；不把计数status布尔当native资格。ACK0内部writeback与ACK1 payload由原固定driver成功路径强门，消费者没有新增内部观察探针。

PC1有效MAC301989888；分母4096×(ACK1边沿−PC1接受边沿+1)，覆盖完整PC1主周期窗口。whole-block利用率不在此授值。typed参考196608项逐bit、hash全部一致才能判该轨通过；若不一致，先保留全量FP32/FP64数学诊断，再固定失败码首停。两个数学轨保持独立误差/ULP诊断，不新增application容差；official_raw_numeric_pass与application_accuracy_pass仍null，full_block_pass=false。

原异常优先于落证/恢复异常。私有EXECUTION_RESULT保存原native diagnostics；未知异常固定码null，不投影任意异常文本。冷测只mock，真实长执行必须在此SOURCE、精确私有调用和有界合同独审后由获授权调用方发起一次。
