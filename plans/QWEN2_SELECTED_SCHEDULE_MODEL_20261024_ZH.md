# Qwen2 调度对应模型：本轮计划与检查表

目标先Qwen2-1.5B典型完整block，再Qwen3.5-0.8B与35B-A3B各L0/L3。本轮只关闭Qwen2一个实际模型调度缺口，不扩大为架构重写。

- [x] 固定main 1ea9b511与现有QK16五文件recipe的选定Scala postimage，区分bare main和已组合目标。
- [x] 新增显式opt-in：单个Attention Job内部QK16 → 每head softmax → legacy PV；保留key顺序、BF16物化、FP32 fold和Scalar故障行为。
- [x] 同一Matrix资源独占acquire，真实原client按结果/done/回复drain后切换；测试提前切换、重复/遗漏完成、输出ACK和释放。
- [x] 默认packed六head及所有原源码/源码hash门不改；只在新partial overlay应用两项新patch。
- [x] 有限真实owner控制测试及纯Python Fraction/RNE M2数值回归，normal76项、-O76项PASS；M2不是M128 prefill，全部具体计数见候选validation报告。
- [x] 列出QK/PV实际issue几何、有用MAC与active capacity，保留4096安装资源，host ticks不冒充硬件cycles/utilization。
- [ ] 新profile2/native闭包、输入、原始M128参考和资源预算单独审查冻结，再复用现有full-block prefill入口。不得继承旧27项PASS、不得128次完整M1冒充prefill。
- [ ] 查明并闭合选定Dense-only cache与原raw-KV Public transport差别，验证整个模型↔选定Chisel路径，而不止调度。
- [ ] 完成新M128整block数值资格与真实全block硬件周期测量，再谈更长序列和90%目标。

结论：本轮小模型改动可单独审查；整体仍INCOMPLETE。原full M128 admission仍拒绝改变后的源码闭包，未启动RTL、native/fullmodel长任务，也未改历史验收门或编造mask/容差。
