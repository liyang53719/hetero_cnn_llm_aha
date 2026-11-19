# Hetero M128 恢复检查点（2026-11-19）

状态：**INCOMPLETE，五个完整 block 0/5**。此前云端检查点丢失，旧数值不能迁移到新身份。本页只记录源码/输入复现线索及证据范围，不含权重、执行快照或生成 RTL。

## 固定约束

- 一个原始 Chisel Host 定义、接口和物理容量，4096 MAC。Qwen2-1.5B 典型块、Qwen3.5-0.8B L0/L3、Qwen3.5-35B-A3B L0/L3 只换运行配置与权重，使用真实 128-token chunk，不以 M1 循环代替。
- 保留 Qwen2 FP32 存储，普通 RMS 与 GatedNorm 按各自官方算子精度，不给普通 RMS 无依据地加中间 BF16 舍入。PyTorch MoE 路由基线及待确认同分规则不改，不注入官方专家 ID。
- 参考、原始模型与后续 RTL 回放分层。Matrix FMA 与 iDMA 必须走原硬件；验证回调如采用，仅报告断言，不参与计算。

## done（仅限下列证据）

- 新统一候选 Scala 编译退出 0；CIRCT 1.163.0 生成 CHIRRTL，SHA-256 `27327f10f15ce3effb85859c04ab5b074cdbe92d70163a71e9affb94cbb53d25`。同源 HW IR `38c94fc2ae91abdd82eb86c25991a31218889b062faef22bc745f4717d8867dd`，8 Matrix / 8 ICG / 1 iDMA，105 条时钟断言逐模块计数一致。这是 IR 证据，非运行或断言逐条件等价证明。
- iDMA 固定 upstream commit `2e0b0fe53b6f8823319e2428e2e9abc2db149b7d` 的导出已重建。927 个成员校验，真实 Verilator 预处理完成；历史文件集合 928/928 相同（含清单），926 个字节相同，另两个为环境相关证明元数据。不是完整 Host 链接。
- 35B 两块 cold M128 首 RMS 官方 CPU 参考重建：transformers pin `42ca9701`、权重 revision `62704185bd97ad488cfc404e7caea797396b74dc`，固定 Torch 2.10.0+cpu。首 RMS 参考各 262,144 个 BF16 元素，仅用于比较。Qwen2 与 0.8B 两块首 RMS/投影另有独立项目顺序参考。不得预载任何参考中间值。

## ongoing / todo

- **ongoing**：Arc 真实模型中的全部断言须保持时钟、使能、谓词和失败中止语义；原 iDMA / Matrix / ICG 编译并接入相同的 Host。普通 Arc 直接降低时钟断言的最小探针失败，禁止通过删除断言绕过。
- **todo**：五块均从 reset 开始，先验证首 RMS 写回、真正退休与首投影真实消费，再沿各自原控制链推进完整 block。35B 后续 MoE 未完成。
- **todo**：模型数值通过后，冻结同一份源码、参考、输入和配置，只生成一份最终 RTL，以同刺激回放五块。完整 block 有效 MAC 利用率尚未实测；按固定 4096 和整块周期计，至少 80%、争取 90% 以上。32-lane 逐元素每周期发射仍是候选，不当作已实现；第二档 1024/1224 待定，不阻塞 M128。
