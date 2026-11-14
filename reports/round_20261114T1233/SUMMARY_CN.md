# 2026-11-14 12:33 真实执行闭包恢复（INCOMPLETE）
## 原任务与环境
main基线8bc2a1fbfc9653d11af8ab07e0e10e4ad2dacbf7，CI43590773334 success仅payload守卫。1033/1133产物和官方工具仍在，本地工作树clean、可用RAM9.3GB/盘56GB。原37765没有可确认终态，不重启；丢失50行checkpoint不继承。
## 真ICG与源依赖
原artifact恢复的927份iDMA/techcells源码逐pin验证（iDMA2e0b0fe、techcells3a3de736），使用真实tc_clk_gating非fixture。12314生成/单线程编译/修复wrapper链接exit0；34458真实接口测试exit0，验证门锁存高低拍、never-eval destroy、undriven/非法bit拒绝。test-only context finish注入后eval拒绝且read/clock保持拒绝；不是RTL fatal资格。Matrix/DMA尚未编译、实际17共享运行闭包未完成。
## 17 typed桥与共享transport
按新1033 HWIR实际17路端口重新生成LLVM24 typed→packed bytes薄桥并编译；Matrix输入122/输出2062B，ICG3/1B，DMA158/202B。全17路宽位/字节测试通过，两transport错误负例abort。新共享transport编译及4项mock边界通过，保留stage快照/fresh检查/永久poison/共享handle限制；未绑定真实全部leaf、未验证ICG→Matrix→DMA时钟，不是shared17/Host数值PASS。
## 新Arc严格转换代码
新脚本将实际17 native调用拆为sink/source边界，保留105 fatal条件和额外1 immediate assert为106 clocked terminate。默认ASSERT_VERBOSE/STOP宏为1，非默认宏不支持；原clock/enable/reset条件保持并记录错误消息映射。适配1.62→1.163语法，移除唯一空且无引用OM元数据。
初次解析在宏语法和空OM类失败，已保留候选修复轨迹；新circt-opt完整语法校验及原46101 arcilator preproc exit0。预处理结果仍106 terminate、17 sink/17 source。不声称fatal运行时诊断/边沿优先级或native固定点等价；未生成可运行完整Host。
prepare源SHA ee55348213d4cb72263ade8e308edbdb5bfbeb0367242efa29491f27f6868d76，prepared IR60aca0b57b0263e9853e4bd71574ba57fb8a1b19ad25cd54c7e53e4b496e4f37；源码与IR仅本地。
## 实际输入接入代码
统一ProfileInputs(0/1/2).read直接复用三原桥/manifest地址与raw pins，485差分读取/171拒绝测试通过。35B3/4、非法profile、写只读区、未初始化中间值均fail closed。来源表含三profile精度/元数据/hash，不代表硬件准入或完整数值。
## 五块边界
完整五块128原Chisel0/5，固定4096统一硬件目标不变；完整RTL及全block有效MAC利用率未测。Qwen2/L3首RMS仅新独立参考资格；L0 strict FAIL保持；35B完整权重/冻结runtime与MoE契约仍缺。没有新Host启动或盲目重跑前缀。
临时清单已核、清理0；保留唯一/运行证据。远端仅允许摘要/中文计划，不发布受限实现、数据或原日志。
