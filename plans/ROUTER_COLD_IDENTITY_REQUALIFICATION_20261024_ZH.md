# Router cold 源身份与历史 replay 资格分离

日期：2026-10-24。局部基线：`e4580b5`。范围仅为 35B saved-postnorm
router logits 的源身份与拒绝门槛，不是新数值、完整 router/block 或 RTL 验收。

## done

- 已核对 [失败 CI job](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40078020201/job/120825503256)：实际 checkout 为 `df45d5a7a316f066adf427c17ae28d68ade5f32c`。普通模式 15 项中 14 PASS、1 FAIL，错误是 `chunk/vector.py` 源漂移。由于 `set -e`，优化模式、两次 cold CLI 及最终 `NOT_EXECUTED` 检查均未执行，不能合称已通过。
- GitHub 对该 SHA 的文件读取确认 Vector blob 为 `99b3e09b074df5e3ad11575444d332b9a27969f0`，与本地相同；当时 TypedMemory blob 为 `95d99c7415163b560f420bb081f14bd759ceb8ab`，还是旧实现。最新局部基线另有 `_resolve` 提升，因此旧 108 项 map 在本批编辑前有两处漂移，不是只补一个 hash 即可。
- `logits_identity.json` 原字节未改，SHA-256 仍为 `bd2be32639995ec7b4c3f1c8248f4eb667b7d6046e444a8d6fd819c40c0da7b2`。历史 fixtures、输出摘要、runtime 与 actual PASS 证据不重写、不继承。
- 新增独立 `cold_identity.json`：保留全部 108 个旧 source 路径，逐项校验当前精确字节。只显式列出审计后的四个替换项，即 Vector、TypedMemory、本批 gate 和测试；另外覆盖 R2 C++、payload source manifest、35B model profile，合计 111 个 source/config 路径。
- 冷报告明确为 `TEMP_REQUALIFICATION_REQUIRED`，仅 `cold_source_identity_status=PASS`；`actual_status=NOT_EXECUTED`、`actual_matrix_owner_executed=false`、`historical_actual_pass_inherited=false`。新 cold hashes 不构成 actual replay 准入。
- `--run-actual` 仍只走原 `source_identity()`，无 cold fallback；当前 source drift 在读取 fixtures、分配 owner/数据缓冲、加载原生库或创建输出目录之前拒绝。`source_identity`、`run_actual` 和 `replay` 的函数 AST 保持不变。
- PASS：CI 等价的普通与 `-O` 两轮各 21 项测试、两次 `-S` cold CLI、最终状态检查。新增测试逐一拒绝 111 个 source/config 中任一 hash 漂移，并覆盖旧 manifest 改动、删除更新项/可选依赖、改写资格标签、源符号链接逃逸、执行中 cold manifest 改动，以及 cold hashes 无法解锁 actual。
- PASS：本轮另跑 17 项 Vector backend admission 与 19 项 memory-only 差分控制，共 36 项，均无跳过、失败或错误。仅合成库/编译器回执与 fake loader，没有 Vector/Matrix 原生算术或构建。测试可能导入 NumPy 元数据依赖，不能表述成整个测试进程没有任何原生依赖。
- 所有上述最终测试限定 1 CPU、512 MiB 地址空间，每个 suite 最长 120 秒、cold CLI 最长 30 秒。没有模型下载、原始工作区运行/写入/发信号、远端 CI dispatch 或 push。
- 保留本轮两次稀疏 checkout 的准备失败：初次 router suite 缺本地 profile 文件导致 3 个 setup 错误；初次补充 controls 缺本地 `qwen35_35b_exp` 包导致 1 个 import 错误。只从独立副本已有 Git 对象补齐文件后重跑通过，没有修改生产实现或绕过检查。

## 源与配置兼容性审计

- Vector 旧 SHA `37e3af3886b2892335b0b765b676dfa9effcee27de4984ce1de3199c148f787a` → 当前 `d8a7ce5456507d5f29423434aa3d985b4ccff50744f832f5b06b7cfebb81c533`。AST 对比中 `op`、`mul_add`、`acquire`、`release` 与异常诊断构造不变；改变在后端选择/编译回执准入、构造绑定身份以及新增校验辅助方法。
- Router replay 调用仍显式 `IEEE_POLICY`，但没有传 `arithmetic_backend`，因此仍是默认 legacy，而不是 R2。两种异常 mask 仍为 30/28，原 legacy C++ 与编译参数未改，新增 ROOT 由原 `rms_owner` 指向同一仓库根。旧 legacy 回执可以在原有完整检查下验证，并不自动推导这次 router 数值等价。
- 既有 Vector 资格只覆盖 58 个冷控制和 3 个小型 native 测试（280 次单操作、84 组单独/批调用比较）；它不覆盖这次 saved-postnorm M16/M128 router。此处仅审阅该历史限定证据，没有重跑 native，也不继承其 PASS。
- TypedMemory 旧 SHA `a0d454595709a056e296fd7212449fa8393c87d8a0893703fee8ac8b0b024391` → 当前 `fac5ab5f56602132691c91074fc15b364b8a1f52aef329eab7b1ceb3060f8529`。只有 `_resolve` 的 exact-int 终点计算提升；其他生产函数 AST 不变。19 个 memory-only 用例不能替代真实 owner/数值终端资格。
- 原上游 config、完整 router class、全部原 pins 中其余 106 项在本批编辑前一致；router geometry 仍为 H2048/N256/top8。payload source manifest 与 model profile 原来由 packer/bundle 的精确 hash 间接保护，本批 cold map 与 workflow paths 直接补齐。冷 suite 的实际仓库文件读取审计没有发现上述 map 及两份 identity 文件以外的 source/config 依赖；这不是外部 runtime 或所有未执行分支的完整依赖闭包证明。

## ongoing

- 本批独立 diff 审阅已通过，准备本地小提交；由既有发布任务协调，不从本副本 push。

## todo / TEMP

- 在最终发布 SHA 上重新验证 `qwen35-router-logits-cold`，以 exact SHA 的新 CI 结果为准，不能重跑旧 SHA 后视为新实现通过。
- 当前 actual replay 资格为 TEMP，仍被旧 source map 拒绝。若要重新建立资格，另行准备明确标记未资格化的新 replay revision，保留本份历史 manifest；不得直接把新 source hashes 填进旧 manifest 冒充旧证据。
- 新资格需要在原显式 frozen fixtures、相同 legacy Vector/Matrix/runtime 约束下，对 M16 和 M128 完整 N256 logits 重新执行 owner；运行新的未改上游参考与独立 C pair-reduction 参考，逐元素检查。还必须重新确认输入只读、完整 write/ACK/publication、资源保留/排空、source/native/identity 前后稳定，并保留 sequential 失败诊断。没有完成这些工作前禁止声明 actual PASS。
- 若未来改选 R2，必须单独记录所选 backend、库、编译回执及适用资格，不由本次 cold lock 或 legacy fixture 授权。
- 本轮未执行上述实际 replay、live postnorm 交接、router tail/完整 router、完整 block、Command128、RTL 或硬件性能测量，所有这些状态保持原样。

## 复核入口

- `PYTHONPATH=src python -m unittest candidates.qwen35_35b_router.test_payload candidates.qwen35_35b_router.test_reference candidates.qwen35_35b_router.test_logits -v`
- 对同一命令加 `-O` 再执行；随后分别执行 `python -S -m candidates.qwen35_35b_router.run_logits --out work/<fresh-cold-directory>` 与 `python -O -S ...`。
- 小型证据记录：`candidates/qwen35_35b_router/cold_qualification_20261024.json`。原始本地日志保持 ignored，不作为源码或 PASS 继承授权。
