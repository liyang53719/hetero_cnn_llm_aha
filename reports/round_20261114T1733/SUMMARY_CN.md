# 2026-11-14 17:33 hetero：顺序累积子链PASS，Host机器码INCOMPLETE

## 实做与精确范围
- 新真实shared17测试73647退出0/2.07s：8个512-MAC端点各5次顺序FMA，step0/3清零，含正负积、0.25增量、丢弃旧累积、每5拍门控1拍和背压。各lane最终-2.5；Fraction逐步参考确认测试值均可被FP32精确表示。107520个含hold输出词零差异，170次背压稳定检查，各端点5 issue/5 retire/1 completion。仅顺序累积、清零、门控子链，不是通用舍入/完整Host/完整block资格。
- 原59033已知超时后无遗留编译进程。新44093仅45秒有界pass诊断，日志明确到HostBlockTopV4_eval的X86 DAG指令选择；不是声称卡死。
- 新69690使用官方LLVM sroa,mem2reg,early-cse及verify-each，2.42s成功。新候选eval约56.1万行缩至44.2万行。106 strict sites、17 sink、26 source调用保留；没有加入fastmath或虚假pure/readonly属性。
- 同一优化pass集的微型真实Arc机器码验证：20次eval各读取变化source并调用sink，clock/reset正例通过、原严格异常子进程-6。仅微型副作用/边沿资格，不代表全Host等价。
- 对新优化身份76519进行一次有界llc -O0，120秒仍超时，host.o为空。未链接、未运行Host，不继续重复同一命令。优化IR SHA256 ba17547d2f5ad300bb2e934bf3f12f26f66ee0c12090c0bc89f100adb251fbab。
- 顺序累积RESULT SHA256 3d4b722cda4c8407314125a0cb3b2d702a24ca6494dd93fdf81409475403bb33。

## 五块及后续
- 五块完整128原Chisel数值仍0/5（Qwen2、0.8B L0/L3、35B L0/L3），完整RTL和完整block有效MAC利用率未测。固定4096及统一硬件约束不变，局部仿真耗时不冒硬件利用率。
- L0原strict下溢FAIL、35B真实权重/契约/准入阻塞保持。旧37765终态UNKNOWN未重启，不继承丢失50行PASS。
- 下一：基于已定位X86指选瓶颈审计不同官方指选策略或保语义大函数处理，并保持当前真实17、layout和输入桥身份；对象有效后才做新的有限Host reset/idle。
- 起始main7e5bd0084733b5f975fae0fc4f8fc81e25d05201，CI43616956325成功，仅payload guard。本地陈旧HEAD54776eab干净，不覆盖远端。
- 临时清单已核，约34MB新增源/IR/诊断证据全部保留，清理0。仅允许摘要/计划发布，无权重、NPZ、生成IR或被拒源码上传。
