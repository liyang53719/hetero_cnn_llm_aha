# 六头概率面板：寄存器借用与完整 64 B 传输审计

这是独立的索引、生命周期、运算顺序和必要成本审计。未修改正在运行的
`attention_bank_m128`；未实现新 datapath、借用端口或 RTL；未验证 80%/90%。
`source_pins.json` 固定本文依据，`M128_COUNTS.json` 可由 `constraints.py` 重建。

## 结论与资源边界

有条件可把 M128 score/prob scratch 从 7P = 693,504 次事务降到
4G = 27,648 次完整 64 B 事务。其中 P = 12×128×129/2 = 99,072，
G = 12×Σ[n=1..128]ceil(n/16) = 6,912。
条件是接通一个真实的 96×FP32 面板，并完成以下独占借用和控制器修改。
这个条件不能由“SRAM 容量够”或 Python list 的存在代替。

`chisel/continuous_prefill/src/main/scala/heteronpu/continuous/Qwen2Block.scala`
57、64、121 行，在 retained 256-column 配置中声明
`denseWeights=Reg(Vec(denseColumns,UInt(32.W)))`，共 256×32 bit。
其建议视图如下，所有视图必须指向同一个存储实例：

| 生命周期 | 字下标 | 载荷 | 冲突 |
| --- | --- | --- | --- |
| QK | 0..255 | 16 keys × 16 stripes 的 Matrix B | 独占全部 256 字 |
| Softmax | 128+16h+j，h<6，j<16 | 六头 score→原始 exp weight 面板 | 必须先结束全部 QK |
| PV | 128..223 | 同一面板的原始 exp weights | 跨本面板所有 key 保持 |
| PV | 0..127 | 当前 key 的 128 个 FP32 V | 与上面不重叠 |
| 非 QK | 224..255 | 不分配 | 不能偷作另一个隐藏 cache |

这是源级候选借用，**尚未证明该旧 core 的寄存器在目标物理配置中保留**。
`QwenOwnerProtocol.scala:75–77,109,150–151` 把 pipelined Dense 分发到独立
Dense owner；旧 core 的 Dense 路径可能被综合移除。发布“同资源复用”前须比较
实际选定配置的 emitted/synthesized inventory，证明对应 8,192 bit 确实已存在。
不能因为重新接线使死寄存器存活，就把新保留的资源算作免费。

若该 stage 不存在，可单独评审 **+96×32 = +3,072 bit（384 B）面板寄存器**
的资源版本。其 4,096 MAC/cycle 分母不变，但必须报告寄存器、mux 和控制资源增量，
不能称为同存储配置。这个 +384 B 只覆盖面板：当前 Q/K/V ingress 仍未完成物理
placement；若没有另一个已计入的 128×FP32 V stage，V 的 512 B 也必须另行计账。
若直接新增完整 256-word stage，则载荷增量为 1,024 B，不能只报告其中 384 B。
本审计没有实现任一新增资源版本。

## 必须改动的接线和保护

1. 全任务 register lease：仅在旧 core idle、Dense/DMA、bank、Matrix 和 Scalar
   的既有债务全部归零后获取；租期覆盖 QK、softmax、PV、最终输出 ACK，以及各
   请求之间的空隙。`Qwen2Block.scala:224` 的 owner-ready 目前没有这个 lease；
   不能只靠 `scalarExternalExclusive`（101–113 行仅单请求 busy）保护。
   同时禁止 Norm/RoPE/Bias/FFN/Dense 或其他 borrower 使用相同小寄存器/ALU。
   `QwenOwnerProtocol.scala:147–153,328–342` 已有全局 owner/memory 选择，须接入
   其准入及 drain/poison 条件，不允许另开 Dense 来隐藏面板成本。
2. 输入 stage 的受限写口：现有 359 行支持每拍 16 个 32-bit 字写入；需要新的
   64 B raw 响应→upper panel 路由、V 响应→lower128 路由，以及目标范围验证。
   **355 行 `denseWeights:=0.U.asTypeOf(denseWeights)` 是致命覆盖点**；借用时
   必须屏蔽整个原 Dense loader/clear，不能原样调用它来装载 V。
   整行读入先经过已有 dv[16] 运输暂存或在 ACK 边沿直接捕获进目标 16 字；
   两种实现都须明确捕获边沿和 backpressure，不得增加第二份面板载荷。
3. 现有 Matrix B mux `Qwen2Block.scala:163–166` 仅 Dense 选择 denseWeights；
   非 Dense 只有前 16 个 fmB。新 QK/PV 路由必须显式选择对应视图。PV A 从
   acc[0..5] 选择六头的归一化 FP32 值，B 从 lower128 选择 V，剩余 lanes/slices
   屏蔽；保留 Matrix ingress 的 BF16 RNE，不能把 panel 提前截为 BF16。
4. 六路 panel gather/scatter、16-word store view、写使能及选择 mux 是新增接线，
   不是新 SRAM 端口；其 fanout/时序尚未验证。cv[0..5] 保存 max，cv[6..11]
   保存逐 key sum，Div ACK 后原位替换 inverse；acc[0..5] 保存当前六头运算结果；
   tmp[16] 在 QK 用作 fold/score，dv[16] 用作 bank transport。原寄存器声明见
   `Qwen2Block.scala:95–96`。各读写也须纳入同一 lease。
5. 控制元数据须包含 owner/generation、query、KV-head、panel first/key count、
   六个 head 的 load-valid/commit 前缀、当前 key、lower V-valid、scalar-debt、
   Matrix group/context 与 step-debt、bank ACK key、poison。优先复用已有计数器和
   scratch 的 validity 元数据；确有新增 flip-flop 必须计账。full-vector clear
   只在 lease 外合法；切换 panel 先失效旧 tag，不可把尾部 padding 作为有效 key。

## 最小可实现串行调度

对每个 query、KV-head（六个 query heads）执行以下步骤。

1. 完成所有 head、所有最多 16-key 的 QK tile：每个 tile 仍是八次 Matrix
   stripe 累加，随后按 stripe 0..15 顺序 FP32 fold，再 BF16(dot)、FP32 scale、
   BF16(score)。tmp[16] 作为一个完整 score beat 写 bank，匹配 ACK 后发布。
   最大值按每头 key 递增从 tmp 观察，无额外 score 读取；当前实现来源是
   `attention_bank_m128/controller.py:56–82` 和 `storage.py:16–27`。
   等待最后 score ACK、joined result 消费及 Matrix group done，再开始 upper-panel
   借用；六头逐一 QK 的过程中不能保存其他头的概率面板。
2. 按 first=0,16,... 装入六个 head 的 score beat 到 upper96。随后按 j=0..count-1
   取六头同一个 key：通过已计时的服务执行 FP32 subtract、原 exp、FP32 sum；
   每头 sum 保持 key0→key(n−1)，不得 tree reduce。用 exp 结果原位覆盖已消费
   score 字。完成该 panel 后将六个完整 64 B raw-weight beat 写 probability plane。
   尾部无效字写零，不调用其 exp/sum。原始 exp 仍为 FP32，不能舍入为 BF16。
3. 所有 raw weights 都已 ACK 后执行六个 reciprocal，ACK 后 cv sum→inverse。
4. 按 first 递增读六个 raw-weight beat 到相同 upper96。按 j 递增取六个 weights，
   通过六条真实 SFU lane 执行 FP32 weight×inverse，把结果保留在 acc[0..5]；
   读取当前 key 的 V 到 lower128。两者完成后提交一个 PV Matrix step。
   Matrix ingress 执行原 BF16 RNE；每个输出保留 key0→key(n−1) 的 FP32 FMA
   顺序，只有最后结果执行 BF16。没有归一化权重的 bank 写回。
5. 前一步 Matrix 的已接受 step 返回/排空后才能覆盖其输入或处理下一 key。
   panel 边界不 clear/last；只在整个 PV 的第一 key clear、最后 key last/finish。
   当前 `attention_retained_result/controller.py:135–136` 禁止 active Matrix 时
   调用 scalar_phase，因此必须显式增加“同一 Attention owner 暂停 Matrix issue，
   排空已接受 step，运行 Scalar，恢复同一 group”的仲裁；不能临时置空指针绕过
   资源检查，也不能在 panel 间新开 group 丢掉 FP32 累加器。
   `MatrixPipeline.scala:68–84,119–135` 允许 unfinished context 等待并停止算术
   时钟；等待边沿仍进入总 wall cycles。此最小方案不假定 Scalar/Matrix 重叠。
6. 输出仍从既有 joined result slot 消费，输出写 ACK、Scalar/Matrix/bank debt
   全部归零后释放 lease。任何 accepted fault 都 drain+poison，禁止最终成功
   publish；重新安排 normalization 后的错误时间点须单独测试。

原始数值来源 `official_bf16/owners.py:128–159`：QK 16-stripe fold 不变；
softmax sum 递增；原 owner 本来就在 PV 每个 key 前执行 normalization，并对八个
column tile 重复相同乘法。packed PV 已共享这项确定性乘法。本方案保持其 FP32
结果及 ingress BF16 边界，但改变当前 bank candidate 的全行 normalization 先行
顺序。因此仍须做 M1/M2、16/17、M128 bit-exact 以及 fault/stall 对照，索引审计
不能替代数值证据。将 16 个独立 key 的 normalization 向量化可另行评审；本方案
仍六头同 key，一个接受/ACK 的 SFU packet，不使用免费 Python multiply。

## Bank 计数及未完成的性能账

当前候选 `attention_bank_scratch/port.py:13–17,86–101` 将 line 映射到
bank pair=(2(line mod8),2(line mod8)+1)，word=line//8；score=4096+8h+p，
prob=4144+8h+p，分别占 word512..517 和 518..523，合计 6 KiB。
同一个 panel p 的六个 head 全部命中同一 pair、不同 word，必须依次读六次；
不能称为一次六头读取。每个 64 B 请求实际占两个 256-bit bank 操作。
原硬件 patch `raw_kv/raw_kv_port.patch:37–59` 仍拒绝 line>=4096；上界4192
的 opt-in 扩展仅在 bank candidate model 中，实际 Chisel route 仍待实现。
同 patch 119–160 行体现既有单读/写调用和 raw/normal 互斥。

每头每 panel：score write + score read + raw-weight write + raw-weight read = 4。
M128 共 13,824 reads、13,824 writes；各为 27,648 次 256-bit bank 操作；总流量
1,769,472 B。没有 per-word RMW，也没有 normalized-prob writeback。匹配请求、
同步读捕获、响应 ACK 三边沿（patch 37–59 行；model port 70–100 行）给出单事务
最小 spacing3，因此 **82,944 service edges 是条件必要成本，不是总延迟预测**。
还没有计 Q/K/V 输入搬运、输出写、额外 register capture、mux timing、bank stalls。

固定 4096 MAC/cycle、useful=6,014,828,544 的 M128 预算：

| 串行最小项，假定本文路由可实现 | 累计必要边沿 | 利用率上限 |
| --- | ---: | ---: |
| Dense+packed Attention Matrix issue 与 scratch | 1,617,024 | 90.81% |
| 再计 fold+scale，候选 vector spacing2 | 1,852,032 | 79.29% |
| 再计六头 softmax，暂不计 division | 2,054,528 | 71.47% |
| 再计既有 FFN SiLU，暂不计全部 division | 3,129,728 | 46.92% |

这里 34G=235,008 是 16 次 fold Add 和一次 scale Mul 的 vector 服务必要数；
spacing2 是 `attention_scalar_schedule/model.py:24–38` 的保守建议，并非物理
已验证 II。六头 key-packets Q=P/6=16,512、六头 rows R=256，softmax 下界
12Q+17R=202,496：subtract3+exp至少3+sum3+normalize3；每组六头至少有一个
exp(0) full-path packet，额外17。全 exp full-path 时为29Q=478,848，另加
256×实际 divider spacing、包级获取/释放和等待。
`BlockFloat.scala:55–98,108` 证明 Add/Mul spacing3，full exp20、cutoff3；
`VectorSilu.scala:34,43–65` 的16个 core 被同一个 SiLU 调度占用，六阶段
exp/add/div/mul/mul/mul。M128 FFN 有128×8960/16=71,680个 vectors，
即使忽略所有 division 且所有 exp cutoff，仍至少15×71,680=1,075,200边沿。
这些条件下仅减少 scratch 无法达到80%。后续必须继续减少/合法重叠 Scalar/SFU
工作、输入搬运和其他 block 开销；保持原每输出运算及 rounding，并重新计入
新增路由/资源。任何“只看 Matrix+bank 得到90%”都不构成验收。

## 便宜验证

运行 `python -m pytest -q candidates/qwen2_resident_matrix/attention_panel_audit`，
以及 `python -O -m pytest -q candidates/qwen2_resident_matrix/attention_panel_audit`。
测试覆盖源哈希、保存报告重建、全128行的4G计数、边界16/17、六头 bank collision、
upper/lower alias、QK phase fence、clear hazard、accepted-debt释放和逐头顺序。
仅是审计约束验证，没有执行 native/RTL 或性能仿真。
