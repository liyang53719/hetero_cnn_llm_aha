# Block checklist（只读视图）

唯一状态源为 `block_checklist.yaml`；本表由 `scripts/block_checklist.py render` 生成。

| 编号 | 优先级 | 事项 | 状态 |
|---|---|---|---|
| C00 | P0 | 重建最新源码与证据基线 | ongoing |
| C00.1 | P0 | 核对当前可用归档和关键源字节 | done |
| C00.2 | P0 | 完整工作区工具与硬件资源基线 | to do |
| C01 | P0 | 冻结三模型真实forward和层索引合同 | ongoing |
| C01.1 | P0 | 现有模型合同入口fail-closed校验 | done |
| C01.2 | P0 | 固定官方revision、forward、权重index和层索引复核 | to do |
| C02 | P0 | 建立双参考和可执行精度合同 | ongoing |
| C02.1 | P0 | 精度比较器公式注册与缺失合同拒绝测试 | done |
| C02.2 | P0 | 官方双参考与每producer精度合同完整冻结 | to do |
| C03 | P0 | 解耦模型几何与矩阵tile | ongoing |
| C03.1 | P0 | 编译器派生几何和状态容量合同 | done |
| C03.2 | P0 | 实际Chisel shape/layout/frontend解耦及回归 | to do |
| C04 | P0 | 统一typed tensor与多输入policy ABI | ongoing |
| C04.1 | P0 | 现有Command128与descriptor整数边界及字节合同加固 | done |
| C04.2 | P0 | typed tensor与多输入policy完整Host到RTL接入 | to do |
| C05 | P0 | 将root微程序接到真实数据owner | to do |
| C06 | P0 | 超64命令与有限tensor存活集合 | ongoing |
| C06.1 | P0 | 长命令容量与生命周期控制专项测试设计 | done |
| C06.2 | P0 | 长命令实际frontend接入与全部门禁 | to do |
| C07 | P0 | 有界片上状态tile与事务提交 | ongoing |
| C07.1 | P0 | 多状态域事务提交与失败恢复控制合同测试 | ongoing |
| C07.2 | P0 | 实际state-memory owner与片上资源及状态续算集成 | to do |
| C08 | P0 | 建立完整block公共测试与回执校验器 | ongoing |
| C08.1 | P0 | 全量tensor/state回执schema与比较器框架 | done |
| C08.2 | P0 | 真实block公共runner和全部比较域集成 | to do |
| Q20 | P1 | 重跑当前Qwen2双层主链保护基线 | to do |
| Q21 | P1 | 官方Qwen2 block权重与输入导出 | ongoing |
| Q21.1 | P1 | 通用权重分块打包与BF16字节回读测试 | done |
| Q21.2 | P1 | 官方Qwen2权重与真实输入导出验收 | to do |
| Q22 | P1 | Qwen2官方语义与批准混合精度闭环 | to do |
| Q23 | P1 | Qwen2官方完整block长度扩展 | to do |
| S00 | P1 | 通用Norm与非线性数值owner | to do |
| S01 | P1 | 有前缀GQA与partial MRoPE执行路径 | to do |
| Q24 | P1 | Qwen2真实状态续算与官方双层 | to do |
| S02 | P1 | GDN因果深度卷积真实数据与history | to do |
| S03 | P1 | GDN单token矩阵状态递推 | to do |
| S04 | P1 | GDN prefill先正确递推再验chunk模式 | to do |
| S05 | P1 | MoE router与实际token路由 | to do |
| S06 | P1 | routed与shared expert完整执行及加权合并 | to do |
| Q35A | P1 | Qwen35完整Attention分支接入 | to do |
| Q35B | P1 | Qwen35完整GDN分支接入 | to do |
| Q35C | P1 | Qwen35官方Attention加MoE完整block | to do |
| Q35D | P1 | Qwen35官方GDN加MoE完整block | to do |
| Q35E | P1 | Qwen35真实3GDN加1Attention周期组 | to do |
| Q38A | P2 | 四分支gated residual真实读写 | to do |
| Q38B | P2 | Qwen38 GDN几何与gate模式复用 | to do |
| Q38C | P2 | QSA index/summary及真正Top512 | to do |
| Q38D | P2 | QSA稀疏KV gather和Attention数值 | to do |
| Q38E | P2 | PLE ngram与稀疏行表及dilated conv | to do |
| Q38M | P2 | Qwen38 512选10 MoE真实几何 | to do |
| Q38F | P2 | Qwen38官方hyper-GDN-MoE完整block | to do |
| Q38G | P2 | Qwen38官方hyper-QSA-MoE完整block | to do |
| Q38H | P2 | Qwen38官方PLE所在完整block | to do |
| Q38I | P2 | Qwen38含PLE与QSA四层周期组 | to do |
| P00 | P1 | 先建立可达性能上界和实际周期账本 | ongoing |
| P00.1 | P1 | 归档原始计数复算与带宽上界检查器 | done |
| P00.2 | P1 | 当前DUT事件计数与互斥周期桶闭合 | to do |
| P01 | P2 | SiLU重叠Host集成A/B | ongoing |
| P01.1 | P2 | 已归档SiLU组件修复与数值/异常门禁 | done |
| P01.2 | P2 | 完整Host与实际iDMA双层及官方A/B | to do |
| P02 | P2 | Dense权重跨token复用及64beat批处理 | to do |
| P03 | P2 | Attention与GDN调度性能优化 | to do |
| P04 | P2 | 当前完整top的SRAM和800MHz实现检查 | to do |
| R00 | P2 | 六类典型block集中发布 | to do |
| F00 | P3 | 典型block之后接完整模型与llama backend | to do |
| F01 | P3 | MTP状态分支与视觉多模态独立验收 | to do |

部分子项 done 的父项仍为 ongoing；官方权重、真实RTL/状态连续性按各自完整门禁验收。
队列默认跳过所有 done 和已有负责人正在执行的 ongoing 叶项，不自动重开历史任务。
