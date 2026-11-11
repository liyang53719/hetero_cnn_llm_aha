# 09:33 真实参考及原执行依赖恢复

状态：五块完整M128原Chisel数值仍0/5，完整RTL与80/90%完整block利用率均未验证。原L0 head4下溢FAIL保留。旧Qwen2/L3任务终态仍未知，未重启，待用户决定。

## DONE：本轮真实工作与精确范围
- Qwen2：本轮完成剩余参考阶段，联合08:33新算前缀构成真实M128完整21-op独立参考候选。最终y SHA cbda6ba00853708fab397dadafbf731b29a8b134f6d9f6541e6b7a5fce6f6cb5。每阶段重新计算后才与旧身份hash比较，没有读取旧输出注入。QK受限BF16乘数/FP32累加proof与原16lane顺序另经交叉审，PV12681216有效FMA flags只有0/1。并不声称全算子异常flags或全部输出Fraction穷举，更不是Chisel/RTL通过。
- 0.8B L3：重新生成16384B trig，SHA1156df1551f166fe3f816547b6a15eac1c2ff994683138d5276d2f64c68aa9bb严格匹配保存的官方Torch capture pin，损坏/截断拒绝。本轮由NumPy候选生成并以完整hash准入，不声称重新执行Torch。现有新hidden与原输入不同，不能继承旧L3测试PASS。
- iDMA：原artifact恢复927源文件并校验manifest，真实上游RTL编译新native库。直接RTL与CABI的8640word一致，覆盖request接受、AXI停顿与reset；8未eval析构、8真实reset/重复高及非法ABI输入负测通过。没有传输完成或注入RTL fatal资格声明。ICG前轮已重建，Matrix与17联合闭包仍未完成。
- 断言：本次CHIRRTL105条与HW IR105 error/fatal按模块、源文件、行及重复次数逐项匹配，4库存正负测通过。可访问155份基底源码assert行未变，153文件逐字一致；Top/Commands变化限已记录安装能力参数与准入位置。历史107的原IR/逐项清单缺失，历史等价INCOMPLETE；未凭数量补造或删断言。

## TODO / 阻塞
先恢复Matrix及17真实native联合绑定并验证严格clock/reset/fatal，再恢复原Chisel完整数值链。0.8B已恢复真实参数与L3 trig，但旧hidden/旧执行证据未恢复；35B完整18/15张量及收据缺失，未绕先前下载拒绝。新候选IR仍为同一4096结构，但不继承旧源码/RTL身份。32lane每周期共享Vector、流水Div与跨tile缓存方案未实现通过。

## 运行、提交与清理
本轮开始远端main72e9994b，CI42988541926 completed/success，仅git-payload guard。旧本地checkout54776eab工作树干净，重建输出在独立目录。新增执行均与未知旧Host分开，无重复昂贵Host。临时文件已登记，不删除唯一证据/运行依赖，本轮清理0项。只发布允许的中文摘要及哈希，不上传候选源码、日志、权重或生成数据。
