# P1/P2 provider 可移植 V2（TEMP / 未执行完整重建或 DUT）

此 V2 仅针对 V1 已实际通过的输入字节 provider 做路径参数化与 receipt fail-closed 加固。**本版只测参数/源码 guards；不得继承 V1 实际运行身份为 V2 PASS，更不声称 DUT 数值通过。** V1 的 runtime/views/原始脚本与既有证据均未改。

## 显式依赖
`DEPENDENCIES.json` 固定仓库相对源文件、原始程序、独立 acquisition 元数据的 SHA/长度。rebuild 启动先核这些依赖，再从 `reconstruct_plan.verified_plan()` 的固定官方 header/name/payload pins 重建计划，并逐字段核验 receipt，再检查 payload 路径 containment。禁止修改依赖 pin 来绕过失败。

```sh
python rebuild.py --repo /path/to/repository \
  --programs /path/to/programs \
  --payload /path/to/native_payload_root \
  --reference-root /path/to/reference_root \
  --acquisition-metadata /path/to/acquisition_metadata_package \
  --output /path/to/NEW_provider_output
```

- `programs/profile{1,2}` 必须含固定的 commands.bin/descriptors.bin/manifest.json。
- payload root 下须有 qwen3_5_0p8b/ 原生权重与 receipt；没有下载或假数据 fallback。
- reference root 下 `profile1/RESULT.json` 与 `profile2/RESULT.json`，其各自 `input_only/hidden_storage.bin` 及 P2 rope_packed.bin；可用本地目录链接指向既有完整官方 reference 目录，无需复制。仅指定 input-only 文件会映射到 DUT 内存。
- acquisition metadata package 是已发布独立计划/官方 headers/pins/脚本，依赖文件表详见 DEPENDENCIES；不包含权重。
- `rebuild.py` 要求 Python/NumPy；实际版本由执行者记录。

```sh
g++ -std=c++17 -O1 -I /repo/candidates/host_runtime_non_dpi_backend/source probe.cpp -lcrypto -o /path/to/probe
python qualify.py --actual /path/to/NEW_provider_output \
  --probe /path/to/probe --output /path/to/NEW_qualification_output
```

qualify 仅检查原样 C++ Config/affine loader 与实际字节/负例，无 DUT。它产生的 PRIVATE_PROBES.tsv 及重建器生成的同名文件包含真实输入字节，必须仅本地保留，不上传 Git。runtime.tsv/views.tsv 含执行机器绝对路径，不是 portable 摘要。可发布源代码、pin、无 payload 摘要。

本次 V2 检查：两个 CLI --help 成功；5 项源码 guard 测试普通和 python -O 各通过。未重跑 provider 重建、未执行 DUT、未扩展任何数值 PASS。
