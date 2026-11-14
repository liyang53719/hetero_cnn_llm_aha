# 2026-11-14 22:33 hetero 进展（INCOMPLETE）
- 现场：远端基线ff20b65、CI43644168292成功，仅载荷门禁；本地源干净，旧37765未知未重启。临时清单核实，清理0。
- 实际编译修复：原始函数内BasicBlock切分，仅新增706无条件branch，所有原Instruction逐一保序、无跨函数移动，PHI更新及LLVM verifier通过。保106 strict、17 sink/26 source、原ABI。微型stack/派生指针2048、PHI2048、strict正负例和侧效应通过；finalize-isel保留5机器块而原1块。
- 原71417转换完成；新IR774c58d5bf9059ee9d8708f1c1749eb8028057b1edd77553a2e18f60cba42663。唯一95943官方llc-O0 PIC在40.006秒exit0，生成8050200B对象b964071df47ce7694d47140bfb1c73066682942e9f8adb2d7eabf5c42bcf4e8b。不是危险arc-split，未重复旧超时输入。
- 新精确身份链接真实shared17：Host库f61dfe3492a1ffac2d6d59b2b12e42dfbc137aadddbee53ebf6940958a185cea。实际4 reset+8 idle共12周期，0.03975秒；PC/issued/jobs/AXI/result/completion/resetRequired均零，组合收敛1–2次。仅reset/idle通过，无launch、数值或checkpoint资格。
- 独立提取候选：live-in/out预算的79段非聚合转换9.906秒；总指令仅+0.4%、新增caller类型3395B、最大块减半，解决此前1.92GB膨胀；未机器编译，不与上一路混称。
- 五块输入推进：L3首RMS输出桥复用原profile2/NormC2（1+gamma）参考ab1f2918…fab9，128×1024 BF16共262144B，仅B ACK后可读。16合成测试通过，未预装输出、无重elaboration，尚未接completion或实际Host。
- 五块128完整原Chisel仍0/5，固定4096；Qwen2与0.8B两层输入已恢复但完整数值未完成；35B两层缺完整权重/资格。L0 strict下溢FAIL、MoE同分待决契约不变。
- 完整RTL数值、完整block有效MAC利用率未测。编译墙钟改善不是硬件利用率提升。
- 下一：沿新对象固定身份验证活跃AXI/严格异常与全Host+17状态保存恢复，再接真实首RMS数值；不继承丢失50行PASS、不重复旧未知作业。
