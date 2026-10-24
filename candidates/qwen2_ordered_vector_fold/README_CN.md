# QK16 ordered vector fold/scale：默认关闭的微模型

状态：TEMP / INCOMPLETE。只在 `OrderedVectorFold(..., enabled=True)` 显式选择时工作；未接入 selected schedule 或任何生产入口。没有改动旧路径、历史 pins 或历史 PASS。没有创建新 SFU、Matrix 或通用 vector 架构。

## 中文执行计划与已完成范围

1. 审核 main `1bdf70eb42de8752edeb616e8ef01e166628ca35` 的原有算术 helper、BlockFloat、TensorMath 和 HeteroFP32Alu。SOURCE_PINS.json 的 Git blob SHA 对应该 main exact tree；不是仅按文件名借用旧副本。
2. 建立独立、可执行的 QK16 group 微模型：持有 live result 引用；lane j 对应 key j；row r=0..15 按原顺序 Add；BF16 物化 dot 后原 scale `0x3db504f3` Mul，再 BF16 物化 score。无 tree sum、FMA contraction、容差比较或完整 tile copy。
3. 运行有界 stdlib CPU-only 精确字测试，并逐 key 对照串行旧配方；测试 arithmetic、尾块、取消、结果持有及抽象债务。不启动 native-heavy、EDA、Scala 编译、RTL 仿真、权重下载、M128 长作业或 CI dispatch。
4. 下一阶段先补齐下述真实 Chisel 接口再提交默认关闭控制 patch。这个包不把未经编译/证明的控制草稿伪装成已接入硬件。
5. 同源完整 M128 重验和固定资源完整 block 周期分母建立前，不声称利用率80%或90%、whole-block加速、频率通过或可发布性能结论。

## 算术异常必须相同

真实 BlockScalarFloat normal 分支（BlockFloat.scala 71–81）检查 NV/DZ/OF，且旧 Add/Mul 的 UF 仍 fatal；非有限输入/结果 fatal，NX 单独允许。显式新 opcode MulIeeeRne 的 UF 豁免不适用于本候选。HeteroFP32Alu 为 FP32 RNE、tininess_afterRounding。

测试直接执行现有 `attention_matrix_batch/test_model.py::ExactScalar` 及 `ffn_public/test_prefix_owners.py` 的原样 AST 定义，没有 import 它们的 native/NumPy 模块前言。ExactScalar 对 tiny rounded result 做 exact-rational 比较，允许 exact subnormal，拒绝 inexact underflow。只调用 Add/Mul/BF；DZ 在 finite Add/Mul 中不可达，故没有把未执行的 Div/DZ 硬件覆盖记为 PASS。NaN/Inf 在输入检查时拒绝，测试不声称观察过实际 NV pin。

BF16 helper 对非有限值的 NaN payload 行为与 TensorMath 不完全相同，但本模型在每个 BF 节点之前保证输入有限，BF 后再次检查 finite。可达域内按 exact word 比较，不隐藏 payload 差异。

## 顺序、状态与真实资源计账

- 先用16次 stripe 扫描检查各 active key 的16个输入 finite。旧 attPackedSelect 是先检查整 key 再开始 Add；扫描在任何 Add 之前完成，避免新路径把后面 row 的 nonfinite 排在前面 Add overflow 后面。
- 再进行16个 stripe Add。acc[j] 初值+0，r=0..15次序不变，读取 live result.value[r][16*j+r]。一个 key fault 后不再调用它的 arithmetic；其他 active keys可以继续计算。
- 单独 scale 阶段把 acc 原地替换为 BF16 score。真实设计可组合 BF(dot)→既有 Mul→BF(score)，不是声称这条组合路径已满足频率。
- 逐 key 顺序退休，一次提交一个 score 并更新现有 maxScore。后 key 的 fault 只置位，不提前发布；遇到该 key 退休时才失败，所以已经提交的 score 前缀和最大值与串行基线一致。
- 当前模型只有 proposed 16 sticky fault bits，而不是16份32-bit flags寄存器。真实 ALU 的 NV/DZ/OF/UF 可组合归约到这一位；NX不需保存。具体异常类型/首异常 row 不对外输出，若未来要求须另计新增状态。
- acc[16] 是复用既有512位寄存器，不新分配512位 score bank。模型 committed 列表仅表示既有 score SRAM 的观察记录，不能算作额外硬件寄存器；scalar.trace 也只是测试观察。
- row可复用既有 lane[3:0]，退休 key可复用 packedSelected[3:0]，active count为原 packedKeys，maximum为原 maxScore；新增控制状态必须检查原枚举宽度与互斥。没有声称这些复用已经完成 elaboration。
- 新增组合控制包括16路 finite/flag归约、live FIFO stripe选择及现有vector输入选择。扫描多读一次 selected cells，共不超过512个word reads/group，不是256-word或16KiB暂存tile。
- 成功时最后一个 score 退休之后才发 consumer ACK；ACK被阻塞时继续持有 live result。故障/abort不发成功ACK，保留已接受工作债务，等待底层 client drain。

## 明确 Chisel 接口缺口：本批不提交伪集成补丁

针对 selected Qwen2Block postimage SHA256 `31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68`：

1. 137–139行的16个组合 HeteroFP32Alu 已存在且适用，但实例在 map 局部，vout丢弃 exceptionFlags。最小集成必须保留实例序列并显式导出16组5-bit组合 flags，不是只接 vout 就宣称 strict。
2. 现有 acc 在 attPackedIssue 收到最后 result 后被第一 key selected lanes覆盖，并立刻转 attReduce。开启候选必须改为初始化16个+0并进入 scan/fold，不得保留旧 acc:=fmOut 覆盖新 accumulators。
3. 现有 final-result fmOut/packedSelectedFault 和最后连接 finite检查只针对当前 selected key。并行 scan不能把后 key的fault接到全局 fail，必须仅在该 key退休时把 sticky bit转为 packedSelectedFault。
4. 既有 packedCommitted 只在最后 score写入时置位，c.io.result.ready 由其与 !poisoned控制；这条消费ACK、completion.ready、packedOwned及 packedMemDebt/packedLocalDebt/packedScalarDebt 的清债路径必须保持。新模型的 result/done/response集合只是抽象测试接口，不证明 PackedAttentionStreamClient 真正 done/response 时序、tag检查或 resetRequired 优先级。
5. 现有 attScore 具有 poisoned/resetRequired/port.done.valid 门控，末尾 last-connect safety优先覆盖 transition。真实 scan/fold/scale/retire都必须保持同样终止优先级，不能写出已poisoned后的score。模型只测试显式 abort，未证明真实外部done error竞争。
6. vectorA/B/vectorMul被 norm、bias 等状态共享；必须审计全部状态互斥及 external borrower配置，再将fold/scale接入。不能借用独立 ElementwiseMemoryEngine 冒充这里的16个ALU。

## 运行与资格

在包含 main原始源文件的 checkout：

    python candidates/qwen2_ordered_vector_fold/test_model.py --source-root . -v
    python -O candidates/qwen2_ordered_vector_fold/test_model.py --source-root . -v
    python -I candidates/qwen2_ordered_vector_fold/test_model.py --source-root . -v
    python -I -O candidates/qwen2_ordered_vector_fold/test_model.py --source-root . -v

启动前校验所有 SOURCE_PINS.json 源文件；不改旧源 guard。建议 CPU limit 20s、address-space limit 256MiB。纯 Python stdlib，无自动 RTL生成。最终 normal、-O、-I、-I -O 各12项测试通过；完整通过记录在 validation/ 下。

覆盖：144个tail/rounding/cancellation/±0/subnormal组合、96个固定seed随机tile、80个fault-key前缀组合、所有active tail 1..16、结果/输入回压、11个abort时点、未最后消费前不释放、三债务清完前不重用、跨group max继承、mixed-sign/±0固定最大值、故障发现顺序逆于退休顺序、default-off。测试数字是case数不是硬件事件数或周期数。

尚未验证：生产schedule接入、Matrix arithmetic/fullblock、真实client abort/reset/error竞争、Chisel编译/RTL同源对应、mux/flags时序面积、完整M128、固定4096MAC与整个block周期分母。模型step/主机耗时均不能当作硬件cycle或MAC利用率。

启动隔离修复：旧冻结脚本在 -I 下缺少脚本目录，已复现 ModuleNotFoundError。新脚本只添加自己的已解析目录，并校验 model.__file__，不添加 production source-root 或导入生产模块前言。model.py 与原冻结版本逐字相同；原失败记录保留，不能将旧包记作 -I PASS。
