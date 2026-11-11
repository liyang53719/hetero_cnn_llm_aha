# 19:33 实际数值异常边界与AXI驱动修复

五块128 token完整原Chisel数值仍0/5；最终同刺激RTL未通过；固定4096完整block有效MAC80/90%未实测。原L0 head4 FAIL保持。旧Qwen2/L3终态未知的完整profile并发边界不变，本轮不启动完整profile。

## DONE：实际AXI响应器修复
修复原响应器只支持64B对齐的缺口：size0–6、非对齐首beat有效byte lanes、ID/RLAST与反压保持、WSTRB精确逐字节覆盖、显式pre-edge offered握手、4KiB/总线宽度/非法LAST拒绝。5项driver测试通过，读写各448种宽度/lane组合、每例3beat。仅transport单元范围，不替代算术或完整硬件资格。新axi.py SHAb011e9a18131b5ba18902f103c9f4638c6f3761bb8601fa698f315b4bb68ed79，未重建无变native库。

## 真实同4096 Host数值异常：有拒绝证据，预期status测试FAIL
新独立synthetic首RMS身份，只允许pc0/issuedJobs≤1，不读真实模型权重或参考中间值，不允许写回/第二op；使用合法M128×1536 FP32首op metadata，x首FP32为+Inf、其余0、gamma1。Host envelope虽保留原21command字段，执行严限首op与20000周期/60秒，不是完整profile或旧刺激恢复。
原21147明确exit1：172周期、12次真实R握手、读取synthetic x首64B，原Host返回Protocol7/resetRequired1，completed0/pc0、无任何写，测试原期待Numerical8因此FAIL保留。
静态追踪原Guard137–140遇globalFault可把owner状态升级Protocol，Top156接owner.resetRequired；这是原路径解释，内部Numerical8未直接观察，不能冒其已实测或为了预期去改策略。
一次有限全0对照77564 exit0，204总周期/200活动，metadata相同，仅synthetic首FP32不同，12次R握手、job1、无结果/无resetRequired/无写。证明该窗口内非finite关联拒绝，不证明完整RMS或完整模型正确。没有strict exit86触发、没有内部state修改或预装参考。原预期8的FAIL不翻为PASS。

## Qwen2程序语义静态核对
21阶段输入/输出、先生产后消费与alias、FP32七权重存储、LegacyV0、RoPE半维配对及cos/sin偏移、QK16lane归约和一次1/√128缩放、causal softmax/PV顺序与独立参考源码核对，未发现已证实新算术差异；静态一致不替代执行或全Matrix flags。
BINDING未显式version的初始疑点经交叉核实：1833 driver原本已补version=1，现映射与STATIC_WIRING_RESULT完全一致，不是既存启动错误。本轮补闭包显式字段校验，不把检查当硬件修复。真实FP32完整新布局未launch。

## ONGOING / TODO / 阻塞
继续推进原完整执行链需解决未知旧任务并发限制；当前新Qwen2完整FP32输入/命令/descriptor/响应器在，尚无完整运行数值。0.8B两层仍缺原hidden，L3原身份亦缺；35B两层仍缺完整真实payload且CDN拒绝未重试，不重复候选或换路。严格fatal实际触发及活跃完整时序仍未获得资格。
开工main e26c1ec1及同head CI43080117380成功，仅payload guard。工作树干净、约9.1GiB/56GiB可用，关键库和binding逐hash复核；临时清单检查，既有数据清理0。无候选源码/rawlog/权重/输出发布，仅允许摘要及hash。保持同libhost/17native定义，不按profile重elaboration，不缩4096。
