# 共同命令入口：本轮固定开发与验收范围

基线：450c4ece604a91f75287c3956eb25dc5f24a38c7。保留已提交 real16 原512-MAC + pinned-iDMA 数据通路，不修改保留或生成的 SystemVerilog，不扩展新模型。

## 实施顺序

1. 增加 Chisel 共享 MemoryRequest 仲裁：命令、descriptor、现有算子数据复用唯一 pinned-iDMA；锁定在途 owner、重映射完整 tag、保持返回回压，错误后停止接收直至 reset。
2. 复用 Record128Reader，解码已有 tensor_base/shape4/stride3 和 SFU_PROGRAM 字段；检查 rank/dtype/连续 stride/64-byte 对齐/物理 DDR 区域与读写权限，不把地址编码容量当实际容量。
3. 先启用既有 SFU_VECTOR 二输入加法（residual）Command128，使用现有 ElementwiseMemoryEngine。只有最终成功写回、元素数和字节数一致，才能发布事件和完成。未知或尚未接通的 opcode 明确拒绝，不新增不透明 block opcode，不声明完整21-command图已接入。
4. 在共同生产 top 中串接已通过的 Qwen2 block 实际输出与 Host Command128 residual；共用同一 DDR 和唯一 iDMA，禁止 host/golden 中间态替换。先做短用例和错误注入，再尝试同一真实尺寸 real16。

## 验收证据

必须保存被测源码身份、Chisel编译/单测、实际生成电路数值/协议日志、请求/响应计数、写回后完成检查、实例数和文件哈希。unit stub 测试与真实 pinned-iDMA 集成分开记录。Qwen2 block 的15阶段和新增Host命令分别计数，不用后者冒充原始全部图命令。

本地 agent 不编码；本轮开发侧提供固定复核与执行入口。失败保留目录并返回日志，不改阈值/源码/参考。800MHz/1.250ns是时钟目标，不是本轮DC声明。工作文件、旧checkpoint和失败日志全部保留。
