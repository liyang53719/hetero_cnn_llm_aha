# 2026-11-15 01:33 hetero进展（INCOMPLETE）
- main基线789bfad，CI43659624823成功，仅载荷门禁；本地源干净，约9GiB可用内存/53GiB磁盘，临时清单已核清理0。
- 上轮三段终态均exit0，cycle39067/3行18432B零差异已核，不重复前缀。本轮沿该最近已验包执行48261、93203、67508三段及各自fresh恢复，全部exit0，实际152.52秒；最新cycle63597，480ACK/30720B=首RMS5/128行参考零差异。
- 本轮三组freshprocess120周期轨迹与完整终态包一致。最新入口0133/host/LATEST_VERIFIED.json；包SHA e462134a8bcd5a92d14fba08c78dba5bea6165db4cec9f600379d2c6afc7e3df。当前无任务在途，只partial ACK数值与恢复，不是完整RMS/owner completion。
- 并行真实profile：L3原70959与L0原48162 exit0，各500周期约1.43秒，原profile2/1合法launch，各44个R握手（其中1个input64B）逐字节对原真实桥一致，issuedJobs1，写ACK0。两者与Qwen2完全相同Host/shared17硬件hash，未重elaboration。只首RMS读取前缀，不是完整数值；历史L0 strict FAIL保持。
- 实际性能诊断：离线63868发现每cycle全ACK字节扫描随6144→24576B由0.425→1.972ms，快照复制约0.1ms基本固定；journal存取与120周期全ledger轨迹也增加墙钟，不是硬件MAC瓶颈结论。
- 新独立增量比较候选：只重算成功ACK变更字节，覆盖会修正旧mismatch，保全部journal/checksum、恢复重建及每段fullscan核对。保存96/192/288/384ACK逐笔对照、256随机真实Capture覆盖/partialstrobe和python-O错误负例通过，nochange约1.1us；未修改本轮冻结runner、未在真实Host采用，下一轮须显式新identity同刺激资格。
- 五块128完整原Chisel0/5，固定4096。三块真实前缀已推进，35B两层完整权重与准入/路由资格缺失，MoE同分未决不改参考。完整RTL与完整block有效MAC利用率未测。
- 下一：从63597最新已验入口继续，不退旧包；先显式采用并验证增量候选的同刺激/完整状态等价，再持续推进首RMS。唯一证据/源码留本地，清理0。
