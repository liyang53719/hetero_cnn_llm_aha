# 2026-11-14 04:33 hetero：INCOMPLETE/有界执行FAIL

五块128 token完整原Chisel数值仍0/5；统一4096 Matrix MAC定义不变，完整RTL和完整block有效MAC利用率未测。

## 当前Host真实结果
从已验cycle11831完整包恢复的唯一新session76291以第二行ACK为有界目标，触发既定110秒TimeoutError后exit1；未达目标、未生成新完整包，未完成fresh-process比较。没有扩大预算重试，也没有重复旧29364。首行6144B已验保底包SHA08e35d53b2253e73048c72dd9793b98f73e0b3851b41a857424dc5bd0353356d保持不变。
本轮控制缺口是runner仅达到目标后保存，导致超时前状态未持久化；不能将尚未保存的进展冒充可恢复。下一修复须在预算前安全排空/保存，保真实Host、17 native、AXI、控制完整状态及新source身份；未验证前为TEMP。

## 实际数值诊断
L0 head0/chunk0 phase6故障源语义确认：dot和pair输入均normal，衰减差-79.914093处于原Legacy exp合法域，乘积才tiny且inexact。整数24×24乘积124971864098300、右移26及RNE余数复核得到0x801c6a52/UF|NX。n16→gradual=false→Bank policy0→UF fatal与参考一致；不是遮罩、转置、BF16格式化或参考bug。
保持当前精度/次序/严格UF，输入必失败；FTZ、重排、夹到80或放宽UF均改变契约，未实施。历史strict head4 FAIL保留；当前新故障也不能冒历史同刺激重现。无独立Vector已编译小库，未借运行Host状态冒硬件复现。

## 真实局部Scalar资格
原BlockScalarFloatPolicyV2经Chisel发射RTL/Verilator，build61072及run79419均exit0。11事务及每事务4周期返回背压保持通过；policy1 exp(-100)=0x1b、error0、flagsValid0。原Mul下溢flags3/error1，MulIeeeRne相同结果flags但error0，证明既有策略区别，未改策略。
这是局部RTL模块验证，不是完整Host、MoE或五块数值通过；共享adapter仅源码审计，不冒联合lease/路由测试。

## 维护
基线main3032170950e384321363ceda21770a650867834c，CI43552327591 success仅payload守卫。旧29364Unknown不重启；35B权重/冻结Torch运行闭包与MoE同分契约仍阻塞。工作树clean、临时清单已核，清理0；所有唯一证据和原失败日志保留，仅发布允许摘要/中文计划。

已补本地periodic候选控制源码：每1000周期停止新AR后排空，核实际ACK参考并保存完整包/receipt；90秒提前收尾，110秒硬界保留较早已保存段。仅py_compile通过，未实际执行或fresh-process验证，明确TEMP，不作为修复完成或恢复PASS。新读请求背压是仿真驱动节流，不改变硬件，但仍需同刺激连续/恢复差分验证。
