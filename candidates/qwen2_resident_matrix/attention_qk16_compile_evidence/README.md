# QK16真实owner：编译证据小增量

已完成实际class-only编译：83源、474class，29.234551秒，编译器/外层退出均0、cleanup完成、日志为空。独立审查结果由本目录外的交付记录确认，避免为了审查状态修改执行或证据身份。

复用 attention_qk_owner_compile_evidence 的完整83源计划、87JAR锁、Java/HardFloat出处、474class基图和监督器源码。本增量只保存2个变化的owner源码哈希、3个变化的class哈希、计划/收据的小字段差异。reproduce.reconstructed() 必须重建真实summary/PLAN/launcher的逐字SHA；没有发布class/JAR/HardFloat archive或其它二进制载荷。

reproduce.compose使用原始完整项目和固定HardFloat源码重建83个编译输入。reproduce.command核验相同Java、87JAR及83源，返回相同class-only命令而不执行。历史监督器仅route路径与PLAN哈希变化；既有信号安全子进程所有权、环境白名单、排空和前后身份检查未变化。必须外层TERM90/KILL+10，总100秒；Xmx1GiB是heap上限，ActiveProcessorCount1是调度提示。

资格只有Scala class类型/接口编译。没有调用Emitter/ChiselStage、没有顶层构造/参数展开/CHIRRTL/SV/RTL或数值工作；没有性能或80%/90%利用率结论。默认关闭真实QK16路由仍需后续展开、同刺激数值/RTL和完整owner集成验证。

冷验证：仓库根执行
PACKED_QK16_COMPILE_ORIGINALS=/path/to/originals python -m unittest candidates.qwen2_resident_matrix.attention_qk16_compile_evidence.test_evidence -v
再以python -O运行同一模块。无原件时两项明确skip，不宣称外部原件验证。
