# 03:33 原完整prefill实际推进及重连恢复边界：INCOMPLETE

## 实际工作与已提交结果
开始已核main ab5406d8、CI42948926352成功、原作业及资源。L3从664907显式恢复，前两段91555/77307 exit0，分别261.81/262.18秒，保存到764911、864911。新增实际pipeline stalls但仍有写回，不能据此前线性速度估计完成时间。
L3可恢复终态仅864911、Matrix108608、pc1/completed1。21组件与原/新closure已在重连后独立重验；Q已提交425984 BF16值与同刺激独立参考逐位一致，98304未写排除，无半有效字。manifest2af801db295cc66f0717be2fed210586bf888b0779c1bd82ed99500a3b4a6278；receipt segment600k_CONTINUATION.json SHA ffbf5a20742eda4970894894c44c61016e23304d2bbabff8a2ad2555587da4cc。

Qwen2从100000真实状态恢复，没有冷重启。新增显式resume入口，补拒绝未经driver检查的周期占位、旧默认/相对receipt及错误新runner身份；6项前置门禁测试通过，恢复序列/低相不产生reset或重新launch。两段保存到200000、300000，原FP32/固定硬件/数值不改。
Qwen2可恢复终态300000，21组件/closure/新runner重验通过；38400已写FP32 Norm值与原同刺激参考逐位一致，158208未写排除，无半有效字。manifest27ea31c6ea565e2fa321eab8e7a8d5c196e1dc2375486e11b43331e4186f83f6；receipt segment300k/RECEIPT.json SHA fe320546000617313e2197ccdd4c562b9b4a1707b02625e3b407ef061d823428。

## 原在途第三段观测不可用
环境重连后，原执行线程poll L3 session3321、Qwen2 session19911均Unknown process id。L3最后日志03:48:31 UTC/active909504；Qwen2最后driver日志03:48:30/active385728，心跳03:47:38。均无第三段终态receipt或manifest，checkpoint目录为空。不能确认退出原因，不能臆测OOM/预算/数学错误，也不能把日志末点当保存进度。没有自动重启或终止；原日志保留，下一步仅可从上述已提交且重验的保底组恢复。

## L0实测与五块范围
同冻结4096 Host和17native，完整原17-op/219描述符真实launch握手成功，已进入pc0 input_norm。短预算3000 active cycles/8.10秒：jobs1、DMA197、读ACK165、写ACK32/2048B、reset0。原driver按预算退出1，完整数值INCOMPLETE。首尝试因无checkpoint目标却遗留active-cut环境选项被既有guard拒绝，active0，保留原日志；仅移除不适用运行选项后实测，不改guard。未跑到原head4下溢FAIL，不解除该FAIL。

Qwen2与L3当前均只是已提交输出子集数值PASS；L0仅launch/服务执行资格。35B两层缺真实完整权重仍FAIL，未重复网络失败或绕限制。五块128 token完整数值仍0/5；最终RTL同刺激回放未通过。固定4096及同Host定义不变，本轮原编译IR+真实native模型执行不冒最终RTL数值。完整block80%/90%有效MAC未测达标。

## 计划与清理
DONE：两路前两段真实数值、可恢复组重验、Qwen2恢复入口门禁、L0真实准入。BLOCKED_OBSERVATION：第三段原运行身份不可查询，无提交凭证。TODO：从L3 864911与Qwen2 300000保底继续，显式核receipt和closure，逐段持久并比完整阶段。
初始全round清单43485文件约10.864GB，约9GiB可用内存/47GiB磁盘，未删除任何文件。原输入、唯一checkpoint、失败证据保留。仅发布允许中文摘要/hash，不上传候选源、原日志、checkpoint或权重。
