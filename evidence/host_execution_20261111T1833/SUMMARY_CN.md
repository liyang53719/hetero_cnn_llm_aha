# 18:33 原Qwen2绑定恢复与真实活跃AXI边界

五块128 token完整原Chisel数值仍0/5；最终同刺激RTL未通过，固定4096完整block有效MAC80/90%未实测。原L0 head4 FAIL不变。未知旧Qwen2/L3 profile任务没有重启，以下是明确独立新边界身份。

## DONE：原Qwen2 public21重新发射与真实输入绑定（TEMP）
找到原pack_owner_block_fixture.py，历史源码pin3efc7bb21b66bd16f757b8aac99c779ad3efe9289115e6ea7d5628a4ff6c2154核实。按M128/H1536/F8960/12Q/2KV/HD128原builder重发21条command、215条descriptor、35 allocation，标新刺激身份，不冒旧丢失table的同刺激资格。
最终只用FP32 metadata，tensor全部dtype7，包括七个Dense权重；13个真实FP32输入和原Host-double trig绑定，中间数据未预装。源码核bf16Weights=true仅允许BF16 B，不拒绝FP32；原FP32存储入口仍可用，不改硬件精度。调查生成过BF16 metadata，但明确排除，未转换/消费实际权重或运行，最终emit移除转换步骤。
command SHA618cd4db94fbc5f0e3829182a72d5e298b5a42d2a3840ec2b9f9be639cd884c4，descriptor SHAd5ef2c75f7c8f790993a9aef04ff0af96209365af3df85b33fae9ff8d8cb3086，BINDING SHAc025fcb03bd9d1831dba4771a12753c613c41fc4ae416e451f8c94f8ceac0c1a。
62个tensor前缀按当前原reader独立字段解析、13真实输入读取、ROM和未写先读拒绝通过；代码已接1733真实AXI响应器，静态读取首command/descriptor并核实际x源，准备新layout launch参数。未运行完整Qwen2，硬件metadata准入/数值仍待验证。

## DONE：真实Host活跃AXI边界
唯一1833_host_axi_opcode_ff_v1 exit0，37周期，真实AXI取0x1000命令64B，原decoder收到FF返回Unsupported4、completed0/pc0/epoch0x1833。AR、completion/result各反压5周期，R延迟3周期，valid/payload保持；部分低相3次delta收敛，不固定延迟代替。
修driver新增pre_outputs，按pre-edge信号判真正accept，不用post输出冒握手。该测没有权重/中间值，MAC/job/写请求均0，仅命令取数及结构化拒绝PASS，非prefill数值。

## DONE：真实外部错误契约；strict fatal仍INCOMPLETE
4个R/B×ID0/255未请求响应、resp3新独立负例，各19周期、exit0。ready保持0，原quarantine/resetRequired触发；撤valid后3周期sticky且launch_ready0，计数不动，3reset+1idle恢复ready1。对应原IdmaWeightBurst.scala137–149和Top334。
另3个匹配请求SLVERR、错误RID、错误LAST活跃负例，真实R握手后原Memory status3/completed0/pc0，反压稳定。不是assert-fatal：均正常结构化错误，不能冒strict exit86负例。没有修改内部state或发明fatal策略。
原105断言多数为内部held/ownership/互斥不变量，没有找到由公开非法请求必触发fatal的源契约；当前保留strict调用但实际联合fatal触发仍未验证。下一步依合法活跃数值或真实不变量故障验证，不人为损坏state冒完整资格。

## ONGOING / TODO / 阻塞
Qwen2真实FP32输入与新程序绑定已齐到静态适配层，但实际完整launch受旧任务终态未知限制，未擅自重复；原Host实际解析与完整数值仍需验证。0.8B L0/L3缺原hidden实体/生成者，L3原身份亦缺；35B两层完整权重payload缺且既有CDN拒绝未重试。不把其他四块检查冒编码进展。
继续真实完整模型后冻结同刺激RTL；本轮未新生成或按profile重elaboration硬件，复用同libhost6c7ec0…36e50及native271b15…118cb。
开工main b17b29a8、同head CI43072213478成功，仅payload guard；工作树干净、9.1GiB/56GiB可用，关键实体新核hash。临时清单检查、既有数据清理0，无权重/输出/候选源码/rawlog发布，仅允许摘要与hash。
