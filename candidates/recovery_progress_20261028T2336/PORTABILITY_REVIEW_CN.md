# 发布依赖复核及实际运行身份边界

本批是可审查的 source/pin/hash/摘要，不是带数据自包含一键完整数值包。外部权重、input/ref 二进制、精确运行库均须独立按 pin 重建，不会以摘要替代。

- `independent_reference_runtime_binding_20261028T2300`：只提交选定的参数化 launcher/sidecar 派生源码、sidecar、参考 hash 摘要。排除历史 RUN_P*.sh、interface_check*.py 及其工作区路径依赖。原 SOURCE_MANIFEST 不改；发布单独 PACKAGED_SOURCE_MANIFEST。实际 forward 版本由 P0/P1/P2 result/runner hash 绑定。
- v2/v3/P0 cache arm：runner 必须与 profiles.json、stimulus.py、tensor_acquisition_plan.json 同目录。运行库、receipt、config、payload 参数见 PORTABLE_DEPENDENCIES.md。源码 CHANGE 是创建时的历史状态，后续真实结果看独立 SOURCE_ONLY_REVIEW，不篡改旧状态记录。
- P0 provider：便携参数版与原已运行源码身份区分。五项声明的仓库依赖哈希已逐一对照 base `b793d61132a5a7ec79fe853142717af8937c9572`；另列出继承的完整 27 文件 input-pin package 哈希。未冒充便携适配版实际重跑。
- P1/P2 provider V1：保留已运行源码及原证据；rebuild.py 的固定恢复目录和 qualify.py 的 actual/probe 布局属于历史运行身份，不是独立通用入口。新复现使用 `portable_v2/` 的显式参数及 DEPENDENCIES.json。V2 六项仓库依赖与上述 base 一致，五项 guard 测试正常/-O 独立重跑通过；未重新执行 actual provider、未执行 DUT。
- router_tie_diagnostics_v2.py：原始 logits 与 FP32 softmax 边界同分分开判断，不改 PyTorch topk；三项 synthetic 测试仅诊断分类。历史测试从仓库 candidates/ 目录运行才可解析相对脚本路径，需独立 pinned Torch runtime；本批不声称在发布暂存环境重新执行此 Torch 测试。
- iDMA check_ranges.py：原整数穷举与命名引用扫描的历史脚本，需先重建原 hash 对应的 provider/Host 生成物目录；发布的是固定源哈希和范围结论，不提供生成 SV，也不声称脱离这些生成物能重跑扫描。

完整数值仍 Chisel 0/5、最终 RTL 0/5。没有硬件或算术改动，没有隐含 80%/90% 利用率达标。
