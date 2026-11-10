# hetero 19:33：完整原模型编译与真实17native启动（INCOMPLETE）

## 已完成的实际编码/测试
- 实现fail-closed extern transport拆分：原每个实例输入sink/输出source共用同一真实native handle，核验原17完整路径、类型位宽、物理module headers不变；不是修改RTL、删ready依赖或插入硬件周期。
- 独立审查发现首次调度仅覆盖native→core，修复为双向pre-edge快照：低相先收敛并冻结双方输入/输出，Arc与native分别一次advance，然后发布post并同level收敛。加入8个core寄存器驱动Matrix命令的真实测试；故意读取post的反例exit1。保留step_ready对当前context/out_ready的真实组合依赖并实测0→1变化，不统一忽略依赖。
- 17真实native反馈图400半周期、1667200个Matrix word对照一致、8slice各一次output/completion；重复高不新增边沿。简化opaque图本身也能编译，未谎称其复现原SCC；原完整失败与新完整编译才是直接对照。
- strict断言/print compiled小例6场景通过：低相收敛坏值在rise终止，重复同level不重复推进；pre-good后的post-bad留到下一个rise检查，pre-bad不能被post-good掩盖。

## 完整模型里程碑，精确范围
- 原完整Host保留107条断言桥、原print、固定4096资源及全部17native，拆分后唯一Arc→LLVM编译8252 exit0，74.41秒；此前明确的extern保守反馈SCC编译失败已解除。
- 唯一llc对象编译59534 -O1 exit0，174.23秒，在180秒/7GiB预算内。首次shared链接漏-fPIC被ld拒绝，补标志后链接成功，无重编对象。库明确链接strict检查与官方print runtime。
- 完整state为1624112字节；17实例223个native端口槽类型/偏移/无遗漏/重叠核验通过。
- **PASS范围仅完整compiled Host reset/idle**：3周期reset+5周期idle真实执行exit0，约0.134秒，17真实native绑定，settle最多2轮；ready=1/result=0/resetRequired=0，issuedJobs=0/pipelineIssues=0。无launch、无中间参考预装、无完整block数值比较。不能据短smoke推算完整性能或利用率。

## 五块与下一步
五块M128完整数值仍0/5、最终RTL未通过。Qwen2真实FP32原链等待接回原AXI driver运行；0.8B L0原underflow FAIL保留，L3真实owner/receipt全链待执行；35B L0/L3真实冻结输入与MoE同分契约缺口仍在。共同原硬件定义/物理接口未改，32bank不等于目标32lane全吞吐，80%/90%利用率没有完整周期实测。
下一步复用原193-byte输入/368-byte输出transport、hash核验真实权重和输入，不传oracle或预装中间值，先有界真实M128完整执行与独立参考比对。当前准备接入，不把编译/启动称作完整模型数值PASS。

## 发布与清理
只发布本摘要和hash；候选代码、IR、工具、native库、日志、权重/NPZ均未上传。临时清单保留唯一失败和运行证据，无清理。所有上述编译与smoke均终态，未重复长Host/EDA。

## 本轮随后真实M128尝试与性能候选
原AXI driver逐端口193-byte输入/368-byte输出接入后，首次3帧因适配器漏首次low观测而被native clock保护拒绝，未launch；原失败完整保留，修复不放宽ABI。一次已授权120秒完整M128重试（原身份PID7/start6716702）实际launch并执行到首Norm，24731帧、pc0/jobs1/DMA98/completed0/pipelineIssues0/resetRequired0，未收到final；120.004秒预算终止，明确INCOMPLETE、无参考比较。定向小测曾错误等待driver连续high而未停，已如实将该原进程计为唯一完整重试，不重复开另一轮；随后仅4帧0.182秒验证首low/rise及主动repeat-high，无launch。所有原身份和分阶段证据均保留。

独立传输候选用严格检查的little-endian memmove替代native out_acc的512字Python大整数pack，未改模型、时钟或pre快照。真实17native 400半周期每次拷贝均与旧字节结果对照通过，另11字节案例/7异常拒绝测试通过。2000次2048-byte局部拷贝基准0.478秒→0.00222秒，仅微基准，不是完整Host提速或硬件利用率。尚未将候选用于新完整M128运行，0/5不变。
