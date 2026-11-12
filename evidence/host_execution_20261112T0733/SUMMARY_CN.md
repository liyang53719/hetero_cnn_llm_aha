# 07:33 Qwen2参考继续、0.8B真实输入消费核验及native缺口

复用RMS/Q，本轮实际新增K/V完整投影、Q/K/V bias、Q/K RoPE七阶段，M128。原44585 exit0/6.40秒，92062 exit0/3.81秒；K/V逐FMA舍入证书残差均0，各2个完整K输出由原Fraction差分；bias/RoPE全量Fraction。原freeze_trig及cos/sin pin恢复，无Torch替代。仅参考值，flags未完整审计，非完整block/Chisel/RTL。

0.8B L0 16只读段→17命令/219记录、L3 13段→22/261独立解码核验，pins、TypedTensor地址/rank/dims/stride、主a/b生产者顺序与最终output声明通过。8项测试含缺hidden、预载中间值、坏root/地址、缺生产者、重复输入、截断程序拒绝。仅静态主依赖与字节消费，非Host/owner/scratch执行；L0新padding身份不变，原head4 underflow FAIL保留。

native73源SHA匹配，5个相关当前Chisel源已pin。Matrix CABI37in/521out，末word仅protocol_error而无raw算术flags；Qwen2独立finite/scalar检查仍存在。源码8×512和真实ICG/active-low reset确认不冒当前17实例elaboration验证。旧链接20路径全缺，三wrapper缺never-eval finalization保护，共享17桥/schema/库与生成闭包仍缺；未运行native。

五块完整原Chisel M128仍0/5，最终同刺激RTL未通过、4096完整block有效MAC80/90%未实测。35B两层仍缺18/15完整张量，受限下载不重试绕过。未知旧Host不重启、丢失PASS不继承。下一步补生成闭包、修复生命周期后核严格异常与真实执行，而非把静态或参考通过冒全链。

开工main3fdd1261，原CI43170045154 success仅Git数据门禁。本地工作树干净，约9.1GiB可用内存，临时清单保留、清理0。仅发布允许摘要/hash，不上传源码/权重/原始日志/生成数据。

Host本轮仅只读确认0633结果、0433原Top/Emit源码及firtool路径；尚未完成860class与工具hash重验及最小emitter准备。明确未启动elaboration、无在途session，无新IR或编译PASS。原0633类型检查终态保持已验证，不重复未知完整Host。
