# 2026-11-15 02:33 hetero持续执行（INCOMPLETE）
- 现场：main基线c1bc238/CI43663895127成功，仅载荷门禁；本地源干净，约9GiB可用内存/49GiB磁盘，0133持续证据约3GiB。清单已核，清理0；旧未知任务未重启。
- 增量比较迁移已实际资格：从63597旧包预检恢复，相同120周期fullscan/增量轨迹和22终态文件一致，段末全扫描保持；继而6个有界段至130437、11行零差异。
- 后续轨迹优化同样先资格：120周期全ledger轨迹与可逆ACK-delta逐拍重建ledger SHA一致，终态22文件一致（18.99s与1.41s）。保真实每cycle数值检查、完整journal/checksum和段末全扫描；只减少重复序列化历史，不代表硬件MAC利用率提高。completion停止分支控制测试通过。
- 原4761持续批已exit0/BUDGET_SAFE_STOP：31段/1438.13秒，最新461769cycle、3744ACK/239616B=首RMS39/128行零差异；31组fresh120轨迹和完整终态22文件一致。包a1e0af074452a3d7ca50300a2b9c2b1807e789e55647f039802482df1de550fc，FINAL_ENTRY明确保存，首RMS未完成。
- L3同一机器完整写侧资格：原90809 exit0，30392首64B ACK后120周期到30512，13ACK/832B；fresh轨迹及22文件相同，部分参考0差异，未owner completion。最终包b2dd8db587f46bce050600836816aa1c4b03127e1e671e23805110069708473e。此前readonly/schema迁移都独立固定身份，不混Qwen2。
- 正在继续：新Qwen2原22738取得同profile独占锁，完整pins核验后从461769复用同qualified runner/机器直接续，最多25分钟；每1000周期保存，每段fullscan/fresh120，completion即保存停核，不重算前缀。
- 并行L3原31421从已验30512串行最多3段，每段有界+fresh120；初次路径import错误在native load前失败已保留，修路径后才执行，不重复硬件。后续L0独立状态准备，原strict FAIL仍保留。
- 五块128完整原Chisel0/5；固定4096、三实际profile同Host/shared17哈希。35B两层完整权重/原准入与MoE契约仍缺，不缩硬件、不伪装统一通过。完整RTL数值/全block MAC利用率未测。
- 只提交允许摘要和计划，生成数据/权重/执行源码不上传；正在运行/唯一证据均保留。
