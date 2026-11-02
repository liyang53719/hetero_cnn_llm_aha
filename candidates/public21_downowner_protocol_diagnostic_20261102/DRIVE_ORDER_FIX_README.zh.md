# B 协议夹具驱动顺序修复

原云端 41423897669 实际完成 10 个准备/编译/emit/ports/Verilator/make 阶段，协议在 tick 62002、ng=0 的两 K-partial 之后断言 resetRequired；此时 owner status/bankReset 均 0，尚未到第二 N 窗。它不是原 P0 首因的已证复现。

真实原 DenseTileSumBridge 小模型三场景严格闭合：结果握手后尚未更新 mock valid 时，inflight 已清，组合 unexpected→tiles.abort 为真而注册 reset 仍假；先驱动新周期输入再采样后跨下一边沿无 fault；真正非法 valid 保持跨边沿仍产生 sticky poison。小模型无真实 banks/Matrix，并不授 B 或数值资格。

修复仅将原完整故障断言块移动到本周期所有 mock 输入驱动之后、握手采样之前，保留每个原断言、队列/计数状态和 early done 语义；新增仅首个 vector request/result 实际 fire 的有限 tick 输出。机械逆变换逐字恢复旧 Spec 和直接驱动。原 generator 实际再生新 driver 全字节相同，两修后源码实际类型编译成功；尚未运行修后完整 B。

不改 Harness、4710 端口、生产 Chisel、banks/矩阵容量、资源门或数值条件。原云端缺少当拍 vector fire 记录，因此不追认其唯一首因；后续完整 B 必须重新证明。
