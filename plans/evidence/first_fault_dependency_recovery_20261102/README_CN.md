# 只读首故障构建：依赖证据格式拒绝

原唯一 run 41441028806 的有限 Actions 投影显示，20 个阶段直到 host_link 均 native 0、无监督错误、cleanup/EOF/gzip 完整。阶段 elapsed 之和是 3594.720530416 秒，不是整个 job 实际耗时；RSS 仅为采样值。这里保留的是远端日志中的有限投影，不冒充已下载并逐个复核的原 worker 收据。

host_link 后，原 GCC .d 解析器在“非空、原 token 全唯一、原 token ≤4096”合并条件拒绝。没有获得该次实际 .d，因此不能断言具体哪一子条件或哪个 header 导致此次拒绝。没有上传七件、没有新 ELF 验收、没有 DUT 执行或数值通过。

独立只读检查已有严格闭合的 tiny GCC 依赖文件，确实发现合法输出含完全相同路径的重复 prerequisite；对其中真实 ReadProbeChild.d 调用原解析器，也在同一 unique bounded dependencies 门拒绝。这是格式兼容性证据，不是本次云端 .d 的精确因果重建，更不是原 P0 resetRequired 的根因。

修复必须保留原 .d 全文及哈希，仅在显式新 readonly candidate 域处理有界的完全相同词重复；多规则、路径别名碰撞、缺失或漂移依赖仍拒绝，实际完整唯一依赖集合继续逐 pin 核验。旧产物及旧解析器不因此放宽。新修复的真实 GCC 小例、capture/pack/export 正反例与重新构建须另以实际闭合结果证明，本证据不预授这些阶段通过。

本目录不发布原始日志、依赖绝对路径、生成 SV、ELF、权重或参考数据。
