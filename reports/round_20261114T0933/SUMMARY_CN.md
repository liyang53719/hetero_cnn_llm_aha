# 2026-11-14 09:33 重连恢复（INCOMPLETE，历史证据不可继承）
云环境离线后重连ready，但文件视图回退至Nov13早期；Nov14运行目录、最新Host/native库、完整checkpoint及锁/终态丢失。原37765 poll Unknown，旧只读检查stale generation；不能据本地无进程宣称旧任务已停止。没有重启或重复完整profile。
最后历史观察为当前候选首RMS50/128行、307200B零差异、cycle584351及fresh恢复差分通过，包hash aec6d9e4566c0db8f75be058e2f46f90b796d7573334ae95c18ede67a16922db；该包当前不可访问，不算现可恢复PASS，第107批未知。
## 已实际独立恢复并重测
- 保留155份原源码逐项重hash全部匹配；仅源码完整性，不是编译数值PASS。
- 原Qwen2真实输入桥5测试重新运行通过，拒未初始化中间值，不大计算参考。
- L3 loader及命令审计重新编码：13只读段36983808字节全逻辑布局一致，680正读/39非法读拒绝，22命令65tensor根和损坏root负例通过。trig重生成hash匹配旧pin，不称当前Torch执行。当前实际Host GQA顺序仍需新库身份核验。
- MoE最小lease候选重新构造两赋值，原860类hash核验；session55188 exit0，Scala typecheck4.937秒，4静态测试通过。新源码SHA a245fe7c690572db1c402fe6928d40c84e0b6469c62e6e74912efa84408829bf，与丢失候选不混同，未继承其RTL/Host结构PASS。
- Host四文件新恢复候选正在基于保留原源/类进行反变换审计和有界typecheck，不声称匹配失去的源码hash；未发射完整Host或运行。
## 边界
五块完整128原Chisel仍0/5，完整RTL无PASS，全block有效MAC利用率未测。固定4096、原精度/舍入、L0 strict FAIL和35B权重/数值契约阻塞保持，未打开profile3/4。旧任务未知不启动冲突完整工作。
远端基线a10829d95d173b93f54c2d2f6c516a712c83a328，CI43576506803 success仅payload守卫。当前可见目录和恢复产物清单已保存，清理0。当前RAM可用约9.2GB/磁盘57GB；ps只说明当前隔离视图，不证明旧executor终止。仅允许摘要/计划发布，源码与数据仍本地。
