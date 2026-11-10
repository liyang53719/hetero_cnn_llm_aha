# hetero 15:33：原 FP32 控制链候选，完整数值 INCOMPLETE

## 已完成
- main 590998b 的 CI 42837350545 success，仅可重建数据提交保护。无残留旧Host；内存可用约9 GiB、磁盘约51 GiB，临时清单已检查，未删除。
- 原HostBlockCommandsV4隔离执行真实Qwen2 M128 launch及已校验命令/描述符，实测Unsupported=4、pc0、完成0、元数据读取0、owner派发0，复现项目V4入口限制。不是上游整体不支持prefill。
- 明确区分实际编译闭包与较早恢复副本。候选基于实际已运行原Commands闭包，仅增加限定完整固定Legacy FP32安装组合的准入谓词，不切OfficialBf16、不改原typed/bounds/alias/算术/物化规则。
- 候选真实parser/dispatch完成21命令、19次owner派发、236次元数据读取、1231控制测试周期；QK/softmax/PV仍按原逻辑融合。全部19个job保留FP32地址/shape，weight/activation/output BF16及Dense物化四位均0。
- 以上返回为明确synthetic ACK，只是控制资格，绝非21-op数值PASS或完整block周期利用率。
- 负测：非法版本Unsupported4、失齐地址Bounds5、profile2仍Unsupported4；坏owner tag→Protocol7，完成0。保留原拒绝基线及测试初版失败归因。
- 四runtime profile实际IR层次/连接审计完成：现有RMS/Conv/RawPrep/Chunk/GatedNorm/QKNorm/RoPE/KV/GQA/Elementwise/StreamingDense及8Matrix端点已装；旧TransposedDenseDown/ResidentCoordinator未装。不能把入口拒绝说成所有runtime模块缺失，不能切全局数值策略蒙混。
- 原profile1（17命令/219描述符）、profile2（22/261）入口拒绝实测；同一Qwen2候选IR仍拒profile2。profile3/4本轮缺可核验冻结program，未伪造。

## 进行中
- 唯一真实Host候选 session92335 已启动，预算900秒/6GiB/1CPU；冻结候选Commands接真实AXI驱动，不含synthetic ACK。输入preflight通过。新完整Host源码/IR身份重新记录，不继承旧PASS；当前结果待定。
- 并行推进runtime服务能力与Qwen2数值策略分离，核真实typed/lease/staged receipt链，不按profile重elaboration不同硬件。

## 范围与阻塞
五块M128完整数值仍0/5，4096 MAC不缩减，无完整RTL数值PASS或完整block利用率实测。原head4 underflow FAIL不放松；35B真实权重访问与MoE同分契约阻塞未绕过。先前审查拒绝的源码/原始日志继续仅本地保留，本次仅允许最小摘要和hash。
