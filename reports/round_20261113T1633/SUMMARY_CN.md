# 16:33 真实首RMS持续推进与参考顺序差异（INCOMPLETE）

现场保留，main基线f6c57162及CI43455120309 success已核，仅payload guard。工作树clean；临时清单已核，清理0，保留所有唯一证据与在途依赖。

从已验证新身份cycle439完整checkpoint恢复真实Qwen2首RMS，不重启旧84795、不重算前缀。原71040首段exit0，439→3439，3000周期31.918s。串行控制器53928沿完整20块状态续段；第5段到cycle15440，真实B ACK后scratch6144字节，即完整首行1536个FP32存储元素。我独立比对固定hash的norm0.f32参考，6144/6144字节相等。仅首行，不冒128行/完整RMS。正在安全段边界升级逐段数值硬门禁，确认旧控制器退出才续，后续新入口需依LATEST核验。

真实shared17写方向恢复：保持8Matrix共4096MAC＋8ICG＋DMA，AW反压、W反压、Bpending三切点fresh-process恢复后55/45/41拍完整pending/output一致。实际64B写回字节、strobe、账本恢复，恰一次提交、无重复W/重发descriptor。仅联合native恢复，不冒Host写回完整资格。

L3独立完整QK→scale→mask参考发现必须保留的差异：当前Commands的qkNormPolicy=1映射配对高位优先(1,0,3,2...)，旧参考升序0..255。相同Q/K输入，两序FP32累加27981处不同，最终masked BF16有2处不同，首[query39,head2,key5]旧0x40a6、当前源码候选0x40a7。两份参考保留，未改原基线或硬件；当前候选不构成用户批准顺序变更，旧attention资格不可迁移。

五块M128完整原Chisel数值仍0/5；35B真实权重缺失、原L0underflow FAIL保留。完整RTL及有效MAC利用率未测。源码/真实日志/数据仅本地，远端只允许摘要。下一步持续首RMS完整状态续跑、真实写回覆盖检查，并解决参考顺序契约差异。
