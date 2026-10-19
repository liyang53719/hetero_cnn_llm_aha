# TEMP 纯源码准备计划：本地 N0 后续仍有资源与工具缺口

本批只保存固定来源、必要变更与资源缺口说明；没有新增执行代码、冷测结果、workflow、下载、安装、迁移、删除或 Host/native 作业。原 8 GiB MemAvailable 门不变，当前不启动 Host。

## 已有可复用材料
- 本地 historical 原参考资格已有实际独审通过：原自然 AVX512、原五库/运行时/4-1线程、原官方一次 forward、原双 SHA 完整。该结果仅 local_reference_qualified，baseline_adopted/DUT/fullblock 仍 false；不把它伪装成 CI ci31214 same-job 前门。
- 只读成本核对报告称：16 个规范输入均与原各自 SHA 相符，总94,920,448 B；同 SHA Host SV76,366,612 B（2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61）；iDMA原 source ZIP9,926,876 B（a8012f28942acd248dcc2942613a39669579d02d3f7bf687f98776b64e8f2dce）可免重复获取。安全 SOURCE_PINS 只列角色/公开源身份，不复制权重、张量或机器路径。
- iDMA ZIP仍须按现有 ready_o+valid_o 双拆块派生合同重新提取并核319成员；不能复用旧未双拆块结果。其控制/flush四态、原子gating和算术不改。

## 尚缺真实工具和模型
本次限定只读检索未得到可验证的当前 Verilator backend、完整473源码树或真实VHostBlockTop模型。当前可见模拟头是 cold fixture，不能替代实际生成头/链接证据。原固定PATH中的autoconf、autom4te、m4、flex、bison缺失；现有CI工具入口按/usr/bin:/bin找工具，不能未经新绑定就假装已装或默默换版本。

已有固定官方来源可供后续最窄恢复：Verilator revision4e194cc3ec8e27b18e17f80d7f99c15f984bbdae、473 Git blob表、11,747,893 B原核心、只一项m_seqnum初始化修复后11,747,906 B；五固定Debian包共2,466,616 B，67选定成员3,598,623 B（含FlexLexer.h）。来源URL、包/成员pin及原ar/xz安全解析已在既有代码中。五包metadata不等于当前工具已可运行：还需固定私有暂存目录/脚本数据relocation、解释器及ELF动态依赖的当前兼容检查、真实version+micro和头编译探针，然后重建同固定版本backend及tiny。不能从历史已丢失binary继承资格，也不采用便宜但不同版本替代。

## 最小必要源码后继（都待审，未实施）
1. 一个本地有限入口对既存16输入、参考、SV、iDMA ZIP做固定同buffer身份准入；收据明确既存资产重新验证，不能复用旧CI采集收据或跳过原same-job约束。
2. 私有固定依赖暂存与PATH绑定，仅复用已审五包/67成员与既有工具微例。完整473固定源核、唯一seqnum派生、全新backend构建和tiny；保原warning-fatal、单核、资源/共享截止和失败即停。
3. 复用当前cluster配置、256同参数共享库条件及真实新生成参数/wrapper/make/archive/ELF合同；真实顶层是VHostBlockTop。旧8 endpoint门和手写mock ABI均不能继承。当前root header256观察UNKNOWN保持，不能用期望值倒填。
4. 现比较器在n0_compare.py的RUNTIME_IDENTITY仍硬选ci31214。未来仅独立historical绑定adapter，原五函数、FP32→FP64/NumPy归约、196608全分母、finite门与max_abs≤0.03125/mean_abs≤0.005原阈值不改；exact_match继续单列。该adapter由独立片准备，本批不包含也不授其资格。
5. 本地续接需重新审核真实生成ABI/单RTL单RAM供数、B退休→ACK0→196608值读回和计数/安全错误。沿已批8M探索帽与有界剩余截止，帽或时间耗尽仍INCOMPLETE，不能记numericFAIL；本批不授长数值或Host启动。

## 当前资源阻点与成本口径
2026-10-19T13:36:49Z的限定只读观察：MemAvailable7,998,820 KiB，固定8 GiB门8,388,608 KiB，缺389,788 KiB（约380.65 MiB）。cgroup memory.max/current/high/events不可见，不能声称容器硬内存余量已证。该瞬时数值不是执行时保证，未来仍须当场过原门；Host生成和C++编译原8GiB+3GiB空闲磁盘门均保留。

runtime约794 MiB和wheel约206 MiB目前占tmpfs的观察仅支持一种迁移提案；迁移到磁盘、删除tmpfs文件或改变布局均等待用户明确答复，此批没有做。即使迁移，须固定资产重新hash和新位置绑定，不能预宣称会过门或已有授权。

历史另一已完成37阶段作业39232100796，仅作为有限成本参照：fresh_make451.755421秒、生成123.743956秒、编译56.433910秒，三项和631.933287秒；37阶段和858.346829秒、协调器870.427722秒。它不是当前环境ETA或新资源证明。其child_maxrss_kib_cumulative为RUSAGE_CHILDREN累计高水位，不能当每阶段当前实测峰值；单独leader采样也不覆盖后代。

成本只读独审：PENDING。当前仅文档/固定来源准备；没有新增测试运行。后续成熟SOURCE可小批审后持久化，长Host须先解决资源门及新增绑定审，不以此说明直接执行。
