# 22:33 原控制位宽与参考main修复（TEMP候选，完整prefill INCOMPLETE）

现场2033/2133保持，执行闭包1733–1933仍缺，未重复整套重建。main cbce5c10、CI43302562281 success仅payload门禁；工作树干净，临时清单已核，清理0。

实质控制源码审计：原attentionPolicySlot可达0..2，第一层+1得到context1..3不溢出；第二层countPolicy普通+把matrix分支3+1截为2bit的0，漏掉4个policy槽的distinct掩码。43617真实小Chisel编译/emit exit0，实际getWidth检查policy2/context2/original2/corrected3通过。仅第二层改+&的候选完整SHA8cea5e8863e47ca14978871d23b7f80639e43ae3192c3e6c0ccf372b1c73a20f，与历史候选同hash不继承PASS。

范围精确：影响0.8B L3/profile2和35B L3/profile4的runtimeAttention QK/PV；Qwen2原FP32/profile0、L0 GDN/profile1/3不走此分支。它不是token128或4096容量溢出。原policyGet已有prefixRevisit/policyRevisit先行检查，未证明实际绕过准入或造成数值失败。真值表/alias检查为Python逻辑校验，非Host/RTL仿真。物理4096不改，但采用控制候选后必须重新冻结硬件身份并全五块回归。

实际集成参考恢复预检：2033预检原先未接入main，现候选入口取得运行锁后、输入重建/trig/计算前验证完整已有receipt。模拟后段输出损坏、receipt断档、后段shape错误均零输入重建、零算子即拒绝；冷启动正例到首次输入读取。13真实raw及候选源码准入通过，未执行真实参考或Host；原0833源码及PINS保持不变。

本轮不冒执行恢复：五块128完整原Chisel仍0/5，最终同刺激RTL与固定4096完整block有效MAC80/90%未测。原L0 head4 FAIL、35B完整权重缺失及旧未知Host不重启边界不变。环境持久性尚未解决，需要可靠执行闭包才可继续完整回归。只发布允许摘要/hash，候选源码与必要证据保留本地，不绕先前拒绝。
