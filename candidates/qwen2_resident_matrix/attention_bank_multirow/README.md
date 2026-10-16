# 同一 bank-backed controller 的多行 Fraction 校准

## 中文计划

- 已完成：独立形状门只放宽冻结 run 的整数上限2→16；M1/M2回归保留原输出、score、操作数和时隙；观察trace改为固定schema计数/hash。
- 已完成：14项普通/优化模式准备测试、68项依赖/8项候选源门和独立审查；实际修正M4、M8、M16均通过原owner全部score/output对照。
- 进行中：实际receipt证据独立复核与下一份M128分块profile准备。
- 待做：单独实现M128的16-key QK分块、M17边界与M32有界校准，再审查M128预算。M4首次观察器失败保留；本profile当前仍拒绝M128。

此profile复用attention_bank_scratch的原controller、实际ParentLoan/Banks、accepted-operation callback和完整债务。AST转换检查精确source SHA，只改 `integer(tokens,1,2)` 的上界；独立入口仅接受1/2/4/8/16，绝不把128次M1当M128。旧候选文件、Public运行和硬件源码均不修改。

## 观察存储与原oracle

Candidate的read_events/ack_events/views/scratch.events变成固定schema SHA256/count sink，仍执行每个原append；不保留逐edge历史或旧TileView引用。语义状态、银行payload、accepted operands、response与metadata没有削减。

Oracle继续执行实际原OfficialAttentionOwner AST及原 `_matrix_step`、原Fraction FMA/Scalar。仅将requests/reads/writes和Scalar trace观察历史改为流式hash；最后两个Scalar事件用于检查BF16→scale→BF16边界，完整dots/scores/output只作为oracle观察。M1/M2逐字、全观察hash及计数回归保证该存储优化没有删掉操作。

## 首次 M4 失败与修正

首次M4原oracle完成（0.607秒），candidate的旧观察器随后抛出 `original QK boundary`，被accepted Scalar packet正常转换为NumericalFault。原因是错误复用了原逐key BF→mul→BF邻接检测器：packed多lane会先执行多个mul再转换BF。该失败不证明算术不等价。

新候选只hash全部Scalar操作，完整score由实际Result与原oracle比较；原oracle的严格边界检测保持。相同M4固定输入回归复现旧故障，并验证新hash观察与普通trace记录产生完全相同Result、packet计数、时隙及事件hash，且全部score/output匹配原owner。首次失败JSON保留；独立审查后一次修正M4、一次M8和一次M16正式校准均已通过。完整原始receipt见相邻 `attention_bank_multirow_evidence`，执行源pin为d2508047…fef5d5；此后仅更新本说明和对应pin，不改变执行代码。

## 数值校准而非性能验收

校准输入为固定seed的合成有限FP32，native arithmetic=false。runner一轮执行一个原owner多行job和一个candidate多行job，比较全部score与输出，检查完整请求与bank账本，再校验所有源hash无漂移。摘要仅hash/count/time，不含tensor/weights。

Opt-in runner内部定时器1..60秒；首次M4/M8另加外部30秒超时。M16已依据M8测量采用同一内部25/外部30秒上限，receipt总13.550秒、CPU13.544秒、peakRSS66588KiB。超时/异常返回非零、FAILED_CALIBRATION；不继承旧PASS、不增加M128执行许可。没有worker子进程或新编译。

对于M16，预期P=1632，packed Matrix1808步骤、原legacy26112请求，scratch11424事务/34274最小服务edge。这里只验证同一原计算图的真实多行执行，不是hardware cycles。Q/K/V输入、最终输出、Chisel scratch/mux/staging lease仍待物理放置和连接；整块SiLU成本、4096MAC分母和80/90%未通过状态不变。

## 复现

`python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_multirow.test_profile candidates.qwen2_resident_matrix.attention_bank_multirow.test_oracle candidates.qwen2_resident_matrix.attention_bank_multirow.test_runner -q`

同一命令加 `-O`；源门：`python3 -S -B -m candidates.qwen2_resident_matrix.attention_bank_multirow.check_sources`。

已审查的校准命令示例（不自动重跑）：`timeout --signal=TERM --kill-after=5s 30s python3 -S -B -m candidates.qwen2_resident_matrix.attention_bank_multirow.run_calibration --rows 4 --seconds 25 --output /tmp/m4-calibration.json`。
