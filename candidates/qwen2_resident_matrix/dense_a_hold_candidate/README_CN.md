# 默认关闭的 Dense A-hold 控制候选

本目录实现独立 `DenseAHoldModel(enable_a_hold=False)`。默认关闭时，
Queue4、A/B read、DMA、seed、Matrix、tile 和 writeback 的逐周期事件与冻结
FFN-window/Down owner 相同。打开时只把同一 K 的 context0 A gather 保存为
256 B hold，后续 context 仅读 B，并把 A 位值复制进各自 Queue3 entry。

这是实际调用既有 bank read、cold DMA ingress 和 owner retirement 的 Python
控制实现。尚未接入 Chisel、Public runner 或 RTL；测试中的 Matrix result 是明确
标注的有限值 transport fixture，不是模型权重或算术参考。相同 accepted Matrix
packet 的全位比较证明本次调度没有改变任何逐 context 的 K 顺序、操作数、clear、
last、finish、emit；不代表新增了完整 block 数值或利用率验收。

## 可执行行为与资源账

- 默认 Queue4，开启后 Queue3。每个同步 RAM read 在发出时保留一个 response
  credit，`len(fifo)+pending <= 3`。response 不能被下游 backpressure 停住。
- 首个 context 同时读取既有 8 个 A bank 和 2 个 B bank；后续只读 2 个 B bank。
  Python `pending` 中的 RAM 数据表示一拍同步响应线，不是额外响应 SRAM。
- hold 只在 context0 的响应边沿捕获。context1 可以在该边沿发 B 请求，B 响应
  下一边沿才读取 hold。最后一个 context 的响应复制入私有 FIFO packet 后释放
  hold；旧 packet 即使尚未被 Matrix 接受，也不依赖后续 hold 内容。
- 不借用 finalValue、结果队列、aHigh ingress hold 或 B SRAM。A/B allocation
  仍为 688 KiB / 80 KiB，B 行布局、单 descriptor loader 和两个 half 完全沿用。
- 每个 Matrix packet 有效负载为 128 BF16 A + 32 BF16 W = 320 B。原 Queue4
  有效负载 1280 B；Queue3 + hold 为 960+256=1216 B。名义 bundle 为 544 B，
  其中 112 个 B lane 恒零，不能把这些可能被综合消除的位称作现有物理储存。
- 新控制显式预算 112 bit：当前 generation 32、hold generation 32、pending
  generation 32、hold global-K 14、hold-valid 1、pending-read-A 1。原 pending
  K/context 继续使用。该保守 metadata 预算为 14 B；mux、比较器、时钟负载和
  FIFO 实际综合映射另行验证，1216 B 并不是面积或频率结论。

当前 A bank 仲裁仍沿用 owner 独占。B-only edge 的确没有发 A gather，但本候选
不会自动授予 FFN tile/SFU 访问，也没有新 A SRAM read port。实现 FFN overlap
仍需独立 read-tag 路由、RMW write reservation、live tile 与结果 fence 证明。

## 失效、fault 与 debt

setup、N group、K chunk、FFN window execute/A fence 都建立新的不回绕 generation。
每次 context0 响应必须匹配当前 generation/K。最后 context capture、输入区域
clear/load write、lease invalidate、abort、local reset 和 fault 都清除 hold。
FFN 上部 tile 写不破坏与其不重叠的下部 A input lease。

运行中 invalidate-lease 会 poison 当前 job 并按原协议 drain，不能以重新读取 A
来悄悄改变已接受的 Matrix group。idle invalidate 允许下一次普通 fresh load，
但复用已失效 window lease 会在新 gather 前被拒绝。generation 达 UInt32 上限
后锁定，必须 coordinated reset，不允许回绕匹配旧响应。

同一边沿 DMA fault 可能发生在旧 scheduler 已计算 can-issue 之后。本候选在真正
bank issue 前再次检查 poison，禁止新读；同步旧响应仍退还其已保留 credit，但
不恢复 hold。只在被丢弃的 drain entry 中形成零 placeholder，永远不送 Matrix。
若错误在本边沿更晚的 Matrix result 检查才被发现，本边沿合法接受的 bank 请求
仍是必须排空的债务。local reset 不清除债务，只有真实 coordinated reset 可以。

## 冷启动测试与边界

运行已有环境，不下载依赖：

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_candidate
/workspace/shared/hetero-contracts-venv/bin/python -O -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_candidate
```

测试从 job/window admission 开始，A 只能经接受的 DDR beat、同步 RMW 和 fence
到达 banks。B 只能经既有 descriptor 接收填充。所有结果经过最多两个 joined
result slot、finalValue、tile 或 DDR writes/ACK 后才产生 terminal。

覆盖 M16/M128、1/3/5 context、N256 尾组、BF16/FP32 输入、两个 K chunk/prefix
restore、长 Matrix stall、pending response credit、abort/local reset/lease
invalidate、stale generation、同边沿 DMA fault、generation exhaustion，以及
fresh Gate window 后 retained-A Up window。数据由有限值地址模式生成。
具体几何为 `(M,K,N)`：`(16,32,32)`、`(16,32,96)`、`(16,64,160)`、
`(16,32,256)`、`(128,32,160)`、`(16,256,256)`；FP32 ingress 单独覆盖
`(16,32,96)`。26 项测试另含 held DMA response、已接受 A RMW、held write
ACK/joined result 和 prefix seed obligation 的 abort 排空回归，未返回的 backend
debt 会阻止 terminal；没有用提前发送 MatrixDone 来跳过未排空结果。

`COLD_RESULT.json` 是 M16 K32 N256 的可重建 transport receipt：256 个 packet
位值与顺序相同，A gather 从 256 降到 64，192 次 gather 仅读 B。测试对文件逐项
重建比较。完整 M128 七个投影的 1,462,272→298,496 gather、平均 4.899 倍复用
仍是此前 source-pinned shape 计数，本目录没有运行完整投影或 M128 block。

## 后续 Chisel 接入点

依赖来源及 SHA256 固定于 `source_pins.json`；不修改这些文件：

1. `transposed_down/owner_down.patch:295–321` 的 Queue4/readPending/issue loop：
   加默认 false elaboration 参数；开启才选 Queue3/256 B hold。reserved 必须含
   尚未返回的 synchronous read，不能只看 Queue ready。每个 queue entry 继续有
   私有 A。既有固定 K、context 内循环和 terminal flags 不变。
2. 同 patch 的 `TransposedDownOperandRead` 加显式 readActivation，响应增加
   对应 activationValid/tag；A `readEnable` 改为 load 或 gather 且 readActivation，
   B read-enable 不变。禁止在 B-only response 使用 SRAM 的陈旧 activation 输出。
   legacy false 路径仍每次读 A，不能影响原 Host 配置。
3. 同边沿 context0 capture/context1 issue 需要显式 next-state predicate：已有效
   hold，或本拍匹配 generation/K 的 context0 RAM response 即将捕获。不能依赖
   Scala 语句顺序形成组合穿越。C=1 时 packet 取当前 RAM response，而 hold-valid
   在该边沿最终为 false；last-context 与下一 K read 的边界也必须按此优先级处理。
4. `ffn_window/window.patch` 的 setup、A lease invalidation、beginExecute 和
   Down 的 chunk advance 接到同一个失效网。全部同步 response 必须带已接受时的
   generation；fault 优先于任何 cache-valid 写入。已有 result/seed/DMA debt
   仍由原 owner 负责，不能用换 generation 清空它们。
5. 当前 `ffn_tiles/tile_ports.patch`、window owner 的 whole-owner 仲裁继续成立。
   将空出的 A slot 分给 FFN 是下一项独立控制改动，不包含在本次模型中。

W 物理布局/row burst、多 descriptor credit、Silu 微序列和 divider 配置属于独立
候选。原 W serial loader 与 options0 divider 下限仍在，A-hold 本身不能证明
80%/90% 利用率，也没有 1 GHz、面积或实际 SRAM 时序结论。
