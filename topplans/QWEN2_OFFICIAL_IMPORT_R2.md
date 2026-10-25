# Qwen2 官方 normal-import r2 独立阶段结果

本次小包只交付 candidates/qwen2_official_layer_import，不等待 full-reference 准备，也不携带其代码或任何新增数值结果。

已完成：一次受限官方正常导入及独立执行复核 PASS；3 个版本、4 个类自身源码/方法 code、9 项对象关系；精准一次 loopback probe 原 bool True 与相同 socket 闭合。47 个动态诊断项细分为 45 个 no-file 模块字典和 2 个非模块元数据项，不证明全部 live-code 或全部 __globals__。

仍未完成：实际官方 Layer 创建、forward、新数值 oracle、DUT/matrix 比较、性能/QoR。不得将 import-only PASS 写成上述任务 PASS。

旧 cold01 仍 FAIL，未回写；新 r2 是独立运行。原 caller/address 未留证，对旧失败的归因不是直接动态证明。

交付范围：本批按独立小提交交付已审源码与脱敏证据；提交不重跑真实 import，也不启动 forward 或新增数值验收。真实完整 runtime 与原绝对路径 manifests 留在本地包外，fresh checkout 仅能读证据和运行纯 mock。

## 发布基线与历史执行来源

本候选 overlay 拟叠加于已发布 capture 片提交 6f0867b4635072b0990f230975eaac67e7def0df。该值是本次发布父基线，不是历史 cold import 的执行来源。历史运行的当时上下文、源码 pins、时间戳和 receipt 均保持原样；不得据新父提交改写它们。包内四 source 与 test 保持原 hash，未改 capture 源码。
