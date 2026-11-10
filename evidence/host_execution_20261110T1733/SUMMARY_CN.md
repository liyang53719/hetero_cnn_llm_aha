# hetero 17:33：匹配工具取得及真实编译执行边界（INCOMPLETE）

## 工具阻塞解除
通过正常权限审查从LLVM/CIRCT官方release取得firtool-1.163.0 full-shared Linux x64包，SHA256 2a3b8a19a8884e7adf9508555346bb9107feb6aaced9ad7fdf247dbf7048a945完全匹配。安全解包后firtool/arcilator/llc版本命令均成功，LLVM24。未使用代理、变域、用户设备或重包装绕行。因此上轮“无工具链”阻塞已解除，但不能因此宣称后端合格。

## 真实新增测试
- 同一v2原Chisel现代CHIRRTL经新firtool --ir-hw完整降级29.38秒成功；没有生成Verilog。默认Arc preproc5.14秒成功却将原107个sv.assert全部丢失。小AssertOnly实际编译到LLVM并执行，enabled=1/good=0仍exit0：严格保护FAIL已实证，不接受为模型资格。
- 官方--lower-to-core完整前端28.24秒成功，preproc5.09秒保留107 verif.clocked_assert。对应小例Arc拒绝legalize verif.clocked_assert；包含终止的小例在sim.clocked_terminate条件降级失败。保持原clock/enable，没有删除保护以跑通。此路线仍INCOMPLETE。
- 同版本顺序状态/同步reset/重复高电平小例31项实际compiled IR检查通过；异步reset小例被新Arc明确拒绝。旧1.62.1精确源码实际存在异步转同步行为，不能迁移新版结论或使用async-as-sync。
- 2个原Matrix接口实例经Firtool→Arc→LLVM→llc，与真实RTL-native库显式state-slot边界适配：400 halfcycles、416800输出word逐项对照、各1次512值真实矩阵输出及completion、400次重复高不增加边沿。注意LLVM本身没有自动调用native，测试harness读写Arc extern slots并调用真实库；只证明该显式边界，不是完整17实例Host调度、4096资格或完整block数值。
- 原RMS源码索引/地址/计数256组检查通过，覆盖M1..128与H1024/2048；不产生假receipt，不算实际数值通过。

## 五块与后续
五块M128完整数值仍0/5，RTL完整数值亦未通过。Qwen2真实FP32全链尚未完成；0.8B L0保留原underflow FAIL，L3真实owner/receipt仍未完成；35B L0/L3真实冻结输入及MoE同分契约缺口未解决。固定4096资源和共同硬件定义未改变，不做profile专用elaboration。32bank并非目标全链32lane吞吐，80%/90%利用率无新增实测。
下一步必须实现并证明严格assert/fatal保留，以及17native全Host调度/异常适配，再执行完整真实输入；不能直接采用会丢保护的默认Arc路径，不重复900秒解释器慢跑，不先跑长RTL。

## 发布及临时数据
仅本摘要/hash发布。候选源码、官方工具、生成IR、rawlogs、权重和NPZ均未上传。临时清单已核，保留唯一失败证据和依赖，本轮未清理。原长作业全部终态，未重启重复Host。
