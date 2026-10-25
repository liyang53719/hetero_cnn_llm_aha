# Qwen2 完整 block ordered 接缝准备计划

基础：已发布 `8b3c5a2ea6e9615f5a2a8c37ad5392c6d4a7941a` 的真实 Attention M1/M2 Observation 组件证据。本文只新增完整入口准备，不将组件 PASS 外推。

**终态：准备源码与193项四模式控制回归通过；正常fullgraph import因未准入PyYAML而FAIL，九个真实方法绑定尚未到达。完整数值仍TEMP。**

本片仅在独立 source composer 后像中修改原 suffix pc12 dispatch，默认关闭；复用原 DenseReduction prefix、Norm/RoPE、O/FFN、物理内存和 Matrix service。QK profile2、legacy PV profile0；旧 rawKV/PV2 入口及 pins 均不改。

代码与复现见 [候选说明](../candidates/qwen2_ordered_fullgraph_entry/README.md)。冷控制测试覆盖 source composition、实际编排调用关系、service 继承方法绑定、原 terminal/ACK 清债与 registry 拒绝；fixture 不是完整 block 数值执行。

完整 M16 准入仍 NOT_READY：现存 provider/raw 文件已只读 hash 核验，M16 x 与旧输入一致，但原 M16 独立参考输出闭包尚未恢复；M128 reference pins 仅 source-only 元数据，不是 oracle。32 个实际 inventory 条目不等于官方 29 语义节点完整覆盖，未物化与缺捕获逐项列明，不用参考补值。

下一步必须先闭合 source/runtime/provider/reference/observer 的精确身份、新的进程预算与独立准入，才考虑一次 M16 实际运行。M128、native 重编译、RTL/EDA 均不在本批范围。原失败保留，正常依赖初始化不称作“没有任何 native 库加载”。

固定 4096 MAC 分母不变；legacy PV 路径完整 block 上界仍为 63.57%，本片没有 80%/90% 利用率或硬件周期/频率证明。
