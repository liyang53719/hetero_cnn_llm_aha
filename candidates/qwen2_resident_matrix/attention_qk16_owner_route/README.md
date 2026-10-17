# 原始 owner 的16-key QK DDR gather候选

## 已完成 / 进行中
- 在冻结的单key真实owner路由上新增独立默认关闭 enablePackedQk16Keys 参数；不修改已发布原件。
- 源码实现：每depth先读一次已有Q local槽到av，然后逐个匹配DDR响应收集最多16个K包到已有denseWeights[256]，再发一条Matrix step；共8条，最后才emit。
- 最终FIFO头一直保留；每key从value(lane,16*selectedKey+lane)取16项到已有acc，按原顺序16次Add、一次Mul和score写。最后active key写入后才ACK结果，匹配done/completion后才推进组base。
- 源/冷行为测试及独立审查已完成：12+12项通过；尚未编译/展开/数值执行。

## 物理资源与租期
仅复用原Qwen2ContinuousBlock已经声明的denseWeights[256] FP32寄存器（1024B）、av[16]和acc[16]。没有新payload tile、SRAM、Matrix阵列或FIFO；现有packet是唯一DDR返回包。新增gather/selected各4bit，共8控制bit；前一版本owner38+client53=91bit，此版共99bit。状态枚举增加2项，原有7bit仍足够。count由稳定token/base组合得到5bit，不加寄存器。调试事件列表不属于RTL资源。
整个packedOwned租期排除原Dense清零状态denseWindowGot和Dense owner端口；不能与Dense并发。每depth所有active列均须经匹配成功ACK后覆盖；inactive尾列在Matrix入口显式选0，不读取旧denseWeights，因此不需要在组中全向量清零。默认关闭走原路径。

## 接受 / 故障 / 退休
保持原DDR request/tag、local和Scalar已接受债务以及错误排空规则。发生当前错误禁止新gather/score写；后续key选择检查finite。之前已写score不能回滚，后续故障使owner失败且禁止后续正常发布。结果槽不能因某个非末key完成而释放。base在组内稳定；4bit index+1采用扩位避免15回绕。原始多步FMA非有限值不能恢复有限，因此最终选中值检查保留故障发现但延迟时间不同；本冷测试不建立数值或RTL等价。

## 精确请求数，非吞吐结论
M128/12头：99,072因果key，6,912组，55,296 Matrix steps；每step实际4096 cells，共226,492,416 physical FMAs。K仍为792,576个64B DDR读（50,724,864B），Q local读55,296次；score仍99,072次，顺序FP32 fold Add仍1,585,152次。首次Q写入及其它阶段流量未包含在这些QK计数中。
此版仅减少QK issue并聚合K gather；大量串行DDR读/Scalar fold仍在，不能据此宣称80%/90%全周期利用率或全prefill完成。raw scratch、PV6和共享bank整体调度另待后续工程。

## 冷测试
从仓库根执行 python -m unittest candidates.qwen2_resident_matrix.attention_qk16_owner_route.test_route -v，再以python -O运行同一模块。只运行stdlib控制/源检查，不编译Scala、不做浮点数值任务。
