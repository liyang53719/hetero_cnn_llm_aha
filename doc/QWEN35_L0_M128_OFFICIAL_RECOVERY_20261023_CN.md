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

## 追加：2026-10-23 17:20 UTC，官方隔离运行时实际就绪

以上 `PLAN_ONLY` 与九项输入/Matrix 恢复回执属于先前时点的独立历史证据，不回写为运行时 PASS。本追加只关闭新的官方 Python 运行时资格门；新的官方 reference、完整 typed block、数值比较和 RTL 仍未执行。

可公开复核：[运行时安全摘要](../reports/execution/QWEN35_OFFICIAL_RUNTIME_20261023/QUALIFICATION_SUMMARY.json)、[当前门禁与重建计划](../plans/QWEN35_L0_M128_CURRENT_GATES_20261023.json)、[精确公开依赖锁](../config/upstream/qwen3_5_0p8b/official_runtime_lock_20261023.json)。原 `PLAN_ONLY` 文件保持不变；新获取器的源码/fixture 测试不能冒称本次历史获取已经使用该脚本。

### 新安装与资格结果

- 根进程实际执行新安装及 `scripts/qualify_qwen35_official_runtime.py`，qualification 退出码 0；新回执状态为 `PASS_ISOLATED_PINNED_RUNTIME_READY`，22 项非空、严格布尔检查全部为 true。回执时间为 `2026-10-23T17:20:35.449031+00:00`，没有继承旧目录或旧 receipt 的 PASS。
- CPython 3.12，隔离 `site-packages`，`-S`、禁 user-site、固定 PYTHONPATH；加载模块路径和当前进程 native maps 已检查。Torch `2.10.0+cpu`，git commit `449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`；NumPy `2.3.5`；Transformers `5.19.0.dev0`。
- Torch 导入前为 `ATEN_CPU_CAPABILITY=default`，实际 DEFAULT dispatch、单允许 CPU、intra/inter-op 各 1 线程；确定性算法、最高 float32 matmul 精度与 inference/no-autocast 状态通过检查。这里只核运行时策略，不构造 Qwen 层、不加载权重、不执行模型 forward；实际模型的 eval/inference 仍由后续 capture 门验证。
- Transformers 保持固定 commit `14e738b5d0cc69aa27a95dde272aea41fde44f2f`、canonical GitHub archive URL 及原 ZIP SHA256。原生 pip `direct_url.json`、安装报告及构建 wheel 的 origin 均一致，没有手写或修复来源元数据。四项固定官方源码及全部已安装 Transformers package 文件均与固定 archive 核对；构建 wheel 另锚定生成的 metadata。
- 38 项已锁 wheel 中，pip `26.2.1` 只用于独立 bootstrap；37 项运行时 wheel 加上从固定 archive 构建的 Transformers，构成 38 个已安装 distribution。实际 wheel/安装 METADATA、Python 与 wheel tag 兼容性、marker/extra 传递依赖、原生 RECORD、console script 以及完整已安装文件归属均经过检查。没有使用 host site-packages 补缺。

### 失败尝试与离线边界

第一次新安装在最终 guard 审计时失败：固定 pip 所带 urllib3 的导入期 IPv6 能力探测试图创建 socket，被原有 guard 拒绝；失败证据完整保留，没有 runtime-ready receipt，也不计为成功安装。第二次使用另一全新目录；仅避免安装器不需要的该项能力探测，临时值在导入后恢复，未放行原被拒绝的 socket 操作，也未改变系统安全设置。

第二次安装的两个父进程阶段各有实际 socket 拒绝自检与 pip transport 拒绝自检；每个实际 backend PID 均对应显式 guard 激活及入口验证。qualifier 独立复核事件类型、次数、顺序及 PID 集合，拒绝任意多余拒绝事件，不以泛化的“预期自检”标记掩盖失败。依赖安装只消费已锁本地文件；固定 archive 使用原生 pip verified-download cache 路径，canonical Link 与来源记录不改。

这是 Python 层审计和固定受信源码范围，不是任意 native 代码的 OS 沙箱。现有解释器、已加载标准库和系统 native 库有测量记录，但没有重新构建并证明完整解释器/OS 源码闭包；`complete_environment_closure=false` 必须保留。

### 可复核的有限证据

- 新 runtime receipt：7,331,503 B，SHA256 `2ce86dceb6b34bf9b9974023e5df9d25b3fe4e27ac3f3ed96dab80e121914c4d`。
- qualification 输出：2,474 B，SHA256 `eae7b8f6a52b5496a7d736b610239bf1de171caeabba201b449d4e33a5800818`。
- 精确依赖锁 SHA256：`806f6a7f409e85965261bf864fcc8de4558aaedf9f3da26759323625ca131497`。
- 运行的 qualifier 源码：50,210 B，SHA256 `7686d0da3a220607b91f73934a22df7a949eda2ab74d6c89c20a82fdfe6e74f4`。
- 回执含 23,582 个 artifact 记录，去重后为 23,575 个路径、1,237,248,965 B；不能把“记录数”说成“不同文件数”。其中已安装文件 19,964 个，bootstrap 文件 476 个，保留原生 Transformers stage 文件 3,065 个。38 个锁定 wheel 与 installer/driver/guard/runner、wrapper、来源报告和资格源码/输出均有当前路径、尺寸与 SHA256。
- 独立标准库只读校验重新哈希了上述全部记录，3.74 秒退出 0，并核对新回执与不可覆盖的 candidate 字节一致、失败尝试没有 ready receipt。该复核没有导入 Torch、加载模型或重跑资格过程。
- qualifier 的 24 项标准库 fixture 测试实际通过，0.019 秒；覆盖空/伪真 checks、路径逃逸、符号链接、重复 JSON/ZIP、安装 RECORD 篡改、pip 原生路径重定位、vendor metadata、entrypoint 内容和 guard/PID 负例。这是代码契约测试，不替代上述实际 runtime qualification。

根执行工具报告的资格进程资源限额为：1 CPU、4 GiB 地址空间、260 秒 CPU、qualifier 内部 240 秒 alarm、外层 300 秒及 5 秒终止宽限；不把这些 launcher 限额冒称为回执内的独立资源测量。fixture 测试另用 1 CPU/512 MiB/30 秒限制，不与 runtime 进程合并。

完整 receipt、文件清单和绝对路径仅在本地保留；公开候选只包含复现脚本、锁、hash、尺寸和安全摘要，不上传权重、输入、输出、NPZ 或可重建权重的文本编码。下一步仍是各自独立进程的新 M16、M128 官方 capture，再执行完整 cold128→carried128 typed block 和原门限比较。运行时 ready 不是官方 block 数值 PASS、候选 PASS、RTL PASS、硬件周期或 MAC 利用率证据。

## 追加：2026-10-23 17:29 UTC，新 M16/M128 官方完整 L0 reference 已实际捕获

运行时批次提交 `93fb48799da266ff75d050d474a50437f8fcd091` 后，根使用未改动的 `native/capture.py`，先后在两个独立新进程与新输出目录执行 M16、M128，均退出 0。M16 逐项复核通过后才进入 M128；没有重用丢失的历史 capture 或给旧回执补 PASS。运行的 capture 源码 SHA256 为 `72c5181034162ee9a475d3118c85a18dab62e50348ab6e753795cbfefa8f03e7`。

- M16 是 `cold16_then_carried16_from_second_window`，取两个原始 128-token 窗口各自前 16 行，实际 prior token 数为 0、16。每次实际官方调用为 1 个 64-token chunk，padding 48；不能称为 cold128/carried128。共 91 个 tensor 文件、11,359,232 B activation；记录耗时 9.967843943 秒，峰值 RSS 567,615,488 B。
- M128 是真正的 `cold128_then_carried128`，两个原始输入窗口逐字节一致，同一 DynamicCache 对象连续使用，实际 prior token 数为 0、128。每次官方调用为 2 个 64-token chunk，padding 0；carried 的卷积历史与 recurrent initial state 均与 cold 的最终 cache 位一致。共 91 个 tensor 文件、45,113,344 B activation；记录耗时 11.168520706 秒，峰值 RSS 564,559,872 B。
- 两次均保留原完整 24-layer 配置，仅构造并执行官方完整 decoder layer0；14 项原 checkpoint 参数的 bytes、shape 与 BF16/F32 存储类型核验通过。实际 DEFAULT dispatch、1 CPU、intra/inter-op 各 1 线程、eval、inference、禁 autocast、确定性算法及最高 float32 matmul 精度均记录在 manifest。
- 独立标准库只读复核逐项检查两次各 91 个 tensor 文件、精确目录清单、23,583 个 runtime provenance 记录、8 个源码记录及 fixture/payload manifest，尺寸与 SHA256 全部匹配；另核对输入切片、chunk 几何和 cache 连续性。复核没有重跑模型、reference 或候选。

M16 manifest 为 8,966,353 B，SHA256 `e2ab33feaafda28e70b387e5f872ff12caa1884ddc2ca981243066a41c549e2a`；M128 manifest 为 8,966,736 B，SHA256 `d2ad73c9b8742e8419c3c2dc453fd2c3ff08288e6781746c31bee33a5a1bd5c4`。公开的 [reference 安全摘要](../reports/execution/QWEN35_OFFICIAL_REFERENCE_CAPTURE_20261023/SUMMARY.json) 只列元数据、hash、尺寸与计数，不包含 tensor 数值或私有绝对路径。

观察边界仍明确：15 个 named module 各被调用两次，但 `linear_attn.conv1d` module forward 未调用，实际执行的是已捕获边界的官方 functional `causal_conv1d_fn`。没有声称捕获全部内部量；L2-normalized Q/K、FP32 三角系统/求解、每 chunk 中间状态和 functional residual/activation 内部仍不完整。hooks 返回 None，包装函数以原参数调用原算术并原样返回结果。

原 capture 自带 120 秒 CPU/wall 限额及 128 MiB activation 上限。根报告两次均使用独立 fresh pycache prefix，避免 `-B` 只禁写、不禁读旧 bytecode 的问题；这属于 launcher 记录，不冒称为 native manifest 中的独立测量。Python 包/解释器/OS 受信边界不变，不据此声称 OS 网络沙箱。

当前只新增“官方完整 L0 软件 reference 已捕获并验真”证据。完整 typed M128 replay、原阈值数值比较仍未执行；没有候选 PASS、owner/RTL PASS、硬件周期、吞吐或 MAC 利用率证据，五完整 RTL 仍 0/5。实际剩余门已更新至 [当前门清单](../plans/QWEN35_L0_M128_CURRENT_GATES_20261023.json)，历史计划、输入/Matrix 回执、runtime01 失败及 runtime02 资格回执保持不变。
