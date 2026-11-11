# 07:33 执行闭包重建：完整数值 INCOMPLETE

## 身份与范围
main ec7cc3d0和CI42973846583 success已核，仅提交载荷检查。上轮恢复源码仍在，约9.3GiB可用内存和57GiB磁盘；204项上轮文件清单已记录。本轮没有重启旧L3/Qwen2 Host、恢复未知会话、删除证据或迁移丢失PASS。最新checkpoint仍缺失，旧executor终态仍不可确认。

## 真实参数字节链实际重建
重新使用已逐hash验证的原真实权重和原emitter：L0的14原张量合并/转置为13个运行参数段，共43,111,008字节；L3全部11参数段36,705,280字节，保存原只读地址/shape/hash映射。L0仍缺原hidden/history/state，L3仍缺原hidden/trig；没有捏造输入或预装中间结果。
L0 gated_gamma原为F32[128]，初次错误BF16扩展被目标长度检查拒绝，修正为原512字节后重跑成功；未运行Host。两层各24步明确synthetic小向量×真实系数的独立Fraction RNE索引校验通过，3项单测覆盖转置、shape拒绝及underflow flags3。这不是M128、完整Dense或Chisel数值通过。原14条参考外依赖中5条找到同SHA本地源码并建立路径重映射。

## native包装层实际修复与边界
恢复旧Matrix wrapper缺未eval时析构保护。新增独立initializationComplete，只在成功eval后置位，drive不清除此标志。真实C++编译wrapper配明确测试替身，旧源码未eval析构返回-5，新候选8次生命周期/ABI长度/padding/seed拒绝/低到高及重复高保护通过。没有计算矩阵，不冒硬件或历史SIGSEGV重现。
新增参数化ICG重建入口，先验证真实RTL SHA、Verilator5.032/runtime及新输出路径，再生成argv，缺源负测明确拒绝。真实17native仍缺原generated RTL/archive、iDMA依赖filelist和工具运行库；现有tc_clk仅export fixture，不能替代冻结上游来源。生产Host未接入候选。

## 五块与计划
五块完整M128仍0/5；本轮均为重新验证的源码/参数/包装层或独立参考，不能冒完整原Chisel或最终RTL通过。固定4096不缩减，原FP32/BF16顺序和L0下溢FAIL要求不变，完整block利用率无实测。
DONE：真实参数桥重建、独立小参考测试、native入口与保护候选。TODO：补齐经验证的共享源码/工具和native闭包、重建真实输入并重测；旧执行处理决定明确前不重复启动Host。全部生成权重、源码、测试日志本地保留，只发布允许摘要与hash。

## Qwen2参考源码精确恢复与新测试
从此前允许且已保存的源码包精确恢复全部4项DEPENDENCY_PINS，包括candidate.py、legacy_reference.py、operators.py和原flags说明，SHA均与原pin一致。新跑2600个标量FMA/flags案例（含600边界）对独立Fraction RNE，4个非法输入拒绝；另三种合成Dense形状共4112输出/65792个递增K-FMA，与整数oracle一致，8个rational原语一致。
这些不是实际训练张量阶段。含128行的小形状也只是合成算术测试，不是完整128token block。旧完整21-op仍缺原输入/权重和中间张量，要求完整复现的入口exit2；四项源码pin齐全不等于数值主链已恢复。没有迁移旧full_m128结果。
首版合成参考测试曾把仅支持BF16乘数的oracle用于FP32最小subnormal，接口正确拒绝；保留失败脚本，改用独立Fraction原语期望后重跑通过，没有修改恢复candidate的数学。

## 共享Host源码候选与实际类编译
已重新校验155项旧源码基底hash，局部补齐legacy runtime安装能力与数值策略分离候选。没有直接删除dtype/边界保护；静态差分与门控检查6项通过，保留固定物理定义及其他profile范围。但新能力分支会新增准入，未取得动态控制或数值资格，不能冒原统一五块通过。
候选Commands与Top均未匹配原冻结SHA，因此这是新候选，不是旧执行闭包精确恢复，不沿用旧硬件/RTL hash。完整155源类编译首次43.35秒FAIL（诊断入口缺firrtl2依赖）；保留原日志。随后仅排除非硬件DiagnoseOriginalHostMoePhaseV5诊断入口，154核心源99.62秒exit0，生成857个class，没有排除硬件Module。这仅Scala类型/类编译，没有elaboration、Host运行或数值通过。原session84156已明确exit0，未重复启动。
