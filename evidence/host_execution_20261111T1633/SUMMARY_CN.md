# 16:33 真实17路共享接口推进（INCOMPLETE）

五块128 token完整原Chisel数值仍0/5，最终同刺激RTL未通过，固定4096完整block有效MAC80/90%未实测。原L0 head4 FAIL保持；未重启终态未知旧Qwen2/L3 Host。

## DONE：真实native共享transport
新写C++ 17句柄sink/source/prepare/clock接口，复用1533 Matrix及1433 ICG/iDMA已验真实RTL库，没有重建RTL。按原端口decl顺序LSW-first逐32bit传输。两套独立真实RTL句柄400半周期比较3384000个输出/冻结快照word、3200个rawflags零差异；8×512=4096 Matrix各1输出/完成，8真实ICG及1DMA同时存在，DMA接受请求且AXI请求可见，未传输完成。7项边界负测通过。桥库SHA56a45ca6989c304d1e38cc0a19291695a3366036a6d628df6f51e6f3c14bb1cc。
精确范围仅相同外部调度下transport等价，不是独立算术参考或Host边沿资格。Host.eval(high)可能暂存post-edge数据、ICG冻结输出仍low，必须low settle后冻结非clock输入，高相仅传播真实ICG到Matrix边沿；当前未贸然执行Host。不能拿17句柄存在冒Host17路正确互连、strict fatal或完整prefill。

## ONGOING：固定Host编译和时序
同一固定4096候选IR生成真实17extern绑定，保留1533的20组strict诊断callback，不常量化ready。新C++wrapper通过-Werror。原66548进行有界Host Arc编译，出现array_concat的array<1>被scalar化类型错误，完整编译未通过；原错误保留，需最小复现和等价修复。没有五profile重elaboration，没有丢断言路径，没有Host执行。

## 原算术异常审计
不能说Matrix完全没有数值检查：StreamingDense和TransposedDenseOwner独立检查返回finite及BF16转换溢出并报Numerical。finite只检查指数非255，不能捕获有限返回值对应的中间UF。实际HostIR Matrix extern无flags输出，MatrixPipeline主要传播协议/context/last错误，1533新增read_flags仅诊断，未修改fatal策略。
Vector/Scalar实际读取HardFloat flags，有明确opcode例外，NX也不是普遍fatal，不能笼统说全部UF fatal。原head4 FAIL不变。此为源码/已有IR只读审计，非运行异常注入；若契约要求Matrix逐步异常，还需明确传递或证明任务域没有这些异常，21-op值hash不能代替。

## 五块输入进度及阻塞
Qwen2当前全21独立参考候选值及消费闭包保留，无本轮重算，不冒模型PASS。0.8B L0/L3原hidden缺实体/生成者，L3独立原hidden身份还缺，未重复候选/seed或换刺激冒恢复。
35B已恢复官方固定revision的精确张量range：L0 18张量1685402304B、L3 15张量1672492032B，总3357894336B，逐项核index/header、shape×dtype、分片总长。完整真实payload仍缺，payload hash为空，header不能冒内容认证。
历史原54985：小range曾成功、两层各64MiB partial后CDN策略拒绝；当前原终态/partial实体已丢，拒绝未解除，不以历史206证明现在可达。本轮没有网络重试/换路。只有限制正式解决后，才可依次极小张量→非expert→4个expert流式取数并严格验证，当前不启动下载。

## 纪律与下一步
先完成Host真实低高相快照/共享handle和严格异常，再完整原模型数值，最后冻结同刺激RTL。起点main6cf3ed35、同head CI43050640798成功仅payload guard，工作树干净，约9.1GiB可用RAM/56GiB磁盘；1533关键实体重新核hash。临时清单已检查，既有数据清理0项，无权重/输出/rawlog/被拒源码上传，发布仅允许摘要和hash。

## 后续实际修复结果
精确8对ICG→Matrix映射已从原HWIR逐SSA确认。新增frozen-clock接口，low冻结非clock输入、真实传播ICG时钟，高相新sink不能污染当前边沿；source到下一prepare仍冻结。200cycle双套真实native差分2538000words+1600flags零差异，包含真实门控停顿及冻结后全部输入投毒，八Matrix各1输出/完成。9项新增阶段负测通过，原transport测试全部重跑通过。首轮direct驱动漏initial-low被ICG拒绝-2，保留失败并修driver，不改DUT。最终薄桥库SHA8dacae09c9c423de15b677d668855e3aa901eadc49d5c1ff6e04147315d0a3a5，替代前文初版hash。仍非真实Host组合收敛/联合posedge/完整strict资格。
Host原66548明确exit1，原组合SCC不再报，进入array<1>兼容类型错误。最小concat/get重现同错；官方aggregate-to-comb路径与窄bitcast/concat路径8192顺序case吻合。对Host仅40处concat做等bits/等元素数兼容变换，不缩容量，不变端口。新原98515受5GiB/240s有界编译，等待明确终态，不能按LLVM文件存在推定通过。

## Host LLVM明确终态
新98515明确exit0，完整Host LLVM32393997B，SHAf1542f319a2bd400034883e706efd7a0885f66d667adc280cb1fc70260eb27f0；状态JSON SHAa79fbc70b550fa9725c5450fca17771921a34f2044e6e3e2e94a697301e592c1。20strict函数声明全部保留，6个native sink/source CABI类型匹配，状态1607520B/85ports。原反馈SCC在该编译路径消除。机器码llc新唯一26275受5GiB/240s限额，写本段时仍待终态；即使链接成功也不是Host执行/数值PASS。

## 机器码终态
原26275达到240秒墙限，exit124；没有启动替代重复编译。LLVM阶段98515 exit0保持为仅编译PASS；机器码阶段INCOMPLETE，未完成链接，不声称可执行Host。当前无新增运行作业。20strict实际调用与6native函数已核存在；需沿现有LLVM/命令及资源证据诊断llc耗时，再决定后续预算，不重复昂贵作业。工作区干净，临时清单10480条，既有数据清理0。
