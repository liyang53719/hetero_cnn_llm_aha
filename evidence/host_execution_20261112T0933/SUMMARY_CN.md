# 09:33 原Host HWIR、输入桥和实际参考执行

0833证据仍在。原79669复用5053dcbd CHIRRTL用现存firtool1.62.1 --verify-each，未关闭断言，46.09秒生成HWIR38217735B，SHA1a30b935fd8a119ba5af31fa5ce321108e36a333bba7921d2400be6d547b04e9。真实层级展开8Matrix+8ICG+1iDMA；105error/105fatal/1immediate assert计数保留，非runtime strict回调资格。初审instance正则错误修正并保留。arcilator当前缺失，严格适配和native生成闭包仍待恢复。

三个native wrapper候选修复never-eval或首次eval异常时不调用final，正常初始化后保持final；原ABI/clock/reset与算术不变。4项C++ Probe生命周期测试通过，非真实RTL/17handle执行。实际Verilator runtime/生成headers/archive仍缺，不能声称闭包完成。

0.8B L0/L3真实14/11源张量逐内容hash重新校验，实际物化16/13只读段，原17/219与22/261程序；两hidden、冷状态、trig匹配完整pin。8项准入/边界/padding/禁止写入/损坏/缺输入/中间预载测试通过，仅字节桥。原generator来源包未恢复不冒本轮来源审计，L0原32B bias不改、padding新映射明确。

Qwen2原27005实际M128独立参考，修复BF16转换前非finite拒绝，8类receipt负例和3个NaN/Inf反例通过。快照已完成0–11共12阶段，含QK114.62秒、softmax9.71秒，正在PV。CPU300秒/2GiB上限，已完成阶段原子receipt可续；未完成阶段无checkpoint。参考值不是完整flags/Chisel数值，未继承丢失PASS。

五块完整M128原Chisel仍0/5、最终同刺激RTL未过、固定4096完整block有效MAC80/90%未测。原head4 FAIL保留，未知旧Host不重启，35B限制不绕过。下一步沿原参考身份收终态并补严格Arc/native执行闭包，五块同硬件不变。

开工main b0225af9，CI43185471106 success仅Git数据门禁；工作树干净，临时清单保存、清理0。仅允许摘要/hash发布，原始源码/IR/权重/数据/日志不上传。
