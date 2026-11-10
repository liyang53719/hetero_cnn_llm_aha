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

## 真实执行与资源终态
- session92335因新IR hash输出目录未建，20秒退出，未到engine；保留后修目录。
- 后继96247进入真实原Host和AXI/Norm链：最后日志active320周期、owner1、iDMA读/ACK13、pc0尚未完成，Matrix MAC0。540秒遭SIGKILL、timeout=false，不是900秒预算触发；最后RSS约5.8GB。内核/cgroup日志不可用，不能认定具体原因或数值FAIL。
- 同期v2 lower-only的2GiB Java明确heap OOM，位于官方IR字符串序列化；仅真实Top elaboration和17 native inventory通过，未计low/接口PASS。二者原因不混同。
- 真实IR解释执行约50周期/30秒；采样定位巨大List快照复制。独立改为每次新建immutable ArraySeq，不缓存跨cycle、不改顺序/异常/算术。实际Scheduler mutation/重复/异常和2000输出Treadle差分通过；局部快照基准约5倍，不能当完整Host性能。
- 现只有独占session69954运行（900秒/6GiB/1CPU），所有其他重JVM已终态。硬件v1/真实输入/高低IR哈希须同96247，仅执行器快照表示改变；不含synthetic ACK，无数值PASS。

## 并行runtime链
- v2分离runtime服务安装能力与Qwen2数值策略：原L3隔离控制至pc15、completed15、207 metadata读、14 owner；缺真实postnorm receipt按Protocol7拒绝，未伪造receipt。
- 原Commands+Guard+Prefix真实connectPorts六模块控制测试实际产生Norm physical tag0及scalar/vector lease，localFault0；仍不是22op/数值通过。
- 实际Top仅加一处安装能力参数，未改资源、接口、真实owner或production故障时序；官方lower受上述内存限制未完成。
- enableChunk32=false仍选择真实原ExecuteOwnerV8，Coordinator支持tokens16/128，M128为每头两个64行chunk，不是循环M1。这只是源路径结构证据，不是32lane候选或数值PASS。

## 范围与阻塞
五块M128完整数值仍0/5，4096 MAC不缩减，无完整RTL数值PASS或完整block利用率实测。原head4 underflow FAIL不放松；35B真实权重访问与MoE同分契约阻塞未绕过。先前审查拒绝的源码/原始日志继续仅本地保留，本次仅允许最小摘要和hash。
