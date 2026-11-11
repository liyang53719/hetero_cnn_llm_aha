# 14:33 统一IR与真实native恢复

五块完整128token原Chisel数值仍0/5；最终同刺激RTL未通过，80/90%完整block有效MAC利用率未实测。原L0 head4 FAIL保持，旧未知Qwen2/L3 Host未重启，不继承丢失证据PASS。

## 同一4096模型IR
复用1333新编译860classes，逐hash复核后仅编译小emitter，一次固定LegacyV0、retainedMatrix=true、matrixColumns256、weightReadBeats16、pipelined=true生成Host，不逐profile重elaboration。原73410 exit0。
新CHIRRTL95500001B SHA b9f6f07fa866c09addc0c75eca2335a0a11109f3b5aaec405664867723ba1b75，18.08秒；firtool --ir-hw生成39752238B HW IR，75.34秒，SHA87e42450afc2776a9eb9e769a5591bc828f675aa2a48eff054bf0049eeb32052。本轮独立重算得到该hash，不据历史hash继承执行资格。没有生成Host SV或执行Host。
实际1049模块、17外部实例=8Matrix+8ICG+1DMA，端口库存记录。105源断言逐模块/源行多重集合对应105 error/fatal，5库存正负测通过。仅静态身份，没有动态fatal注入；历史107差异仍缺原完整证据。

## 真实native小库
新ICG库SHA4a6171d32fbf3af0d3a32b320571b58b296224f5e339d34e2c7adfded588e6e7，256次真实RTL direct-vs-CABI观察通过。新iDMA库SHAad724c9068fc7eb4125cbe7174b81096467801005f4d31f72be17275a964628c，8640词比较通过，覆盖接收请求、AXI停顿和reset，不声称传输完成。
33项ABI/clock/reset/finalization检查通过。Bridge补initializationComplete，仅首次eval完成才final；DUT未改。首次负测预期错误：低电平eval已记录low，下一rise合法，修正测试并保留失败记录，未放宽ABI。每作业单线程≤2GiB，无Matrix或Host启动。此范围不是17实际互连或完整数值/算术fatal资格。

## 输入链边界
b048包没有目标hidden生成器/BINDING/original_prep_reference.py，run.py仅外引丢失payload；Treadle prepare失败不等于hidden生成。没有重复排除候选或换seed冒恢复。
本轮原L0 17命令/219 descriptors及51个tensor根地址、原L3 22命令/261 descriptors及65个根的dtype/维度/静态生产链核验：补原input后无先读未产张量。当前仍仅缺原input，L0 rank3 scratch为26869760B；内部访问与L3虚拟score/prob均无运行验证，不能据静态布局冒控制或数值PASS。35B完整真实权重缺口不变。

## 运行纪律
开工main68e6697f，1133–1333实体仍在，工作树干净，约9GiB内存/57GiB磁盘。临时清单保留，清理0项；未上传权重/输出/被拒源码日志，仅允许摘要/hash。32lane共享Vector方案没有实现通过，不缩4096资源。继续恢复运行闭包与严格式17联合，再完整模型数值，最后同刺激RTL。

## 匹配编译IR工具恢复
已从精确官方CIRCT firtool-1.163.0 release确认143163743B包及digest，与远端历史摘要一致；唯一74216正常官方URL下载exit0/12.49秒，SHA2a3b8a19a8884e7adf9508555346bb9107feb6aaced9ad7fdf247dbf7048a945匹配后安全解包8420成员733336968B。firtool/arcilator/llc版本查询均exit0，1.163.0/LLVM24，新binary逐SHA保存。
未运行Arc转换、Host或安装系统。strict callback/17边沿调度桥完整原实现仍缺，不能采用默认丢断言的转换冒严格执行资格。工具恢复不是模型执行PASS。

## Qwen2剩余参考的当前状态
复用1333前10阶段和1133真实权重，唯一原20819受900秒wall/890秒CPU/2GiB限额执行剩余11阶段，未重复前缀或启动替代作业。已新完成精确QK157.35秒、softmax11.63秒、PV131.34秒，以及输出投影、残差、第二RMS、gate/up，已完成阶段hash逐项匹配保存身份。写摘要时仍在SiLU阶段，后缀及当前完整21阶段资格INCOMPLETE，等待原身份终态，不推断成功或停止。
独立受限BF16乘数/FP32累加器数学审计84804例通过：TwoSum残差、FMA值与flags对整数oracle/Fraction一致，RNE/gradual前提明确。这是数学样本和分情况证明，不是全输出形式证明、格式转换flags或硬件资格。4Dense flags adapter仅准备未运行，不迁移丢失的1033全矩阵审计PASS。
