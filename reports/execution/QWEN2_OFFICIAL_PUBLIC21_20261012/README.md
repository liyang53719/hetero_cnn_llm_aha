# Qwen2-1.5B L0：真实 cold M128 公开链，官方门仍失败

`f1d1324efd8d2ac3594acfac1732b3b719030da9` 的公开21命令物理事务软件模型于2026-10-12 12:36:14 UTC完成。17个owner任务、21次公开完成和一次whole terminal全部接受；19份实际输出、10组内部观测已保存。15个主阶段及6个观测节点对冻结独立算术逐bit相同。**这不是官方数值整块通过，也没有执行Chisel/RTL。**

- `M128_RESULT.json` 是原始终态摘要的元数据子集，记录源、输入/输出hash、完成计数与完整原门结果；不包含激活、权重、NPZ或编码载荷。原摘要SHA为 `25b947ff774412685d9691de0a06f1a1cf489388557db357013bf7911c11681a`。
- `INDEPENDENT_AUDIT.json` 记录另一检查器的935项读回核验：86源、19输出、10组观测、14个原输入、114参考工件、最终ACK与17个owner计数。其PASS只指证据一致性，native FAIL明确保留。
- `PROJECTION_ATTRIBUTION.json` 记录实际QR全部40个与官方不同元素的独立精确有理数诊断。实际顺序FP32 FMA及bias/BF16输出全部复现；精确点积再舍入也只匹配官方27/40，不能据此承诺增精度会解决官方后端差异。
- `CONDITIONAL_QK.json` 记录同完整形状、从冻结源码重建stride、相同固定CPU后台的两次孤立QK调用。官方Q/K重放全部196608 scores逐bit一致；用实际Q/K时，99072个已执行causal scores与真实owner全部逐bit一致。原forward未保存stride，因此不伪称stride有旧实测回执。诊断输出的future值从不填入实际presence。

官方整链比较仍有11个causal score/logit差异，全部在head9/query102，max_abs=8，大于原算子0.03125。独立BF16比较还含gate=0.041015625、prob=0.031494140625超门。没有改阈值，也不以末输出合格抵消中间失败。实际n0、官方K逐bit相同；先修通用Q投影归约/BF16临界舍入的可实现问题，不改已在同操作数下核实一致的QK/RMS。

## 重现读回与归因

下面脚本只读取本次已经完成的实际捕获及固定参考；缺件/hash漂移直接拒绝。它们不执行整个模型、不生成RTL，也不下载权重。使用原Python3.12、NumPy2.3.5、Torch2.10.0+cpu、Transformers4.40.1环境；官方源与runtime identity还会在孤立QK入口严格校验。

```
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python reports/execution/QWEN2_OFFICIAL_PUBLIC21_20261012/reproduce_capture_audit.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python reports/execution/QWEN2_OFFICIAL_PUBLIC21_20261012/reproduce_projection_attribution.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python reports/execution/QWEN2_OFFICIAL_PUBLIC21_20261012/reproduce_conditional_qk.py
```

输入所在目录为 `work/qwen2_official_public21_20261012/actual_m128_02`、`snapshot_m128_02`，以及其快照指明的原始payload、M128算术和官方参考目录。脚本产生的小报告仍写work；这些文件不是Git的一部分。重算算术/官方参考不等于重建丢失的实际捕获，不允许用reference替代actual。首次1200秒预算失败原样保存；该次只到FFN54/56，不能借本次成功终态改写旧结果。

## 主机时间及硬件口径

本次主机总1369.129秒，whole terminal1367.008秒，Down实际156.737秒，峰值RSS463628KiB；17,010,491只是Python事务模型tick。有效MAC6,014,828,544，执行MAC6,801,063,936，writeBytes13,369,344由本次接受的17个owner汇总；三个workspace sweep另按其真实流量记录。没有whole-wall硬件cycle，不能从主机秒数或模型tick计算MAC利用率。

本轮f1d1324三个CI均成功并核验工件：model 445 tests，frontend811 tests/143 CHIRRTL，143 IR原始字节与8a3e2fc完全相同；payload guard成功。软件cold M128结果来自本地冻结实际链，不能说CI再次执行M128。carried、长序列、其他四个典型block的M128与最终硬件验收仍开放。
