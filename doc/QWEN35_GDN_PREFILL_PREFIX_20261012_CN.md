# 0.8B L0：真实输入到投影的 M128 模型子门

状态：RMS→QKV/Z/AB 的 typed owner 软件链已通过 M16、M128；完整 GDN block 仍 ongoing，公共 Command128 接线、真正 chunk、状态和 RTL 尚未完成。

Qwen2-1.5B L0 完整 cold M128 的公开21命令模型结果及原 frontend CI 已在 `a38d0bb` 收口。本轮接着推进0.8B L0，保留原20份未提交候选，不继承其旧 M1 PASS，也未修改默认 Chisel 路径。

## 本轮真正执行了什么

- 固定模型revision `2fc06364715b967f1860aea9cf38778875588b17`、Transformers源 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。
- 复核现存14项L0原始参数，新增获取embedding前256行的524,288B固定切片；保持token公式 `(73*i+19)%256`。
- 每个输入窗口真正执行RMS→QKV6144→Z2048→AB32。第二窗口输入取token序号128起；它尚未消费GDN history/state，不能叫carried block通过。
- 全程同一真实地址映射、同一原普通Dense owner、同一Matrix软件资源、同一共享Scalar服务。中间区初始为哨兵，只有实际data/ACK及owner终态被接受后才能读取。
- RMS与Dense均使用2B BF16外部张量；权重原N×K在参数入口转为K×N。AB为A16/B16的打包入口，官方对照仍分别运行两个N16 Linear，再对A/B分别执行原门。
- Dense保留原逐K FP32 FMA和最终BF16 RNE；没有套用Qwen2特有的1024+512归约策略。RMS使用明确的1024宽CPU归约候选、FP32的1+weight和最后一次BF16舍入。这仍是新模型候选，默认已提交GDN RMS仍为LegacyAscending。

## 数值结果与证据边界

[紧凑结果及来源](../reports/execution/QWEN35_GDN_PREFILL_PREFIX_20261012/RESULT.json) 保存两次实际终态、各源/输入/ELF/输出SHA、原阈值及每节点误差。

| 范围 | 实际终态 | CPU壁钟 | 最高RSS | 官方原门 |
|---|---:|---:|---:|---|
| 两个M16窗口，序号0–15和128–143 | 8个owner | 54.36秒 | 406,284KiB | 12项通过 |
| 两个M128窗口，序号0–127和128–255 | 8个owner | 76.46秒 | 428,956KiB | 12项通过 |

M128所有输出与独立固定算术逐bit一致，实际成功ACK合计4,734,976B。对官方源的原RMS类AST和原尺寸独立Linear操作，RMS/A/B均逐bit一致；cold QKV最大绝对误差0.03125，恰好等于既有门；其余QKV/Z最大0.015625。最大均值误差约1.97e-7。保留所有原始bit差，不把通过容差写成bitexact。

原阈值来自 `host_bf16_gdn_descriptor_contract.json`：每节点max≤0.03125、mean≤0.005。没有降低阈值或用末输出遮盖上游失败。这里只执行官方操作参考，尚未执行完整官方DecoderLayer或状态流程。

M16与M128具有各自源码快照；后者只额外加入输入序号范围的报告字段，算术/owner/ELF未变。实际小激活、输出及固定/官方对照保留在本地work，Git只收源码、哈希、紧凑摘要。原20份候选保持不变。

## 资源与后续接入

实际M128前缀观察到526,336个Matrix宽step、2,155,872,256次C++ FMA、6次Dense资源获取/释放、106个group和514个result；共享Scalar计数也完整保留。这是软件事件和源算术计数，不能作为硬件cycle或完整block MAC利用率。固定资源分母仍为4096MAC/cycle，未增加阵列。

下一项为实际投影写回→Conv4/SiLU/history，再接M128准备、真正chunk64×2和双state最终fence。官方冷128与有历史128都走chunk分支，不能复用128次M1作为chunk验收。chunk的Q/K/状态运算为FP32，现有BF16 Matrix入口不能靠降精度假接；需要明确共享运算、存储与控制映射。

后续仍需gated norm、O/residual、postNorm、FFN/down/residual、公开Command128程序以及Chisel/RTL验收。五block M128总目标、S04/Q35B/U00.2/U01保持开放。

Qwen2新增分块Add的bank/Vector开销已记录但完整周期预测尚待重算；旧48.19%/40.34%不能直接代表新归约实现。该事项与本轮数值推进并列，不启动新的性能微优化。

## 冷启动小门

新增CI只做合成软件测试和小C++参考库构建，显式传入本次构建的ELF与receipt；无权重下载、M128重跑、Chisel生成或RTL仿真。首次干净环境在本地暴露payload模块经`heteronpu.config`间接需要PyYAML，保留失败日志后加入固定6.0.3依赖；发布前以冷checkout、仅固定NumPy/PyYAML环境完成整套顺序验证。
