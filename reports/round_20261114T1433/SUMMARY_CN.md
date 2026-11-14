# 2026-11-14 14:33 hetero：真实17闭包资格，完整数值 INCOMPLETE

## 实际代码和测试
- Matrix保留上轮150对象，仅增量make 47.51s/link 8.36s，均exit0，未重新生成；八独立真实512-MAC实例的reset、接口、生命周期测试通过。合计4096，未执行算术作业。test-only finish注入不是RTL fatal资格。
- 新共享接线库真实链接8 Matrix、8 ICG和1 iDMA。五独立进程通过：12周期交替gate、每个Matrix实际8个升/降沿；高相pending不污染冻结快照；4类错误永久poison并禁止读取旧输出。仅注册、时钟、失效语义资格，不是Host或prefill通过。
- 新输入驱动将原Qwen2地址读和首RMS写回捕获连接；仅实际B OKAY握手提交后的字节可读回，中间输出不预装。28合成集成测试通过，未运行Host。
- Arc分阶段诊断：preproc 7.87s、arc-conv 13.43s、arc-opt 22.65s退出0。state-lowering在90.02s超时，最后日志为arc-merge-ifs后CSE；不能证明卡死，未取得Host LLVM。106严格条件回调保留，未通过删除断言避错。

## 精确证据
- Matrix库 SHA256 7fdea3242bcc97356528bc86ae13ee07b5fde8797dad1c77cd64d9ff3bda0668。
- shared17库 SHA256 74ee572fbaa7160dc78d1f05f1b6ac621bba86fba64a32e32350e611a37e238c。
- shared17 RESULT SHA256 44a1762184ef553c2f67855d56787b72cb273a2156a786a0823adc481f67fc63。
- Matrix构建6670、接口56976、Arc阶段50132/53563已终态。原37765仍UNKNOWN，未重启、不继承历史50行PASS。
- 核查前远端main 290cb6dfda300b40b02682205929c85b519a8ef9，CI 43601465059成功，仅payload guard。

## 五块、资源及后续
- Qwen2、0.8B L0/L3、35B L0/L3完整128原Chisel数值仍0/5。单一4096定义不变；32-lane候选不冒实现通过。完整RTL与完整block MAC利用率均未测。
- L0原strict下溢FAIL保留；35B真实权重、契约及准入仍阻塞。新Host候选8个路由相关断言依赖差异尚不冒完整等价。
- 下一步从已定位CSE阶段诊断IR规模和官方pass行为，接已验证真实17与真实输入驱动；不重复未知旧Host或重做完整生成。
- 本地git仍54776eab且干净，未拿陈旧树覆盖远端。临时清单已检查，原对象、源、库、测试、IR、日志均被依赖或属证据，清理0。未上传权重、NPZ、IR、检查点或被拒源码，仅允许摘要和计划。
