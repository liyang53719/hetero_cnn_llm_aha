# TEMP：原完整 FIFO 的模型仿真优化候选

只为原 Chisel 五块128-token数值回归准备仿真后端；不改原硬件/RTL，不读取参考值充当DUT。原depth2、4096个32bit data/entry和37bit metadata保持，变换为17个同容量Memory。

## 当前真实状态
6个源码均已有类型证据；最新2源生成6类。原24边测试尚无通过：先遇严格序列hash差异（仅末尾LF，经独审），修正exact完整SHA后又遇34个head/tail声明可见性错误。最新代码只将memory默认端口连接移至原head/tail声明后、原条件写之前，保持优先级。官方formcheck准备门尚未执行；之后仍须原同容量24边、invalid输出、reset写、满pop/push、整payload下游preedge采样对照。没有等价/加速或完整数值PASS。

保留全部FAIL；24边是定向覆盖，不是状态×事件穷举。六源码原字节，历史两种lowering用小helper精确重建供复现原失败，禁止作为宽松接受分支。具体身份和角色化命令见JSON，不包含class/IR/工具/权重。

## 主线与统一后继
继续原始Chisel五profile同4096MAC完整M128数值，然后冻结同源/输入/参考并生成同RTL回放；当前仍0/5完整RTL。用户已选统一32lane II1候选：32Add+32Mul+32RNE、真实多在途issue/retire/tag/credit、独立exact流水Div，旧DivSqrt的sqrt资源不能默删。Qwen2原FP32中间值不能压成Qwen3.5 BF16，跨tile缓存数据至少17B/activation，metadata另计。尚未实施lane变更，旧16lane与旧RTL证据不迁移；Qualcomm只借鉴共享元素通路/本地microtile原则，不宣称复现未公开EA实现。
