# TEMP：原始 Chisel runtime norm 父链与真实 Admission txn0 修复

本批保留原始实现代码与真实有限结果，不替换根入口或已生成 RTL。

- 原父错误 drain 的 r2 修复加入 activated 子资源 fence；14 源仅编译通过，新52类。未知 format 回复导致 child quarantine 时不得只用外部 transport quiet 宣称 drained。
- 历史2suite4case为 **3/4、整体FAIL**：norm两条协议/abort与DDR epoch通过；旧Boundary将txn0当无效哨兵，context探针失败。旧STOP/FAIL不改。
- Boundary r3 唯一硬件谓词去掉txn0哨兵，显式修旧期望。真实 Admission test 从 dispatch.fire 建立 owned，拒绝结果 holding 的 active=true 不授权。4源类型通过，新15类；后继 **2suite3case实际PASS**，包含Boundary元数据、真实首txn0/后续1..4全context/非法holding及旧DDR epoch回包隔离。不是重新跑旧4case，norm数字仍未测。

## 未完成与资源边界

正常宽度 RMS reduction/Scalar/format 数值、完整 GDN prep/chunk/后处理、唯一真实Host allocator/physical arbiter/最终live drain接回尚未验收。RawPrep 35B gate2仍不可凭软件recipe对照自动开放；72MiB旧arena是未批准提案，64MiB生命周期方案也待真实授权。固定三bank RMS控制不代表额外资源已接入统一top。所有外部客户端必须绑定真实accepted完整context、source/dst、权限与current/late fault，不能host completion或Bool授权。

五profile必须使用同一硬件和接口。用户选定后继32lane II1方向，当前仍未实现/未冻结新bank ABI；旧16lane和4096结构证据不迁移。原833b Host快照首片与拟844b统一版本、FIFO后端变换不夹入本批。Qwen2 ordered QKV和FP32存储边界保留，不转换成Qwen3.5 BF16布局。

顺序仍是五块原始Chisel M128数值→冻结同源码/输入/参考→同4096 RTL回放。目前完整Chisel与RTL均0/5验收。请按SOURCE_SELECTIONS分阶段编译，不能一次编译全部源码或依赖类shadow；REPRODUCTION只是精确角色化命令，非已自包含hermetic运行包。
