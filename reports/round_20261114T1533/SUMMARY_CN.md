# 2026-11-14 15:33 hetero：真实4096单步子链PASS，完整五块INCOMPLETE

## 实质工程及范围
- 复用已核验真实Matrix库，8独立512端点同时执行clear+last单步：BF16 a=1至8、b=2，512路FP32输出分别为2、4、…、16。150周期，各端点一次输出及一次完成；392次背压稳定检查，含hold共208896词零差异，0.84秒退出0。精确范围仅单FMA整数子链，不是Host、完整block、深归约或异常flags资格。
- 17路schema、34个typed sink/source符号和实际库pin静态逐项核验；仍缺有效Host对象/layout，不猜宽参数ABI，不冒联合完整prefill。
- 编码完成分pass诊断脚本，直接使用已保存arc-opt，不重复整链：state-lowering/inline/merge-ifs 4.78秒成功，冻结21MB、358185行IR，保留106严格回调。
- 独立CSE原9574在60.01秒超时，已将耗时定位至该pass，但不称卡死或已证工具错误。
- 诊断性略过一个优化CSE（未改变正式基线、未宣称等价）后，原16972在4.94秒exit1：RemoveI0Types将单元素array参数标量化，后续hw.array_concat仍要求array，出现i32/i1/i5/i8类型错误。保留失败证据，开始微型复现与安全pass顺序审计；无有效Host LLVM。
- before_cse SHA256 dee7807839680dcce279f9de706395339be47fa65bf4c0ef1cb7f7decaa30e2d；真实Matrix测试RESULT SHA256 4251297c3c0dbdba61be6f7089c51d2756f6717785323f89c9445a909d691861。

## 五块/阻塞/下一步
- Qwen2、0.8B L0/L3、35B L0/L3完整128原Chisel数值仍0/5；固定4096、一硬件约束不变。当前恢复候选尚非最终完整统一源码。完整RTL和完整block有效MAC利用率未测，仿真耗时不等于硬件利用率。
- L0 strict下溢FAIL保持；35B真实权重、冻结数值契约及准入阻塞保持。旧37765终态UNKNOWN，不重启、不继承丢失50行PASS。
- 下一：最小复现单元素array降型错误并评估保语义转换，解决CSE成本；之后接真实17和ACK驱动，不删除严格条件或预装参考。
- 本轮开始核main676ed0a658adfdc83d392949faaaa152a8b07c46，CI43605939675成功（仅payload guard）。本地陈旧HEAD54776eab仍干净，未覆盖远端。
- 临时文件清单已检查，源码、库、输入、IR和失败证据均保留，清理0。没有上传权重/NPZ/IR/检查点或被拒源码，仅发布允许摘要和中文计划。
