# P0 新边界输入传输恢复 — TEMP / INCOMPLETE

已实际重建原 21-command / 215-descriptor ABI 的 P0 输入端，七个 Dense 权重保留原生 BF16，激活/输出地址与 FP32 存储不变。仅输入、官方权重与 input-only RoPE；未注入任何参考输出或中间值。

Python 全部 14 个 RO 流完整哈希及 161 项边界/越界/RO 写拒绝/RW 未初始化检查通过。实际发布 C++ Config + affine loader 的 110 组 / 6,126 字节首尾、非对齐及 Dense 行边界检查通过；期望字节来自原始官方权重坐标映射，而非转置文件自比较。`HOST_DRIVER_CONFIG_ONLY` 不实例化 DUT，不能称 Chisel/RTL 数值通过。

源程序 `rebuild.py` 生成 NEW 元数据与本地实际权重转置；`emit_tsv.py` 生成固定 ABI runtime/views。源文件可发布；输出 payload、PRIVATE_PROBES.tsv、local_inputs.json、绝对路径 TSV 不可直接发布。未来公开需路径可移植化并排除数据。

新 hidden 与 RoPE identity 见 SUMMARY.json 和实际 RESULT；不是历史 embedding/prefix 输入继承。原 manifest 在修改输入身份前必须匹配 c5fcd45a…，每个源 receipt 必须等于固定官方计划。全部五块完整 Chisel/RTL 仍未通过。

## 可移植复现
`rebuild.py --repo REPO --payload VERIFIED_LOCAL_DATA --reference FRESH_P0_REFERENCE --rope OFFICIAL_INPUT_ONLY_CAPACITY_ROPE --rope-sha256 4060acc13a636cbd303e96552df99033cd348f238025f11bae1bc0fcab32c815 --output NEW_LOCAL_DIR`。默认使用仓库 `candidates/five_profile_input_recovery_20261028` 的固定元数据验证；可用 `--pin-package` 指定同一份已验脚本目录。需本地 NumPy，不下载/安装依赖。`emit_tsv.py --payload VERIFIED_LOCAL_DATA --provider NEW_LOCAL_DIR --output NEW_TSV_DIR`。实际 TSV 含本地绝对路径，仅供本地运行，不能直接提交。

本 portable 版仅将固定元数据目录解析改为显式 repo-relative/CLI 参数；实际运行证据对应原始脚本哈希（SUMMARY）。portable 参数适配未冒充重跑。REPO_DEPENDENCIES 给出准确依赖文件哈希；source_manifest/source_spec/PROGRAM_MANIFEST/RESULT 仅文本 pins、几何和摘要，无数据。
