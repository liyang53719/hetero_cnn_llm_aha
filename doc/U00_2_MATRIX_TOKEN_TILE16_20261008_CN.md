# U00.2：实际16-token Matrix tile门禁（执行前范围）

在已有默认关闭的Matrix→Norm→SharedL2→RoPE候选中增加显式tile16模式，
复用现有Matrix16×32/512 lane及真实1,572,864B SharedL2，不另建架构top。
现有tensor owner实际每次只使用一行，重复加载每token权重；本轮把最多16个
真实H1024输入打包进既有64KiB activation staging，让每个32列权重tile被活动行共享。
片上packed staging按tile-major固定16行排布，仍位于既有SharedL2。
后续逐head/row Norm256和partial64 RoPE只在明确写ACK后复用单头缓冲。

执行前冻结baseline/AVX2各4命令：cold token0..15 Q8/K2与carried112..127 Q8/K2，
共32选定token、320头/来源。每来源294,912个Matrix K步包、150,994,944个活动
FP32累加器观察值。实际RTL必须核对独立整数顺序FMA与独立C fmaf，原native
max_abs≤0.03125、mean_abs≤0.005不变；失败保留且不得用RTL匹配替代源精度。

补充tail、跨tile、位置、权重复用、capacity/alias、背压、同周期/延迟ACK、reset、
故障及恢复；源快照、逐文件哈希和独立trace/counter均需复核。未运行项不得标通过。
固定资源全block useful-wall分母不变；活跃行增加不是完整block90%或PPA结果。

16行门禁通过后才按8个tile推进M128全头实际回放。此轮不声称完整M128、
generic Command128、位置系数生成/cache、KV/Attention/FFN或三模型完整block完成。
U00.2 ongoing、U01 to do；默认路径保持原状。Git只含源码、pins、哈希和简短摘要；
checkpoint/NPZ/memh/二进制/完整trace均在临时或忽略区域重建，不进入Git。
