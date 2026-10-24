# 隔离 strict-reference wrapper：限定软件验证摘录

此包保留原 wrapper、明确标注的协议 MOCK 控制、R2 native harness、监督入口、固定刺激以及 R1→R2 加载修复 diff 的原字节。没有复制 Fraction 模型、旧 CPP、工具闭包或 ELF。

根执行的一次 R2 单子进程自然退出0。52个请求包含44个唯一三元组，共99次真实单lane trace（52 Mul、47 Add）；46成功、5 Mul fatal、1 Add fatal。全部逐pass bits、flags、有效位和commit与独立Fraction记录相符。12个非finite前拒不调用目标算术；13组93次协议检查明确是MOCK，不是硬件或93个native案例。

原首次实际失败仍保留：dataclasses延迟导入触发缓存路径open审计，在target ELF载入及控制/数值执行前终止。R2仅在原guard前预加载两个已固定标准库模块dataclasses/fractions，并校验来源与新bytecode目录不存在。未全局允许pyc、未重编ELF、未改wrapper算术或刺激。

乘法fatal保留真实product/flags但不执行Add；Add fatal保留其真实诊断但不提交。minnormal交付而无界舍入仍tiny的样例返回UF|NX=3并正确停Mul。FENV标准sticky及controls保持，MXCSR的DE位0→1单列，不宣称整个MXCSR不变。

## 复现边界

REPRODUCTION_PINS.json提供原始源码及依赖指纹。此公开摘录不是独立可执行闭包。launch_wrapper.py仍要求原精确FROZEN_PLAN、固定CPython3.12.14、来源验证的既有ELF与seal，以及监督依赖；这些机器绑定材料未发布。不要为运行摘录而移除pin、换用旧ELF或放宽guard。

可对本包做hash/AST/内存compile静态核验。运行protocol_controls、native harness或launcher属于另外的实际执行，不由本包自动触发。源码中的通用proc/tmp和PATH常量是原监督实现，不包含私有工作目录或运行日志。

## 未获得的资格

没有执行HardFloat数值/flags或RTL仿真，没有16lane整组故障屏障、阵列、Exp/op6或完整模型集成资格。旧CPP/model不被替换。原硬件与整模集成阻断保持；CHIRRTL结构证明也不能替代数值实测。SUMMARY.json严格分列实际、前拒和MOCK范围。
