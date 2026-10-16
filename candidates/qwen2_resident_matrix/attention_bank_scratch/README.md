# 既有 A bank 的显式 scratch 数值模型

## 中文计划

- 已完成：独立 opt-in raw 模型路由、96条 scratch line、真实 Dense owner/Banks 共享、matching ACK 后有效性；M1/M2 首轮原 owner 数值对照。
- 已完成：17项短测试普通/优化模式均通过，58项依赖/9项候选源身份校验通过，独立审查通过。
- 进行中：独立大形状profile与M16有界成本校准准备；本profile仍仅执行M1/M2。
- 待做：真实 Chisel region/mux/staging lease 接线，输入/输出与全部控制状态的物理放置，完整 M128 数值和整块性能验收。

默认关闭。`Controller(scratch_enabled=False)` 不分配 Scratch，拒绝执行该新 profile；必须显式 True。已有候选及 Public runner 不修改。

## 路由、身份与债务

`route.patch` 是对冻结 raw_kv/model.py 的明确 Python 模型适配；`port.py` 是其逐字输出，并复用原 Key/Request/Response/Obligations 类型。默认 line<4096 保留；opt-in 请求和ACK才共同接受 line<4192。原 Chisel key 为13bit，但请求/ACK仍限制4096；本目录没有实现硬件扩展，必须新增明确 profile 和 bank mux 控制才能连接。

score line=4096+8*head+key//16，prob line=4144+8*head+key//16；每line16个FP32word。物理 pair=2*(line%8)、pair+1，word=line//8。96×64B对应原16×1376×256bit A 的word512–523，共6KiB。K/V仍为0–4095，不访问旧KV bitmap或DDR身份校验。

Scratch 使用实际 ParentLoan 和 DenseReductionOwner 的唯一 a_banks；仅在安装时所有真实owner债务为空才能替换未使用 raw transport。query/KV-head/递增generation绑定操作；pending/held/staging存在时不能换generation。换generation先失效96个beat元数据及每head的score/weight/normalized前缀；不清除或复制payload。tag不复用，溢出拒绝。写有效性只在干净matchingACK后推进；abort保留 accepted debt 并排空，不发布有效性。

## 实际访问与暂存提案

每事务分别计接受、同步形成held响应、ACK三edge，反压额外计edge。每接受访问恰好两个256bit bank，hold/ACK不访问bank。原owner每edge一起tick并执行原端口冲突门；不存在空闲bank端口的隐含并行访问。

QK原joined结果slot保持到score写ACK，随后释放。score packet拟复用tmp[16]；acc[16]仍保存fold/gather中间值，av/bv用于operand。cv[0:6]存max，cv[6:12]存sum，Div ACK后覆盖为inverse。唯一64B transport/RMW暂存拟复用dv[16]，在读ACK前捕获held raw响应。没有六line缓存。cv/dv原用于RoPE，真实接线必须新增完整staging lease并封锁Norm/RoPE/Bias及其他owner跨packet间隙访问；当前模型的全局active/raw lease是提案，不能冒充现成硬件mux。

softmax每key依次读取6个score，再按原顺序sub/exp/add。每个weight逐word写入概率line：首word显式零初始化完整beat，其余逐次read-modify-write。sum完整后，按原顺序读取weight、乘inverse、写normalized回同一plane；PV再逐key串行读6个normalized word。原global normalization-before-PV次序保留。已覆盖的weight不再作为旧weight读取。

这是保守的7P事务方案：P为causal head/key对数。M1 P12，84事务，48读/36写；M2 P36，252事务，156读/96写。无反压另加acquire/release两edge，分别254/758 bank服务edge。M128仅账本 P99072 →693504事务、2080512最小bank服务edge，尚未执行。不得混同无需normalized回写的另一个4P优化方案。

## 数值与未完成边界

保留QK8步/16stripe有序fold、dot BF16、FP32缩放、score BF16，softmax和PV原顺序。M1/M2与实际原OfficialAttentionOwner AST oracle及前一冻结controller比较；测试trace可保存scores/output用于验证，不作为运行storage。Q/K/V输入仍为host fixture，最终输出仍为host收集；不能称完整物理控制器。逐cell finite故障、selector/Matrix/divider时延仍沿用前一模型的明确假设。真实异常flags、controller/mux、全输入feed/DMA/最终输出ACK仍未实现。

沿用4096MAC固定资源、整块6014828544 useful MAC、71680 SiLU向量/1146880 division账本。串行bank费用和Scalar/Exp/Div费用都不能当成免费；没有RTL、硬件cycle、80/90%利用率或完整M128 PASS。

## 短测试

`python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_scratch.test_port candidates.qwen2_resident_matrix.attention_bank_scratch.test_storage candidates.qwen2_resident_matrix.attention_bank_scratch.test_controller -q`

同一命令加 `-O`；源门：`python3 -S -B -m candidates.qwen2_resident_matrix.attention_bank_scratch.check_sources`。
