# Qwen3.5-0.8B L0 M128：真实输入与当前目录 Matrix 构建恢复

本记录只关闭真实输入缺失与 Matrix 构建回执目录绑定两个前置缺口，不是完整 block 数值通过报告。检查对象是提交 `f5166c5d1b3311963926382d2139b89ef2151909`；没有继承任何已丢失产物的旧 PASS。

原计划 `plans/QWEN35_L0_M128_OFFICIAL_RECOVERY_20261023.json` 保持原样，仍是 `PLAN_ONLY_NOT_EXECUTED` 历史计划。实际执行证据另存于：

- `reports/execution/QWEN35_L0_M128_OFFICIAL_RECOVERY_20261023/RECOVERY_RECEIPT.json`
- 回执 SHA256：`5d3d46ef15f13a450f9d1d1fed5107f3b421a8cdfbb51c9d99ab767b7ab3f519`

## 已完成并独立复核

1. 通过现有 `input_fixture.py collect-embedding` 恢复固定 checkpoint 的 512 KiB embedding 切片。
   - 模型 revision：`2fc06364715b967f1860aea9cf38778875588b17`。
   - 范围：`bytes=70216-594503`；HTTP 206；`Content-Range: bytes 70216-594503/1746942600`。
   - 实际 524,288 B，SHA256：`5e6f4f309ddda446bf86c961ea13fc12030713b6cac428f7af6c8f9d1b5b83da`。
   - 获取回执时间：`2026-10-23T16:47:00.765399+00:00`。这不是完整 1.747 GB checkpoint 的整体 SHA256 验证。

2. 通过现有 build/verify-fixture 路径重建原始 BF16 输入。
   - 仅按固定 token 顺序复制 embedding 行，不执行模型、不生成中间 golden 或状态。
   - 原有 14 项 L0 权重共 43,111,008 B 全部复核并复用，没有重复下载、复制或转换。
   - cold128：262,144 B，SHA256 `6e8c1a99dd98313abeb693afbe1fdf3aece5ebfab4b19f4737f3b663a0013b54`。
   - carried128：262,144 B，SHA256 `01e6c989b40eb2a9774cb9fe93f9818fb18128e996771ec581fdb23587270fc0`。
   - 输入 manifest SHA256：`e21aa8318cdfbb8b982753288a3a8b9bcfc946dc20bd4c9424e545ca1761333a`。
   - 这里的 carried128 仍只是第二段输入名称；没有据此声称已执行真实 carried-cache block。

3. 使用现有受信编译器，实际生成当前仓库根目录绑定的 Matrix 库与新回执。
   - 入口：`scripts/build_shared_matrix_recipe.py`。
   - 回执状态：`PASS_HOST_BUILD_ONLY`；退出码 0；持久化回执记录编译耗时 0.5625399749842472 秒。
   - ELF：27,032 B，SHA256 `32b02255280c12c6eb3ec39ee02baa989e4c7a55c5f0e89f80edd1011ce7b7cc`。
   - 编译回执 SHA256：`0425ab17f2126cf8a3d0362e590d894898f586fb929c34c207a4dba2b3e80cf0`。
   - 当前根目录、精确编译 argv、编译器 SHA256、编译前后源文件 SHA256、库大小与 SHA256 均通过独立只读验证。
   - 两个编译 translation unit 加上被 include 的 `numeric_smoke.cpp` 构成三源文件闭包；此 GDN 路径不要求可选的第四个 official-BF16 wrapper。
   - 未改旧回执，没有加载 ELF，也未调用数值符号。

## 证据强度与资源边界

上述字节、来源、目录绑定与库身份从磁盘产物直接复核。原执行工具另报告：普通网络 canonical HEAD 返回 302，目标主机为 `us.aws.cdn.hf.co`；没有保存可重新审计的原始 HEAD 或 launcher 日志，不能将这部分冒称为磁盘日志证据。签名跳转查询参数没有写入公开候选记录。

Matrix launcher 的 1 CPU、1 GiB 地址空间、65 秒 CPU、75 秒外层超时与 5 秒终止宽限，以及 builder 内部 60 秒编译超时，明确列在回执的“执行工具报告”部分，与直接验证的 compile.json 分开。没有进行网络或文件系统限制绕过。

独立校验没有导入 Torch、加载 Matrix ELF 或运行模型/DUT。现有 `heteronpu` 包初始化会传递导入 NumPy，因此不声称这是无 NumPy 导入的纯标准库进程；一次辅助的“不得导入 NumPy”断言失败不代表输入或构建身份验证失败，确认导入来源后已重新通过预期的只读身份检查。

## 后续门禁仍需真实完成

- 官方隔离运行时仍须单独恢复、锁定依赖、验证安装来源并产生新的真实 qualification 回执。本回执不建立运行时 ready 状态。
- 原 `rebuild_qwen35_official_runtime.sh` 不能原样作为该门禁：缺少 Transformers 相关依赖，并且回执结构不满足 native capture 所需的 `artifacts`。
- Transformers 必须使用固定 commit `14e738b5d0cc69aa27a95dde272aea41fde44f2f` 及 ZIP SHA256 `15a8ff42ef4fba57ff51034e1cd7d3672dec2bf1cf080134eb69d13c69ee6a2d`；不能伪造 canonical URL 的安装来源。预下载有大小限制，不代表后续 pip 重新取包也已被限制。
- 运行时就绪后，先运行独立的真实 M16 reference，再运行真实 M128 reference。随后用显式 R2、IEEE、K512 projection 与 experimental equal-head exp 策略执行新的完整 cold128→carried128 typed block，并使用原门限比较。
- 本次未执行官方 forward、完整 typed block、数值验收或 RTL；这些结果不能由输入哈希或 host-build PASS 推导。

只保留可复现源码入口、pin、hash、尺寸、摘要与经过区分的证据。权重、输入、编译库、含私有绝对路径的本地 manifest 没有上传或提交，禁止以文本编码替代上传。本次也没有 push 或公开发布。
