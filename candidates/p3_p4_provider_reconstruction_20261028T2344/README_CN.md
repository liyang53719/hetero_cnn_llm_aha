# P3/P4 新边界全专家字节供应器（输入字节资格 PASS，非 DUT）

目的：为统一固定 4096 Matrix MAC / 32-lane Vector 候选的五块 M128 回归重建 P3/P4 的运行输入，不改硬件定义、接口、程序或原 PyTorch 路由基线。

- P3：Qwen3.5-35B-A3B L0，原 13 条命令 / 199 个 descriptor，18 个完整原始张量。
- P4：同模型 L3，原 18 / 241，15 个完整原始张量。
- 模型 revision `62704185bd97ad488cfc404e7caea797396b74dc`。语义绑定来自固定官方 header 名称、shape、dtype、byte range；历史 SHA 集合仅做额外一致性检查。
- 三个专家逻辑数组均覆盖 256 个专家，不筛选参考选中专家、不注入 router ID 或参考输出。
- 原始 `gate_up_proj`：[256,1024,2048] BF16；gate/up 分别取输出维前/后 512。down 原始 [256,2048,512]，逻辑 [256,512,2048]。仅字节转置，不进行数值计算。
- hidden 是新的确定性外部 block 边界，并非上游 embedding/prefix：BF16 [128,2048]，SHA `c32e36dd356244838b17f8aebd8a0e647c5a09198365ad32c6f7996adef237bb`。
- P4 RoPE 必须是独立官方 42ca970 路径生成的输入专用 BF16 [128,64]，且传入独立预期 RESULT SHA，再核验 input-only 文件、形状、dtype、大小、SHA 和官方 source/helper pins；不能任取同大小文件。其生成 receipt 是外部依赖。
- 冷启动 history/state 全零；只给 readonly 区绑定输入。RW、虚拟中间值不预填参考值。

## 重现与依赖

`rebuild.py --repo REPO --programs PROGRAMS --payload PAYLOAD --inputs INPUT_ONLY --output NEW_OUTPUT --profiles 3 4 --reference-result P4_RESULT --reference-result-sha256 INDEPENDENT_RESULT_SHA`

REPO 必须包含 `candidates/five_profile_byte_provider`、`candidates/five_profile_input_recovery_20261028` 和未修改 C++ loader。`DEPENDENCIES.json` 明确 pin 源码、官方元数据及原程序文件。PAYLOAD 须有完整官方原始 tensor `.bin` 和 `.receipt.json`，不随本包上传；INPUT_ONLY 下须有 P3/P4 的 `hidden.storage.bin`。输出目录必须新建，不覆盖旧证据。

脚本用有界流式读取重验完整原始 SHA；不完整物化 1–2 GiB 专家逻辑数组。独立 probe 从原始坐标按字节寻址，不复用 C++ affine stride 解释器，覆盖每个专家首/中/尾边界。

`probe.cpp` 仅定义 `HOST_DRIVER_CONFIG_ONLY`，加载真实未修改 Config / affine loader，不实例化 DUT。编译方式：`g++ -std=c++17 -O2 -I REPO/candidates/host_runtime_non_dpi_backend/source probe.cpp -lcrypto -o probe`。

`qualify.py --profile NEW_OUTPUT/profile3 --output NEW_QUALIFICATION --probe ./probe` 检查正例和 SHA 损坏、probe 损坏、输入视图缺失、最后专家缺失、gate/up 半区交换五个负例。C++ SHA 会触及完整 mmap，因此运行必须由资源调度准入，不与昂贵前端盲目叠加。

## 精确证据边界

实际 C++ 正/负例已经通过：P3 为 2,480 组 / 159,723 字节，P4 为 2,458 组 / 158,554 字节；每块各 6 项正/负例。只代表输入字节供应资格，不是完整 Chisel / RTL 数值通过，没有利用率实测。没有完整逻辑流 SHA 宣称；完整 SHA 是原始原生源，逻辑验证是边界 probe。

`PRIVATE_PROBES.tsv`、原始权重、hidden/RoPE 二进制、运行生成的 commands/descriptors、编译 probe 都仅本地保留；不进入可移植纯文本发布包。失败日志及旧目录保留，未清理。
