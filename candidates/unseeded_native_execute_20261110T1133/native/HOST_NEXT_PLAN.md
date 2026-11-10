# 原 Host 下一步只读连接审计（TEMP，未执行 prefill）

## 当前入口与不变边界
- 已读 `../scala/RunCurrentHost.scala`：固定 `QwenBlockShape(retainedMatrix=true,matrixColumns=256)`、`weightReadBeats=16,pipelined=true`；按当前 CHIRRTL pin 校验 iDMA 外部接口，经原 `IdmaFieldSplitTransform`、官方 Lowering/PrepareAst，绑定 17 个真实 native 实例。这里只 reset 两周期，没有 AXI 内存服务、launch、输出比较。
- 不启动第二份 Host；继续沿父任务 session 20218 获取构造终态。不得使用旧 `OriginalHostTreadleBinding` 的 OfficialBf16/seeded constructor。当前 4096 MAC 定义不改变，SFU 保留 IR，fatal/FP32/BF16 契约不变。

## 可复用实现（仅搬运/握手逻辑，不继承旧 PASS）
- `round_20261110T0133/recovery/sources/hetero_20261109T1934/tail_identity_1934/sources/selected_host/OriginalHostFrameTransport.scala`：完整顶层 pin 快照，以低电平更新数据，升/降沿稳定数据；调用 ExecutionEngine.setValue/evaluateCircuit，防止重复 poke 导致半快照求值。旧 schema 122 ports/41 inputs 需与本轮 low.circuit 精确核对后才能复用。
- `round_20261110T0133/recovery/sources/hetero_cloud_recovery_20261107T2134/host_pin_facade_1634/`：C++ pin-only facade 生成器、真实 AXI driver、affine readonly loader、sparse write memory。可把外部 driver 的 eval 接到上述当前 engine；不能调用旧 Session/gate 来偷换 constructor。历史 generator 会 git-show 旧提交并写文件，不能原样盲跑。
- `published_source_closure_recovery_20261029T1833/candidates/host_runtime_non_dpi_backend/source/host_axi_driver_non_dpi.cpp`：完整 launch、AR/R 与 AW/W/B 服务、写回观察、completion/result/drain/counter 检查。原实现只管理外存字节，不提供数学结果。

## 实际顶层信号
- launch: `io_launch_valid/ready`, `io_launch_bits_{version,profileId,epoch,commandBase,commandLimit,commands,descriptorBase,descriptorLimit,descriptors}`, `io_launch_bits_regions_0..3_{base,limit,read,write}`。
- 输入 AXI: `io_axi_{ar,aw,w}_ready`, `io_axi_r_{valid,bits_data[512],bits_id[8],bits_resp[2],bits_last}`, `io_axi_b_{valid,bits_id[8],bits_resp[2]}`；输出是对应请求、写数据及 r/b ready。512 位数据按 little-endian 字节装配，不改 FP32 存储。
- 输出握手/归因: `io_completion_{valid,bits[56],ready}`, `io_result_{valid,ready,bits_status,bits_completed,bits_failedPc,bits_epoch}`, `io_resetRequired`, `io_pc`、原 MAC/AXI counters。
- 历史 AXI driver 检查：64-byte beat、最多 16 beat burst、INCR、size=6、不能跨 4KiB；在低相计算握手、上升沿消费，按 strobe 提交写回，B/R ACK 守恒。完整 block 周期分母需覆盖 launch 到最终 drain，不能拿单叶子周期计算利用率。

## Qwen2 真实 payload 与桥接差异
- 已存在 `round_20261110T0733/qwen2_host_payload/manifest.json` 和 `REAL_INPUT_BINDING.json`：128 token、H1536/F8960/12Q/2KV/HD128，FP32，21 commands、215 descriptors。
- 表地址：commandBase=4294967296，commandLimit=4294967680；descriptorBase=4294971392，descriptorLimit=4294974848。只使用原 host_commands.bin/host_descriptors.bin，不重新以单 token 循环代替 chunk。
- 当前 payload 是 JSON+f32le/bin；历史 driver 要 `HOST_COMPILED_INPUT_V2` TSV、四区域及 affine views。需写纯格式适配器，复核每个文件的真实 hash/size/布局/地址，生成 ro/rw/virtual allocation，不能把 JSON 直接交 driver。
- 必须按 `allocations` 建区域；`cache_k/cache_v` 是 `kv` 内子视图，不能重复添加重叠 allocation。scores/probabilities 是 virtual，禁止当 DDR 预初始化。所有 scratch 从 DUT 写回产生，独立参考仅在执行后比较。
- 目录列表未见 `rope.f32le`：manifest 含 rope（2×1024×64 FP32），需从已 pin 的原 fixture/生成器提取并验证原 RoPE 输入，不能补零或用期望中间值代替。其余真实权重/输入文件存在不等于已重新全量复核。

## 有界顺序
1. 等原 Host 构造终态；若失败沿该身份诊断。成功后导出当前低级顶层 schema，精确比较旧 facade，保持所有观测输出。
2. 纯格式适配与配置解析小测：21-op 表、215 descriptors、readonly 真实输入和 RoPE 的完整 pin；不运行长 Host。
3. 在同一 constructor 的 engine 接外部 memory bridge，先验证 reset/一次 launch/原表 fetch；这是连接资格，不是数值通过。
4. 继续原 21-op 流程，逐 op 保存 DUT 写回和 flags，独立 Python reference 只在外部比较。保留 fatal 即停及原失败身份；从首个实际差异定位，不先跑长 RTL。

本审计仅源码读取和文档新增；没有修改硬件、启动测试、清理文件或提交数据。五块完整 M128 数值通过仍不能由本文件宣称。
