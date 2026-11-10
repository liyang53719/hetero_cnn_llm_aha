# hetero 20:33：真实编译IR传输优化与同硬件双profile执行（INCOMPLETE）

本轮基线 main 59f10794，CI 42889893135 success，仅Git payload guard；核旧任务终态与资源后再执行，无重复长编译或硬件重elaboration。

## 实际编码与限定验证
将已验证的字节拷贝接入真实Host适配器，仅替换out_acc_o的512 uint32传输；其他输出保持原pack。独立AST审查仅settle函数改变，17个真实native handle、pre-edge双向快照、ready依赖、clock/reset与严格fatal库均未改。400半周期、1667200个Matrix word同刺激对照一致；完整Host reset/idle和首low/rise/repeated-high定向测试通过。这些是边界与启动PASS，不是完整数值PASS。
另将driver stderr改唯一日志文件，消除PIPE日志背压；不改变DUT数值、输入或时序契约。候选源码与原失败日志保留本地。

## Qwen2实际M128
同原真实FP32输入、21命令及固定4096硬件的唯一120秒运行终态：39899帧，pc0、issuedJobs1、completed0、DMA315、pipelineIssues0、resetRequired0、无FINAL；120.003秒预算终止，INCOMPLETE，无独立参考比较。实际driver最后13184 active cycles、96写ACK/6144bytes，尚未完成首Norm。相比旧120秒24731帧约1.61倍，但同时包含copy与stderr两因素，不单独归因copy，也不代表硬件利用率。

## 五块约束和下一步
五块M128完整数值仍0/5，最终RTL未通过，80%/90%完整block利用率无实测。0.8B L0原underflow FAIL保留；35B L0/L3真实冻结输入仍缺，MoE同分契约未改。候选共用同一Hostlib与state、物理接口、17native及4096资源；不是新32-lane硬件达标。下一步降低真实适配器逐帧开销并继续原完整执行链，不预装参考或制造receipt，不以M1循环替chunk。

## 发布和清理
仅发布允许的中文摘要与hash，不上传候选代码、原始日志、IR/native工具或权重。临时清单保留，无清理，唯一失败和运行证据不删除。

## 0.8B L3同硬件真实入口新增结果
重新验证真实M128的22命令/261描述符、15 readonly/20 DDR观察输入hash，虚拟score/prob未预装。原driver支持动态命令与profile2，无须修改Qwen2专用尺寸判断。Qwen2终态后运行独立30秒：9425帧，pc0/jobs1/DMA211、completed0/pipelineIssues0/resetRequired0，无FINAL，预算终态INCOMPLETE。实际共用同一个compiled Host库及state/schema/17native，只改runtime输入，未重elaboration或伪造receipt。旧typed/prefix失败未当成本后端执行结果；本次也仅证明真实输入进入首Norm，不是完整数值通过。
