# 当前统一验收目标（2026-10-06）

本报告落实用户对两个项目的一致目标；此仓库独立保存和验收自己的证据。
目标为 Qwen2-1.5B、Qwen3.5-0.8B、Qwen3.5-35B-A3B 的典型完整 block。
每个必需 block/workload 必须同时满足实际生成 RTL 全量数值/状态通过，以及整 block 有效 MAC 利用率至少 90%。
源码、HLS、E0 模型、组件 canary、旧合成回执均不能代替这一最终结果。物理时序/功耗仍单独报告。

## 当前来源与支持边界

- Qwen2-1.5B：既有精确身份为 Qwen/Qwen2-1.5B-Instruct，保留 Instruct/Base 区分。固定 revision/config/framework 哈希记录在 `config/qwen2_1p5b_target_shape.json`。沿用 B2_DENSE 的完整 Attention/SwiGLU、Norm、bias、residual 与 KV 提交边界；现有合成几何通过不代表当前官方 checkpoint 或 90% 通过。
- Qwen3.5-35B-A3B：已有 `config/model_profiles/qwen3_5_35b_a3b.json` 与 `reports/execution/QWEN35_REFERENCE_LOCK.json`。后者仅 metadata，明确没有权重和数值 RTL 通过。需要 B35_ATTN_MOE 与 B35_GDN_MOE，包含 routed/shared experts、route 与必要状态。固定原字节和当前权重来源仍需复核。
- Qwen3.5-0.8B：U00.1现已新增 `config/model_profiles/qwen3_5_0p8b.json`、固定revision/config/forward/index原字节，以及显式dense-FFN的几何、算子/状态/调度入口。H1024、FFN3584、24层与3:1 GDN/full-attention已由官方来源核实；典型层0/3分别为GDN+dense-FFN、Attention+dense-FFN。U00.1当时仅完成来源/几何E0；后续层3真实payload及官方合成输入forward见文末，实际RTL仍未执行。最初来源、拒绝测试和剩余门禁见 `doc/U00_1_QWEN35_DENSE_GEOMETRY_20261006_CN.md`。
- Qwen3.8：保留历史研发任务、六类 inventory 和原证据，已从当前必需三模型及派工队列排除。它不能替代 0.8B；旧 R00、整网/视觉/MTP 发布不代表当前 U01 通过。

## 利用率及同源门禁

当前可复用的主计数口径来自 `src/heteronpu/block_performance.py`：

`Matrix useful MAC / (该次生成RTL固定配置的Matrix MAC每拍 × 整block wall周期)`。

- 固定资源数来自本次实际 DUT manifest，不能换成活跃 lane 数，不能混用 4096-MAC、512-MAC 或其他项目的配置。
- 从 block launch 握手接受起，到最终输出和必要状态写 ACK 全部完成止。descriptor、DMA、内部 stall、阶段间隙、padding 与 drain 都必须在分母里；不得只截 Matrix 发射窗口。
- 原计数器包含额外启动空拍的历史记录保持原值。新增回执要保存实际起止事件，不能从旧数据中无依据扣掉周期。
- executed MAC 利用率、useful/executed 和 active-window 可旁报，不能替代主门禁；padding 不能算 useful MAC。
- Matrix 与 Vector 单列。Vector 需冻结实际单元数、MAC/非MAC操作单位和计数来源，同用完整 block wall 范围。现有 SiLU `usefulMacs=0` 不能证明 Vector 利用率，非MAC操作不能折算进 Matrix 分子。
- 数值与性能必须绑定同一 model revision、官方 config/forward、layer/block、batch/query/KV、dtype/精度策略、权重/输入/初始状态、cache/内存条件、生成 RTL、source/tool 哈希和资源配置。
- 必需性能 workload 集合在执行前冻结；0.8B合同、token集合、路由/初始状态或Vector计数未确定的地方标明 BLOCKED/未测，不能事后只挑最好长度或用其他模型代替。

## 不能被旧结果掩盖的差距

现有 Q2 冷 N16 两层归档为 1,498,202,112 useful MAC / (4096 × 16,639,515 cycles)，约 2.198%。
98.30% 是 useful/executed，绝不是整 block 利用率。不改变流量及该通道假设时，理想上界约 11.824%，也低于 90%。
来源为 `reports/execution/BLOCK_CHECKLIST_ADVANCE_20260917/P00_1_counter_audit.json`。不改旧记录、不降低新门限；需要实际数据面/复用/映射改善后重验。

MoE 必须增加真实路由 histogram 与实际 tile 映射可达性检查。以假设均匀路由为例，M128、Top8、256 experts 仅平均4行/expert；若另假设64行tile，行占用仅6.25%。
这是条件算例，既不是实际路由，也不是 hetero tile 配置。它说明仅重排调度未必足够，需实测小M映射/packing与固定资源下的 useful MAC；不得把padding计入有效工作。

## 计划与清单落点

- `doc/three_model_typical_block_closure_20260917_zh.yaml` 的“当前统一验收目标”优先于历史六类发布范围，修正 G8/性能目标旧表述。
- U00拆为U00.1“0.8B来源与dense-FFN几何”以及U00.2“全部三模型回放workload冻结”；本次只关闭U00.1。U00仍ongoing，U00.2已ongoing，U01“三模型典型block数值及90%联合验收”仍to do。
- `doc/block_checklist.yaml` 更新计划 SHA，保留所有已完成子项及原证据；当前队列排除历史 Q38/R00/F00/F01。
- 计划校验器检查三模型、90%、实际RTL、固定资源/完整周期、Matrix/Vector分报、必需来源字段，以及U01不依赖历史Q38闭包。校验 PASS 仅代表文档合同一致，绝不代表硬件 PASS。
- C03.3 仍仅为 synthetic E0 shape/layout 与宽地址向量完成。C03.2、官方模型真实接入、三模型数值与90%尚未关闭；Chisel CI另跟踪实际运行结果。

## U00.2 本轮真实header证据（部分推进）

三模型的16个权重分片已通过HTTP206只读取原始header，归档321,392字节、2,637项tensor。两个Qwen3.5的index和全部header完全对应；Qwen2为官方单文件且无index。全部1,350项主文本shape与来源/几何一致。GDN A_log及norm.weight实际为F32，dt_bias为BF16；35B routed experts为packed三维tensor。

`config/workloads/three_model_m128_open.json` 将5个典型block绑定到精确header/config/forward，但仅继承batch1/M128；真实权重payload、输入、初态、逐producer精度、双参考、cache、MoE路由、实际Matrix/Vector资源及必需性能集合仍OPEN。严格模式必须退出2；不得从metadata PASS升级为U00.2完成、模型支持、数值RTL或90%。详见 `doc/U00_2_WEIGHT_HEADERS_WORKLOAD_20261006_CN.md`。

## U00.2 后续：真实payload与官方层数值已实跑

已实际取得固定0.8B层3全部11项payload（36,705,280字节），在未修改的固定官方DecoderLayer运行FP32及BF16。batch1/M128的空KV及past128两组采用不同确定性合成hidden-state；FP32对独立NumPy FP64的全部output/K/V共655,360元素零不匹配，输出最大绝对误差约5.04e-7。BF16为实际运行及精度差异诊断，未冻结其逐producer双参考。

合成输入不等于官方上游激活，逻辑KV空/已有不等于物理cache条件，软件层通过不等于RTL或90%。U00.2保持ongoing，U01不升级。来源、下载上限、完整运行数组、回归与剩余门禁见 `doc/U00_2_LAYER3_PAYLOAD_NUMERICAL_20261006_CN.md`。

## U00.2 后续：真实GDN层0及状态续算已实跑

新增固定层0的14项真实payload，共43,111,008字节。原始A_log/norm.weight保持F32、dt_bias等其余参数BF16；官方mixed-BF16执行时conv为BF16、SSM为FP32。官方FP32完整GDN+dense-FFN对独立NumPyFP64在cold128、carried128和补充decode1共1,123,328输出/状态元素零不匹配，整段256与128+128续算另有548,864元素通过；清零初态确实改变输出。

输入仍是合成hidden-state，mixed-BF16只报告诊断差异，不是上游激活、逐producer精度、实际RTL或90%验收。U00.2 ongoing、C03.2/U01未闭合。详见 `doc/U00_2_GDN_PAYLOAD_NUMERICAL_20261006_CN.md`。

## U00.2 后续：真实embedding到层3的上游链已实跑

新增0.8B真实embedding原0至255行和层1/2共86,746,304字节，复用层0/3固定payload。固定人工token ID经原官方TextModel前缀顺次运行embedding、GDN0/1/2、attention3，两组cold/carried M128对独立NumPy整链的4,210,688输入/输出/状态元素全部匹配；整段256重放另有3,219,456元素通过。逐层单独清空历史均实质影响结果。

0.8B前四层的真实上游激活来源已验证；人工token ID不等于自然语言代表性，前缀不等于完整模型，mixed-BF16差异仍仅诊断。逐producer精度、其余模型/MoE路由、物理cache及资源、实际RTL/90%仍OPEN，U00.2保持ongoing。详见 `doc/U00_2_REAL_PREFIX_CHAIN_20261006_CN.md`。

## 2026-10-07 BF16逐producer拒绝证据

新增 `doc/U00_2_BF16_PRODUCER_AUDIT_20261007_CN.md`：真实官方层2输出进入0.8B attention层3，cold/carried M128各57个producer，126项比较中本机9项超出原门限。最终output仅0.00390625不能覆盖QK最大1.0及carried norm失败。首处分叉定位到FP32 reduction与BF16中点舍入；18个条件local GEMM上界检查仅作诊断。官方eager RoPE逐乘积舍入与硬件v0 FP32 pair后舍入不同，明确不宣称硬件语义验收。新增可信保存夹具/同进程固定源码重建准入、softmax不变量和拒绝测试；CI绿灯仅表示证据收集及测试成功。U00.2仍ongoing、U01仍to do，无实际RTL或90%结果。

## 2026-10-07 独立 all-products-BF16 RoPE 硬件候选

`doc/U00_2_ROPE_BF16_CANDIDATE_20261007_CN.md` 记录四产品/末端BF16的两个独立命名RTL候选、明确转换异常位和非有限值合同、实际HardFloat生成与两套冻结native逐节点验真。原生产FP32模块和0.0625源精度反例保持不变。候选组件通过不切换生产策略，BF16 memory packing/store、QK256 Norm与packed gate、partial64/位置/cache、三模型完整block数值及固定资源整block MAC90%仍OPEN。

## 2026-10-07 后续：SharedL2 head事务候选

`doc/U00_2_ROPE_BF16_L2_CANDIDATE_20261007_CN.md` 将候选接到已有SharedL2 payload的默认关闭分支：head256/partial64、192维原位旁路、真实16位packing、跨beat掩码及实际fabric写回/读回。该有界head门禁与generic SFU owner、Command128全tensor入口、系数生成/cache、DMA/DDR ACK分别记录，不升级完整block或生产策略。先完成真实Q/K Norm及packed gate的producer/布局合同，再按依赖接通全tensor owner。U00.2 ongoing、U01 to do及固定资源整block MAC90%目标不变。


## 2026-10-07 后续：Q/K Norm256 与每头 packed gate 候选

`doc/U00_2_QK_NORM256_CANDIDATE_20261007_CN.md` 记录默认关闭的 chunked 候选：实际 FP32 gamma=1+weight、每 head256 归约/一次 NR、末端 BF16 和原始 gate 保留。新默认路径从固定官方 checkpoint 重建 baseline/AVX2 两套 producer，5120 个 head 观察值通过实际 RTL/整数/C 核对；新 native 有 7 个 BF16 差异，最大 0.015625，门限不变。本地历史回放另行通过，仍保留 15 个差异及 0.03125 边界。旧默认 64 事务等价和独立对抗/reset 复验通过。

权重及数值数组不进入 Git，CI 物化临时数据并只发布简短摘要；历史文件删除不清理 Git 历史。此同输入组件尚未接通 Matrix 真实 producer、Norm→RoPE、内存和全 tensor owner。完整 producer audit 的新 5/9 项拒绝仍保留，U00.2 ongoing、U01 to do，完整三模型 block / 固定资源 MAC90% 继续 OPEN。
