# 后续最小连接计划（尚未实现）

1. 原始 chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala：仅在 attLocal 的 K read 和 attProbScale 的 V read 分流；保留 packet、attDot、attPVCompute 和所有算术。新增默认关闭接口及显式故障消费抑制，不能把模型侧带当成已有功能。
2. 同目录 QwenOwnerProtocol.scala：在现有 mode-0 memory 仲裁中连接元数据缓存/贷款状态机。先接受核心读，再获得原 Down owner 贷款，再发 DDR miss；匹配 DDR reply 与 raw fill 同步接受。错误路径不修改原债务身份。缓存位仅在 clean fill ACK 后置位；用 raw reread 供数，不加数据影子。
3. 同目录 HostBlockTop.scala：只传播默认关闭参数/既有父模块连接。保持原顶层与核选择；mode0/active 在核心 held completion 和所有请求/ACK/lease 退休前不能切换。不得用全局 Matrix idle 阻塞 Attention 的借用。
4. 上述 patch 必须在当前完整原始 patch 组合后单独应用、单独固定哈希；保留已验证 raw bank 基线。先完成父模块 RTL 生命周期证据，再审查最小消费者 unit。禁止通过强制内部寄存器模拟 retained-A 生命周期。

## 失败状态表

- idle→acquire：接受一个合法核心读，建立 core_pending；若已故障，转 error_response。
- acquire→lookup：实际父模块 grant，retained-A 必须先一拍失效。故障转 error_response，无 DDR 债务。
- lookup：命中转 read_issue；未命中转 miss_req。
- miss_req→miss_wait：仅 DDR 请求接受时建立 ddr_pending；已 offered 请求即使 abort 也保持 valid/身份到 ready，然后排空真实返回。任何无债务的 supplier 回复均毒化。
- miss_wait：外来回复毒化但保留原债务；匹配错误/撤销回复退休 DDR 并转 error_response；匹配成功回复只有 raw fill 接受时才退休 DDR。
- fill_wait：稳定 raw 回复至 matching ACK；clean ACK 提交 valid 后转 read_issue；故障 ACK 排空后转 error_response。
- read_issue/read_wait：raw 同步读及稳定 held reply；核心 valid/ready 消费后撤回回复；若 raw ACK 尚未 ready，转 ack_wait 保留 raw 债务，后续 matching ACK 才退休。故障侧带禁止使用数据。
- error_response：稳定原 tag 错误直至核心消费。
- terminal：关闭新读；保留 mode0/active，等所有债务退休后释放贷款，再允许原 host completion。该门控不依赖 completion.ready。

## 验收界限

本批六文件是模型/来源/短测计划，不包含 consumer RTL。M128真实执行、原始算术数值验收、端到端吞吐、DDR性能及硬件资源结论仍待后续单独测试。父模块已编译/展开的结果不能代替其尚未完成的 RTL 生命周期验证。
