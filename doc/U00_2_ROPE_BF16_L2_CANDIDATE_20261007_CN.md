# U00.2：默认关闭的 BF16 RoPE SharedL2 消费门禁

本轮把上一轮独立算术候选接到已有 `qwen2_shared_l2_rope_payload` 的真实内存消费接口。没有新建无关顶层来替代既有路径。默认参数 `EXPERIMENTAL_BF16_ROPE=0` 保留原实现；启用候选还必须在每次请求明确提供 `candidate_policy_i=0xb1`。这不代表用户接受新的生产精度策略。

## 接口审计与本轮边界

当前存在三条不同实现，不能混为一条：

1. `operator_sfu_rope_endpoint_v3` 每次处理8对相邻FP32输入，经SFU owner的512位scratch/final buffer返回；没有head维度、byte mask或真实存储器连接。
2. 本轮实际接入的SharedL2 payload原本服务Qwen2的head128和位置递推，已有BF16读写接口。原生产body保留逐字节身份，候选使用独立generate分支和明确的系数地址。
3. `Qwen2ContinuousBlock` 的owner-driven Chisel路径仍是另一套内联FP32向量mul/add与FP32存储。

本轮仅关闭显式候选的有界head事务搬运/存储测试。原Command128 descriptor目前仍拒绝head256；generic SFU owner、Q8整tensor调度、DMA/DDR最终ACK以及完整block均未据此接通或验收。

## 数据及数值合同

合同见 `config/upstream/qwen3_5_0p8b/rope_bf16_l2_candidate_contract.json`。

- 仅支持1或2个head、head_dim=256、rotary_dim=64及严格对应的8/16个源beat；其余配置在发出任何读写前返回错误。
- 源张量为head连续的BF16，每512位beat包含32个16位值，最低16位为第0个值。输入地址64字节对齐。
- 候选系数地址另指向两拍BF16：cos[0:31]及sin[0:31]，在两个head间共享。没有静默重用旧position地址，position/coefficient_steps输出为0。
- 每head按(i,i+32)、i=0..31配对，BF16零填低16位进入原候选FP32算术，四产品BF16及末端BF16合同不变。真实16位输出直接写入BF16 buffer，没有第二次转换。
- 64..255维共192个值逐位搬运，不经过浮点计算或NaN规范化，不贡献异常位。两套历史冻结夹具只覆盖旋转段；这192维的回放数据明确标记为合成对抗传输数据，包括±0、Inf、qNaN/sNaN payload及随机所有16位编码。
- 输出允许任意偶数字节偏移。对齐时8/16拍，非零偶数偏移时9/17拍；首尾byte mask精确，只写有效BF16的两个字节，未使能字节保持原值。

没有重新运行模型来制造本机expected。所有163,840个唯一真实pair及327,680个native输出直接来自原hash固定local/remote夹具；分组2-head的补充回放单独计数，不能重复算作新的真实来源覆盖。

## 地址、所有权与完成

请求仅在IDLE接受，地址/配置一次捕获。忙时start脉冲被忽略；没有新增可排队或带tag的command接口。完整源张量及两拍系数均读完后才开始写回，因此本轮支持源/目标重叠。每次读仅一笔在途；所有写数据、地址、掩码先寄存，背压时稳定。

使用65位exclusive-end计算拒绝截断、溢出和越界。独立review发现默认ADDR_W=15提供2MiB编码，但真实默认SharedL2仅4×6144拍=1.5MiB；已新增匹配真实fabric容量的参数，默认拒绝0x180000以上未实现区域。较小地址宽度默认全容量，非默认fabric必须明确匹配实际拍数。

read计数为接受的读请求，pair计数为完成的算术输出，write计数为接受的写拍。成功done仅在最后一拍SharedL2写握手后出现一拍；继承接口没有completion ready，调用方必须观察该脉冲。不能把它称作DDR ACK。

reset必须与无ID的fabric及其待响应路径同时复位，并跨至少两次上升沿。它清除在途事务和写valid，但已经接受的写入仍可能留在目标内存；不声称事务原子回滚或单独复位consumer后的旧响应免疫。

## 实际验真与下一步

runner为 `python scripts/run_rope_bf16_l2_candidate.py --output <fresh-dir>`。每次重新clean/compile/emit固定Chisel/HardFloat，并校验源、依赖、manifest和生成RTL hash。DUT通过实际 `shared_l2_fabric` 的公开端口加载数据、masked store与读回；testbench不直接修改其内部memory。

测试逐拍比较读请求、响应、实际写地址/掩码/数据、异常位及完成计数，并读回源/系数/目标及poison guard所有触及字节。另有输入空拍、读/响应/写背压、请求捕获后配置扰动、忙时start、1/2-head切换、32种偶数字节偏移、前后重叠、非法配置、容量边界和协调reset。Python独立byte地址打包再次读取完整真实RTL store trace，拒绝缺失/重复/重排/错误掩码/提前完成。默认关闭分支单独实际RTL测试。

完整命令、原始store trace、张量、mask/data数组、结果及生成原语进入对应CI artifact；仓库只保留小型摘要、hash、日志和独立review。证据目录为 `reports/execution/U00_2_ROPE_BF16_L2_CANDIDATE_20261007/`。

下一门禁仍是Q/K256 Norm的1+weight、packed Q/gate4096→2048的真实producer/布局，再把head事务接入明确的全tensor command/owner和状态/ACK路径。系数生成与cache语义仍需独立同源验证。三模型完整数值和固定资源整block useful-wall MAC≥90%继续OPEN；本轮不测PPA，不以standalone周期推导90%。U00.2 ongoing，U01 to do。

## 本轮实测结果

- 候选完整回放5,184个主事务：5,120个单head覆盖全部163,840个唯一真实pair，另64个双head补充4,096个pair重放。335,872个旋转输出（含补充）均与冻结native逐位一致。
- 1,007,616个合成旁路BF16值按原位存储；主事务实际47,006个512位写拍、2,686,976个使能字节，Python独立解码和真实fabric读回均无差异。全套含辅助事务总读回8,307,264字节。
- 38种非法配置、4类协调reset、全部32种偶数偏移、前/后重叠和边界合法请求通过。读请求/写/响应分别经历24,477/37,830/42,356次人工stall；这些仅为协议覆盖计数，不是带宽或最大吞吐结果。
- 独立review另对默认1.5MiB容量与显式512KiB容量分别执行15种非法地址及6种合法边界预读检查，均通过；检查停在首读请求，不冒称全量数据搬运。
- 默认关闭分支实际回放2个identity事务、128个旧FP32 pair；旧实现body含末尾换行共5,435字节SHA256为cf3a795524f71835c180d0f169fb9d3a83568bc0b4818c7df78849518c280511，和37df696原body完全相同。
- 普通及Python -O focused各482项通过；全仓2,483项通过、5项既有失败不变。第一次完整runner在testbench完成reset时点修正后正确拒绝“source changed during execution”；最终从新目录重新生成并完整重跑，所有源码hash稳定。
