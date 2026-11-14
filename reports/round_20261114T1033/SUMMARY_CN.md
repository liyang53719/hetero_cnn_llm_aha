# 2026-11-14 10:33 恢复工程（INCOMPLETE，断言比较差异待验证）
## 实际新候选Host结构工作
已保存70735 typecheck exit0收据，当前poll Unknown不能覆盖收据也不能推定旧37765终态。新四源与base860类、overlay32类及jar依赖核验后复用，原86200 emit15.229秒exit0。FIR 6cb560a4be5003190cfd2eea3923ece005984cff443a023a2958865e220a74d8。
现有CIRCT1.62兼容结构lower原51792 exit0/55.773秒，HWIR 9e8539b2cf1f3d4bc5cac23c1d43648cad6c7412481cf8b744534da9b4daa811，不冒失踪1.163 Arc或执行库资格。
全部模块公共接口、17native实例和105断言数量保持；断言语义比较不通过：8项held-job谓词经choose受qkNormPolicy1→0候选路由影响，不是纯SSA重编号。保留差异，不删改断言，不声称语义等同，也不据此断定assert已失效。emit元数据误沿用基底sha已要求明确拆分baseline/current并保原副本。
未启动新Host数值、未知37765未重启、未继承旧50行。
## 重建独立数值参考
Qwen2真实输入M128×1536首RMS完整Fraction参考重新计算7.333秒、786944 scalar ops，786432字节SHA ccf1e6c065c6bc4e90458194aeda7475149451ac73479a6781d2fd638bf631df。原x/gamma raw pins及源码冻结，不供DUT中间值。
L3 M128×1024 input RMS按原C2与1+gamma独立Fraction重新计算，输出SHA ab1f29183a7fe678d9dcbd87cc7bc680db323bd75ec7a839ab154a2e41e7fab9；现存旧字节重新比较相同。当前新Commands源runtimeGQA policy0已读源码核验，但不是加载二进制证明，不与Q/K norm C2混淆。
两者仅完整输入归一化独立参考，不是完整block或Torch资格，更不是Host数值通过。
## MoE源码时序probe恢复
原74020编译5.624秒/CHIRRTL2.580秒exit0，八路owned/sequence→packet→accepted→acquire/retire静态核；7独立Python时序规格正负例通过。grant/revoke/busy仍合成边界，缺Verilator/iverilog没有RTL动态PASS，不冒真实allocator/adapter联合链，未改profile3/4门禁与数学。
## 五块与维护
完整五块M128原Chisel0/5，固定4096与统一硬件目标不变；完整RTL、有效MAC利用率未测。L0 strict UF FAIL、35B权重/冻结runtime和MoE契约阻塞保持。运行闭包仍缺native/新工具及可恢复包，原37765终态未知。
基线main012a605545841cdb806eba489e9f69f99cd051a9，CI43584674396 success仅payload守卫；本地git clean，可用RAM9.1GB/盘57GB。临时清单已核清理0，仅允许摘要/计划发布，不上传实现或数据。
