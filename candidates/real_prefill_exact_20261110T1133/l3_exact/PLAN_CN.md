# L3真实 M128 完整剩余算术链精确审计（TEMP，数学参考层）

复用并逐文件SHA核验真实0.8B L3权重、caller hidden及已保存M128中间值；不重算已在上一轮精确资格的四norm。七Dense、8query heads的QK和PV全部按K递增FMA执行，不用matmul/BLAS重排。QK先BF16，再FP32 scale1/16再BF16；PV包含全部128key的masked零概率。有限BF16×BF16+FP32使用已独立审查的FP64两次舍入值等价与TwoSum精确残差flags方法，前提IEEE RNE与保留次正规，不能扩展为任意FP32乘数证明。

真实所有mask Add最小finiteBF16/+0、BF16物化、全key subtract、精确sentinel域检查、degree7 exp逐节点FP32、升key总和、每项Div、sigmoid/attention gating、两次残差、FFN SiLU与up乘法都用Fraction/整数RNE逐值flags核验。相同primitive输入/exp输入缓存复用确定性精确结果，节点及flags计数按实际调用次数计，不是唯一输入数量。exp使用既定8系数与INV_LN2字，非np.exp或FMA。保留原fatal策略，若数学primitive出现UF/OF即停止，不把错误填零。

完整部分RoPE另外覆盖Q8/K2heads各128token前64维：四乘/两加每节点BF16，后192维原值复制，全部输出对保存数组一致。此与Qwen2 FP32 RoPE契约不同，未混用。

结果范围：七Dense/QK/PV共2,415,919,104有序FMA；完整scalar链9,114,112 mul、7,671,808 add、851,968 div；RoPE163,840 mul、81,920 add。实际数学flags仅0/1，最终输出SHA与已保存完整候选一致。

限制：这些flags是数学primitive的NV/DZ/OF/UF/NX，不冒ExpNegative整体硬件接口flags；BF16格式转换的**位值**已执行且全输出一致，但其硬件异常状态映射未资格；不涵盖NaN/Inf域。四norm依赖上一轮各自精确证据，不借此迁移成新的硬件通过。没有执行Chisel/RTL、没有时序/利用率数据、完整五块硬件仍0/5，原head4硬件FAIL及L0四head候选fatal失败不变。

原session56145因PV把[128,512]当三维读取而IndexError，失败日志/摘要保留。修为明确[128,2,256]视图后session25750 exit0/24.92s，未改数据或算术。RoPE22970 exit0。最终增加非有限Matrix输入拒绝，普通与-O边界测试通过；最终-O完整真实链session76438及RoPE结果见RESULT/ROPE_RESULT，不继承失败。

源码包不含任何权重/输入/数组，只含源码、pin/hash和必要摘要。所有实际数据只读，未往硬件填参考中间值。复现需要前轮按hash恢复的真实payload；OPENBLAS_NUM_THREADS=1 timeout600 python -O run.py，再rope.py。2GiBAS/590sCPU限制。
