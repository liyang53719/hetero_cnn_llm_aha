# 独立 accepted packet 摘要验证契约（新checker实现，非只读历史结论）

## 输入与准备边界

`PLAN.json`固定本次 `extended_m128_01` 的5个实际归档输入、1个完整事件流和元数据证据身份。准备期只核对5个小输入的SHA/长度；**未打开真实event流，未进行全量解析**。流237446391B/2478339事件/SHA来自保留的sealed `SERVICE_PROTOCOL.json`，只是待执行的期待身份，不能冒称此新checker已经验证。旧失败、批准、claims、成功证据不修改。

输入为原终态封存的q、KV parent、捕获prob_bf16、presence、frequency；不是官方reference。所有输入打开同一FD完成长度/内容hash检查。新checker只import stdlib；不import DUT模块、source loader、native Matrix/Scalar ELF、Torch/Numpy、参考或RTL工具。

- q：`[M,1536]=[M,12,128]` token-major，FP32容器中的BF16字。
- KV：前`M*256`字为K `[M,2,128]`，后`M*256`字为V，同为token-major。原比较器已检查KV内容等于实际k/v（`terminal_comparator.py:104–105`）；本checker使用完整kv实际归档，不新建repeat。
- prob：`[12,M,M]` head-major。仅`key<=query`合法；所有这些presence=1、frequency=8，future presence/frequency=0、words仍`0xa5963cc3`。本checker保留sentinel，不写任何future值。
- input存储端序为little-endian uint32；frequency为little-endian uint16。跨端序机器使用array.byteswap进行整数表示转换，不作浮点运算。

原Attention job（来源orchestration）：tag=458764，M128/N1536/K128，q base=4485895360，K base=4487337536，V base=4487468608，dst=4489172736，write_bytes=786432。V−K=128*256*4。这里是已封存job元数据，不是新生成的DDR事务日志。

## 独立索引与严格字节布局

执行期的expected cursor独立实现，不调用DUT schedule/index/helper：依次query=0..127、head=0..11；本head全部QK组后才执行8组PV。KV头用独立分段条件`head<6 ? 0 : 1`，不复用DUT的`head//6`函数。

### QK profile2

每组覆盖first_key=0,16,...≤query，active=min(16,query−first+1)，8个depth step，depth=16*index。

- `A[r] = q[query*1536 + head*128 + depth + r] >> 16`，r=0..15。
- `B[16*j+r] = KV[(first_key+j)*256 + kv_head*128 + depth+r] >>16`，j<active。
- j≥active的全部B槽强制期待0；不能读取future K来补tail。
- profile2 group `(opcode,steps,slice_mask,profile)=(0x23,8,255,2)`。
- 每step context=0；clear iff index0；last=finish iff index7；emit iff index7。

### PV legacy profile0

每head的column=0,16,...112，每组query+1个key。

- `A[0] = prob[(head*M+query)*M+key] >>16`；A[1:16]期待0。
- `B[r] = KV[M*256 + key*256 + kv_head*128 + column+r] >>16`；B[16:256]期待0。
- group `(opcode,steps,slice_mask,profile)=(0x24,query+1,1,0)`。
- index=key、context=0；clear iff key0；last=finish iff key=query；emit每步true。
- 同一causal prob实际用于8个不同column packet，且原observer确认8次FP32/BF16值一致（`O/capture.py:35–45,62–72`）。新checker只核8个accepted packet内容，不称8次DDR probability读取：prob并无独立DDR producer。

### SHA输入

每步唯一摘要输入恰为 `struct.pack('<272H', *A16, *B256)`：**先A的16个uint16，再B的256个uint16，little-endian，总544B**；不是FP32、不是B转置、不是JSON、不是只取active lanes。所有实际源BF16容器先验证low16=0且finite，再纯整数`>>16`，所以不是重新计算或改变舍入。

根源：原ServiceTrace `_return`在`accept_step`返回True后读取同一实际step，`runtime_observer.py:55–74`尤其`66–69`。原client把原A/B无变换传入NormalStep：`attention_packed_owner/client.py:327–350`；service字段及native边界：`ffn_attention/matrix_service.py:333–350`。QK生产者`production_qk16_model/schedule.py:31–54`，PV生产者`:99–106`与`ffn_attention/attention_owner.py:83–89`。

## 事件字段域与生命周期

独立decoder核8B magic、uint32LE长度、≤1024B canonical JSON、footer `0xffffffff + count:uint64LE + SHA256(all length-prefixed records)`、整文件同FD SHA/长度、EOF；少一个footer、尾随数据或超额事件都不接受prefix为PASS。

每event形如`[name, edge:uint64, payload:list]`，edge单调不减，**软件edge不是hardware cycles**。

| name | payload / 核验 |
|---|---|
| acquire | `['normal', owner_tag:uint32]`；单次首事件且tag=458764 |
| accept_group | opcode/steps/tag/slice_mask/profile全uint32；按独立cursor精确匹配其余4字段；tag绑定后续done |
| accept_step | index/context uint32，clear/last/finish/emit严格bool，64位hex摘要；bool不能冒充整数 |
| retire_result | context:uint32、last/error严格bool、ticket/epoch:uint64、完整tile摘要hex；核metadata，但**不核其tile数值摘要** |
| retire_done | group_tag:uint32、error:bool、ticket/epoch:uint64，与实际group/result匹配 |
| retire_legacy_reply | ticket/epoch:uint64；仅每个legacy结果之后，末步在done之后 |
| retire_owner_response / release | 空payload；全部组完成之后恰一次、先terminal再release |

QK每组：group→8steps（仅末step发result）→result→done。PV每组：group→逐step/result/reply，末step在reply前退done。没有abort成功路径。一个epoch，组内ticket不变，组间ticket正数严格递增且有限非wrap；不做ticket改写或猜原始ticket值。不同组tag可以复用但每次done必须匹配该组，不额外声称全局tag uniqueness。

## 成功声明与不能证明的内容

成功只声明 `PASS_ACCEPTED_MATRIX_OPERAND_CONTENT_AND_INDEX_SEMANTICS`：归档实际数据在独立预期因果/GQA6/tail映射下，与全部accepted Matrix operand摘要一致，且完整流校验通过。

它不证明：逐DDR地址/tag/response握手（未归档）、完整16384B结果tile、FMA/Scalar重新数值运算、score/max/exp/normalizer电路等价、mask/repeat/logits实体tensor、full29、RTL、硬件cycle或利用率。hash协议是SHA256内容身份，不是逆向恢复日志；相等内容也不能证明地址不同或相同。此checker不提升softmax_fp32阈值资格。

当离线验证通过，可作为四项非物化协议/索引闭环的**新增一层证据**，与现有source pins、实际causal观察、参考侧结构关系合看；不能单凭packet PASS给四项全部无条件签字。
