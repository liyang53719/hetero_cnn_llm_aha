# P1/P2 新输入 byte-provider 重建（2026-10-28 23:24 UTC）

## DONE / 精确 PASS 范围
- 官方原始 0.8B L0/L3 共 14/11 个完整 native tensor，逐文件复核实际 SHA256、固定 revision、名称、shape/bytes/dtype；没有重新下载或复制权重。
- 调用已发布原始 `emit_cold128_programs.common(1/2)` 重建完整 128 token metadata，commands/descriptors 与恢复件逐字节一致，launch/tensors/schedule 一致；分别 17/219 和 22/261。没有用单 token 循环替代 chunk。
- 当前真实 C++ `host_axi_driver_non_dpi.cpp` Config 和 `affine_tsv_loader.hpp` 原样编译用于纯传输资格；P1 147 组/8,387 字节，P2 124 组/7,228 字节独立 NumPy materialization 对照通过。包含首尾、非对齐、行边界、AB 分段边界；所有 source 全文件 SHA 在同一 mmap 上核验。
- 8 个正反例通过：两 profile 的真实配置接纳、错误 source SHA 拒绝、独立期望字节损坏拒绝、缺失 input view 拒绝。

## 新映射与数据隔离
- 仅 `full_block_P{1,2}_20261028T2307/reference/input_only` 的 NEW external-boundary hidden_storage，以及 P2 rope_packed；不继承历史 embedding/prefix 输入身份。
- Dense native BF16 `[N,K]`→logical `[K,N]` 仅地址转置；P1 AB 为 a 再 b；norm/A_log 原生 FP32 保留，其他 BF16 原位保留；无浮点计算、FMA、近似或舍入变化。
- P1 history/state 为明确 cold-zero；dt_bias 的 32 字节尾巴仅 64-byte AXI allocation 的确定性 padding，不改逻辑 tensor 长度。
- RW/intermediate/output 只声明空间，没有注入参考中间值、最终输出或 router IDs；dense scratch 固定原 program region。物理硬件源完全未改，32-lane/4096 MAC 不重新 elaboration。

## INCOMPLETE
- 本 PASS 是 provider/config/实际输入字节资格，**不是 Chisel/RTL/full-block 数值 PASS**。没有 DUT 实例、未运行完整仿真、未测利用率。
- `LOGICAL_HASHES.json` 为独立 NumPy 逻辑物化（含 bus padding）hash，不声称 C++ 全流 hash；C++ 实测为列出的边界 probes。
- 当前 program guard/HW 完整执行与数值链仍由父任务开展；运行前保持 source 文件不可变。

## 复现 / 暂存
- `rebuild.py --root WORKSPACE --output NEW_DIR` 仅产生新目录。脚本要求本次 native receipt 与 input-only capture，元数据不能替代缺失 payload。
- `probe.cpp` 用 `g++ -std=c++17 -O1 -I <published backend/source> probe.cpp -lcrypto -o probe` 构建。
- `qualify.py` 演示当前目录结构正反例。`PRIVATE_PROBES.tsv` 含真实输入字节，绝不发布。runtime/views 含机器路径，为本地运行配置；portable 仅脚本/pin/hash/摘要。
- 未删除、未清理旧证据，未上传 weights/NPZ/probe hex，未 push。
