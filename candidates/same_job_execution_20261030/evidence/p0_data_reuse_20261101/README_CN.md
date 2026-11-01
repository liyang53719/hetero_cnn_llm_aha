# 新 P0 输入复用：真实纯链与有限反例

`run_pure_chain.py` 已在原严格监督器中实际运行：native 0 / errors[] / cleanup 完整 / EOF / gzip 完整，4.202 秒，采样 RSS 116,805,632 B。实际使用当时 830 源目录 SHA `9be76d7c39da2abbb7f92b2724dfa6cf970e5cfc5533f54db35eb9b3d50f732e`；不把随后测试/证据等闭包调整称为同次实际运行。

真实 `provider.initialize → core.materialize → dual-root emit → hydrate → corrector → assemble → load_binding → full-span inspector` 通过。新 material 内实际生成 reference/program/runtime/views/元数据，原 94,916,608 B 输入仅只读复用，无 input_only 复制/alias，无共同祖先 containment 绕过，无手工修改 program 路径。原独立 FP32/转置全内容检查与 emit raw probes 都实际执行。y/cache_k/cache_v 完整最终跨度分别 786432/131072/131072 B。

这不是运行许可或数值 PASS：纯 context 不含活 owner；历史 STARTUP_ABI 只作为原字节复制，并未本轮执行 ABI。未执行 DUT / ELF 或 reference forward，也没有网络或子进程。coverage_acceptance、numerical_pass 均 false。

`negative_checks.py` 真实调用同 core，normal/-O 各三例：错误 binding SHA 在创建目标前拒绝；小 fresh provider 副本中任意 input_root 或错误 commands hash 均拒绝。不改正例现场/旧数据，audit 禁止打开大于 2 MiB 文件及进程/网络；没有重新哈希大输入。

## 复现

先按最终复现源码目录准备独立 pinned reuse doc（context.repo 必须精确该目录）、固定 artifact/review、历史 ABI 和实际 inspector；用 runner `--help` 查看各必填 PATH/SHA。用已有提供 numpy 的 qwen2 wrapper 经原 provider 严格监督预算执行；不得去掉 sourcecatalog/contract/raw probes/containment 门。首次真实运行时 source830 与本摘要源 pins 见 SAFE_EVIDENCE。新输出目录必须不存在，不能指向旧 provider/material。

负例 CLI：`python [-O] negative_checks.py --core <p0_provider_data_reuse.py> --core-sha256 <SHA> --binding <same binding> --binding-sha256 <SHA> --provider <positive fresh p0_provider> --output <new negative root>`。仅复制小 program 与元数据，不复制 input 文件。

本目录仅小源码/有限摘要；不含原权重、参考张量、七件 payload、runtime 库、监督 raw log 或生成 IR/RTL。
