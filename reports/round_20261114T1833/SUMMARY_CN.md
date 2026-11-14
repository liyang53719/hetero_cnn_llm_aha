# 2026-11-14 18:33 hetero：指选诊断与驱动修复，完整数值INCOMPLETE

## 实际工作
- 先核原76519确切120秒timeout、工作树干净、现场无遗留llc，复核冻结LLVM ba17547d2f5ad300bb2e934bf3f12f26f66ee0c12090c0bc89f100adb251fbab。
- 新11915保持同一LLVM，仅使用官方-fast-isel=false避免快速指选回退路径，150秒仍timeout，host.o为空。此负结果说明该策略在当前预算未解决编译，不称有效加速，不重复同命令，不把未知旧Host重启。
- 并行实测默认指选与-fast-isel=false：真实微型Arc source每eval重读、strict clock/reset正例和异常abort一致；17路宽ABI逐字节正例及stage/source失败abort一致。范围仅微型指选/ABI资格，不冒完整Host等价。
- 新驱动修复：把准入、ABI、native返回码及输出检查全部替换为显式fail-closed，不依赖Python assert；补ctypes签名、85端口边界/17schema、完整pin与编译receipt及对象路径绑定。原驱动保留。
- python -O下三项实际负例（坏pin、缺/空对象、超时编译凭据）均在加载native之前拒绝。未链接或执行Host，未预装输出。此修复是实际待运行驱动，不是完整prefill通过。

## 结果和边界
- 新layout仍1607504字节/85端口，shared17七项依赖pin核验通过，106严格site及43个native调用约束不变。
- Qwen2、0.8B L0/L3、35B L0/L3完整128原Chisel数值仍0/5。固定4096与统一硬件约束不变；新恢复候选还需完整等价/准入。完整RTL、完整block有效MAC利用率未测。
- L0 strict下溢FAIL保持，35B真实权重/契约/准入仍阻塞。旧37765终态UNKNOWN，未重启、不继承丢失50行PASS。
- 下一：对已定位大eval的机器指选成本作可观测诊断，评估合理较长有界编译预算或保语义函数处理，不继续盲目短超时循环；有效对象与当前receipt产生后才链接新有限reset/idle。
- 起始远端cf9fe867223b36d55743c283bb031bd55347a8d3，CI43622661410成功（仅payload guard）。本地旧HEAD54776eab干净，不覆盖远端。
- 临时文件清单已核，源码、IR、失败日志及测试证据仍保留，清理0。仅允许摘要/计划发布，没有权重/NPZ/IR/检查点或被拒源码上传。
