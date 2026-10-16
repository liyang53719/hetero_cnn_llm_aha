# 现有 ALU / SiLU 资源的有序调度准备模型

## 中文计划与当前边界

- 已完成：读取现有16个 vector FP32 ALU、16个 SiLU Scalar core、单 owner/mode 以及现有 BinaryAdd loan 源码；固定源码身份。
- 已完成：22项元数据时序/争用测试 normal/-O通过（作者0.016/0.041秒；独立审查0.017/0.039秒），7个源文件+4个本目录文件身份检查通过；独立审查完成。
- 进行中：下一独立候选将把实际数值回调接入接受/结果/ACK时序，先验M1/M2原owner score/output；本目录不继承其未来结果。
- 待做：真实 borrower mux、exception flags、BF16边界、payload稳定性、bank布局与供数、Matrix/result credits 的联合时序、完整块数值与 RTL 验收。

本目录是单独的调度提案，不改原 owner 或已发表的 attention_matrix_batch。它不执行浮点运算、不生成 RTL、不调用 native library，不证明实际新增 mux 能满足任何频率。现有16个 vector ALU并没有通用外借端口；SiLU16 cores目前固定执行六阶段，已有候选只扩展 BinaryAdd，任意 Exp/Div 外借仍未实现。

## 实际资源和时序来源

路径前缀 `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/`：

- `Qwen2Block.scala:128–130`：16个 `HeteroFP32Alu`，共用 vectorMul 控制；Norm(:317–328)、RoPE(:456–461)、Bias(:512–515)使用同一组。当前只路由 out，复用需补原 Scalar flags/error规则。不能同时给这些 owner 与 Attention记账。
- `BlockFloat.scala:55–108`：Add/Mul edge0接受、edge1运算、edge2结果ACK、edge3下一次接受，即最小请求间隔3。完整Exp为20，|x|≥80截止分支为3。Div经 inReady/outValid，模型必须由调用者显式提供服务间隔，数值不来自该模型的预测。
- `VectorSilu.scala:34–65`：16core，allReady/allValid锁步。快速Exp lane必须等最慢lane，不能独立提前再用。阶段原序是exp/add/div/mul/mul/mul，保持每次独立舍入；本模型仅记录这些阶段。
- `QwenOwnerProtocol.scala`：active/mode排他。`ffn_tiles/tile_ports.patch`要求non-overlapped SiLU；`dense_block_reduce/vector_add.patch`只提供BinaryAdd。全局租约覆盖attention/dense/norm/rope/bias/ffn，杜绝默认跨owner重叠。

## 模型协议与保守假设

`Schedule`最多16条有序chain，每chain最多1024项，最多一份accepted packet；两个资源池也不同时issue，属于有意保守的proposal。一个packet最多16lane，必须相同pool和opcode。不同head/key可并行；每个输出自己的fold、key和softmax累加顺序不能交换。短尾仅列出有效lane，不证明真实无效lane故障屏蔽。

- 接受、结果可见、匹配ACK、下次issue是不同事件。响应仅是不可变metadata（packet/owner/pool/opcode/chain/index），没有数值payload；held测试不证明16lane数据保持。
- 使用pre-edge债务和ownership。ACK同拍不能再issue；release必须在先前边沿已经无债务，release同拍不能重新acquire/issue。foreign ACK不退休。
- abort/soft_reset立即阻止新工作但保持accepted debt、owner和held metadata；matching ACK仍可排空，publish=false。poison跨release保持，没有恢复协议；coordinated cold reset和实际后端取消仍待实现。
- `feed_ready`只是显式外部前提。False不接受，True绝不等价于bank无冲突/有足够带宽。这里没有新增SRAM或声明任何buffer已能装入现有银行；Python plan/metadata为host对象。
- Vector原始ALU是组合输出。本proposal保守假设下一edge有registered capture/ACK，再下一edge才接受，因此spacing=2；它不是原 RTL latency测量，也不是已经实现的1cycle流水线。
- Scalar spacing包含即时ACK所需时间；反压会继续占用资源。异质Exp同一packet取最慢lane。显式divider spacing只是被测试场景的输入，未验证为HardFloat实际延迟。
- `softmax_plan`保持按key的subtract/exp/sum、每row一次reciprocal、按keynormalize。max比较、BF16 materialization及payload依赖由后续真实控制器负责；至少一个exp(0)全路径被强制。输入分支必须由真实值产生，本模型不猜分支比例。

## 整块工作量，不能从Attention局部推导80/90

M128有99,072 causal pairs、1,585,152 QK fold adds、110,592 vector fold packets及6,912 scale packets。依本保守2spacing proposal仅fold+scale便需至少235,008时隙，尚无operand/result/Matrix等待。Softmax还有99,072 subtract、exp、ordered sum、normalization，以及1,536次division。这里normalize采用已准备的packed PV广播复用，每pair一次；原PV16循环每pair重复8次（792,576次），模型另列legacy_pv_normalization_calls，不把调用减少误写为已实现RTL。

整个FFN SiLU有128×8960=1,146,880元素，即71,680个16lane向量、6,881,280个lane操作和1,146,880次division。即使所有Exp走cutoff并把division费用暂时剔除，原core服务占用仍至少15×71,680=1,075,200；全部完整Exp时32×71,680=2,293,760。向量wrapper、bank/DDR、ACK、divider都还未计入，不能把这些下界当完整wall cycles。

整块6,014,828,544 useful MAC分母保持不变；此模型不返回实测周期或利用率，accepted_80/90恒false。无Dense/Attention重叠、无免费SFU、无省略SiLU后声称整块效率。完整联合schedule和原数值比较仍待做。

## 复现（标准库，短测试）

从仓库根目录运行：

`python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_scalar_schedule.test_model -q`

`python3 -S -B -O -m unittest candidates.qwen2_resident_matrix.attention_scalar_schedule.test_model -q`

`python3 -S -B -m candidates.qwen2_resident_matrix.attention_scalar_schedule.check_sources`
