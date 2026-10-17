# 原 Qwen2 完整 M128 RTL 基线：只读审计与首个窄接线提案

日期：2026-10-17。审计目标 main c70315949dbc3c129b9690ced83f9228a98dd3fe。
未改工程源码，未组合补丁、编译、仿真、运行数值或 EDA；仅阅读源码及生成本报告/身份清单。

## 结论

已有完整原 Qwen2 Host/owner/causal Attention/resident FFN 的源码组成能力，但没有已经闭合的同 model27 算术顺序完整 RTL 入口。official BF16 补丁不等于 QKV split-K 已接入生产 kernel。最短功能路线是先补现有 QKV reduction 接线，保留原 Attention，随后做完整原 Host RTL 同刺激数值基线。无须先完成 packed Attention；也不能把此功能基线升级为 80%/90% 性能路线。

本报告九个关键文件已经由认证 GitHub fetch_file 在固定 commit 读取返回的 Git blob SHA，与本地完整字节按 Git blob 规则重算逐项一致。REMOTE_BLOBS.json 保留路径、链接、远端 blob、本地 blob、SHA-256 和匹配结果；九项全 true。其他辅助文件来自同工作区已有镜像，未逐一远端重证。

## 现有路径、容量与政策

official_bf16/chisel_policy.patch 的 Qwen2NumericPolicy.checkShape 要求 H1536/F8960/heads12/kvHeads2/headDim128/maxTokens1024，非 native。HostBlockTop 还要求 pipelined、resident FFN，并关闭 bf16V/Qkv/Gdn/QkNormRope/AttentionCore。resident 要求 transposed Down、tile/window/drain 和 non-overlapped SiLU。Matrix 为 retained、256 columns，即固定4096 MAC/cycle。

HostBlockCommands 的 officialRoleOK 在首命令接受 m16 或128，后续绑定 officialRows。因此 maxTokens1024 是容量，不是执行1024 tokens。Qwen2Block.scala 的 scores/probs 各 SyncReadMem(maxTokens, UInt32)：1024容量共8 KiB，128容量共1 KiB，差7 KiB。原功能路线保留这8 KiB；不能为避 guard 直接改成128，也不能把它混算成 packed raw scratch。其他 SRAM/寄存器以完整 elaboration 统计，不由叶子推导。

OfficialBf16Elaboration.scala 仅 parser、单lane SiLU、小 elementwise 的 CHIRRTL。check_frontend.py 明确 full Host/kernel/core/Matrix 未 elaborated、无 RTL/数值。EmitHostBlock 默认 LegacyV0，没有完整 official-resident-splitK 选择。Qwen2Block 已有完整多token/head/key循环；Qwen3.5 M1 profile 不适用于此结论。

## 与 model27 的算术对应及缺口

1. QKV：dense_block_reduce/profile.py 固定 [0,1024)、[1024,1536)，pairReverse=true。各 partial 独立 FP32 FMA，原K/N地址步幅不变，不做prefix seed。随后同SFU Vector loan做一次 FP32 Add，再由下一 public Bias 加 bias、BF16 RNE。不能提前 BF16、不能换普通 increasing-K Dense。
2. Public21DispatchHarness.scala 按 tag低16位PC1/4/7及完整 shape/dtype/writeBytes选择上述 reduction；但 ordinary/resident/window/drain/tiles/vector/backend fences 全为外部服务口。source_audit.py 显式断言 kernel 没有 DenseBlockReductionCoordinator，production_kernel_reduction_connection=false。
3. PublicDenseReductionHarness 已接真实 coordinator/bridge/Down owner/Vector loan，但普通job禁用、Matrix/DDR仍是外口，仅CHIRRTL。不可复制整个 harness 到kernel，否则会重复银行和算术资源。
4. RMS：official补丁保留原行缓存，V8/ILP4/three-block顺序，mean Div1536、epsilon、sqrt、reciprocal；normalize和gamma输出分别BF16。RoPE表、每个乘积、每个和分别BF16，不融合FMA。
5. 原 Attention：每dot八次深度累加、16项ordered FP32 fold，完成dot BF16、scale0x3db504f3、score BF16；score及maximum同值。softmax保持FP32按key累加；PV Matrix入口概率BF16，完成PV BF16。原与packed调度不同，但每输出依赖顺序可保持。
6. Dense最终舍入仅PC13/16/17/19；QKV raw例外。Down四段0..2560..5120..7680..8960之间prefix原样FP32，只最后完整输出BF16。FFN Gate→Up→SiLU→Act drain按160列window、实际m16/m128，全window ACK后下一window。
7. SiLU phase4 BF16后由phase5消费，再phase5 BF16；residual Add最终BF16。Elementwise Copy不应顺带舍入。
8. 有限常规数值顺序对应不等于全异常等价：模型vector默认与legacy Scalar Add/Mul的underflow接受政策不同；F32.bf对NaN canonicalize，模型保留nonfinite bits。已有27门也不能覆盖未闭合full29/mask/FP32tol。

## 首个最小接线补丁提案（待root审阅，不实施）

建议单个默认关闭 enablePublic21QkvReduction 选择，限定 official/resident/transposed/pipelined 配置。保持原 HostBlockTop 作为生产顶层、原命令ABI、原DMA和AXI端口。新增的只是kernel内一份 DenseBlockReductionCoordinator（其自带一个既有 DenseTileSumBridge）及小控制demux，不引入新顶层或第二套owner。

### A. 选路位置和锁定

- 在 QwenOwnerKernel 接受 io.job 的边界拦截PC1/4/7，复用 Public21DispatchHarness 的完整 qkvShape 和范围绑定。Host parser已验证所有21角色/地址来源；不能只凭k/n猜测角色。
- reduction job直接送coordinator.dense.request；不同时送dense.job。ordinary仍沿旧choose/mode；resident仍沿旧group口。
- 保存一份事务归属（ordinary/reduction/resident）直到对应最终result被接受，不能按瞬时window.busy切换返回目标。reduction result通过原io.done返回Host，保持tag/status/bytes/MAC计数。
- 不要把reduction事务复用成旧ordinary active=true：现有window/tile可用条件依赖 !active，这会自锁。使用独立reductionActive，并把它仅加入ordinary/resident准入排他。
- 同拍只允许一个入口fire。非活动服务结果不得被当成合法完成；stray response触发sticky fault并阻止继续发新工作。

### B. 共享服务接口

- 现有唯一 TransposedDenseDownOwner 显式开启 enableKWindow 与 enableDenseDrain；启用既有k_window.patch/dense_drain.patch。
- window：FfnWindowPort(enableCounters=true,enableKWindow=true)，在resident和reduction之间进行全握手demux，包括request/result、busy/reset、invalidateLease。resident普通窗口补 kWindow.enabled=false，其余新增字段明确置零；不得让旧resident隐式继承partial策略。
- drain：同一 FfnDrainPort 的 request/result/busy/abort/reset 双向选路，反压时归属固定。
- tiles：同一 FfnTilePort(enableMatrixProducerOrder=true)，control/read/write及各response、leased/drained/busy/abort/reset全部随租约归属选择；sumBankGranted只在真实owner退休后允许bridge访问银行。
- vector：同一16-lane SFU的 FfnSiluLoanPort(enableBinaryAdd=true)。现有 vector_add.patch 只修改 VectorSiluOwner/SiluVectorUnit及loan类型，没有把参数穿过 ScheduledSiluOwner/SiluOwnerPort；首补丁必须补这一默认关闭透传。resident SiLU显式 binaryAdd=false，reduction sum=true。不能新增一份VectorSiluOwner。
- Matrix：继续原 MatrixPipelineService 和 dense.matrix/legacy client仲裁；window.busy已有useDense选择，可复用，但必须保持直到实际done/result债务结束，不在abort时提前切回legacy。无需第二个Matrix客户端算术单元。
- DMA：继续owner.burst/burstResponse及writeRequest/writeData/writeResponse，不新增iDMA。注意seed/prefix读也经过现有burst，必须计入未退休义务。

### C. handoff与真实drain

- 原residentHandoff已用于HostBlockTop更新完整weight window和dma.flush。新增reduction handoff应排他复用该内部通道（可以明确重命名为通用ownerHandoff），保留full job的b/n/k，不能改成partial K范围而缩窄公共地址验证。
- coordinator partialFlush/drainFlush产生handoff；在下一request发出前完成原window更新/flush。ordinary job.fire、resident handoff、reduction handoff不许同拍争用。
- Matrix debt由已接受group直到真实done.fire；确保该done契约包含result消费，不用步数推断完成。DMA read debt由burst.fire直到对应response.fire；write debt从writeRequest.fire经过所有writeData直到真实writeResponse.fire。不能用请求valid消失或score ACK代替输出写ACK。
- owner内部operand FIFO、SyncReadMem返回、seedOutstanding、burstOutstanding、held result、lease等还须通过原window/drain busy及tiles/vector drained共同约束。PublicDenseReductionHarness的三个outstanding位可作接线模板，不能假设它覆盖未接入的所有通道。
- coordinator.backendReset只接独立DMA/hub错误或寄存后的共享错误；禁止自身resetRequired组合反馈abort。abort停止发新请求、排空已接受义务、保留held结果payload；同拍abort/result-ACK不得发布成功。所有参与模块保持统一reset域。

### D. 补丁边界/为何仍不能称完整基线

第一片只闭合production kernel QKV reduction和共享服务；原Attention及数值算子不改。默认off必须保持既有路径，不能夹带SFU提速、packed scratch或容量修改。基于当前overlay完成全源码组合仍需单独审阅。之后才添加原Host的明确official emission profile，以及canonical memory/reference测试台。首片的控制测试通过只能称接线协议通过。

## 最小验证清单（仅计划，未运行）

- 既有 official_bf16/test_chisel_policy.py：RMS图、输出舍入、policy透传、默认Legacy、无新增算术/存储构造。
- 既有 dense_block_reduce/test_k_window.py、test_matrix_binding.py：两partial完整覆盖、pair reverse、无seed、raw partial。
- test_sum_tiles.py、test_vector_add.py、test_dense_drain.py、test_public_coordinator.py、test_mode_sequence.py：三tile、共享Add、最终ACK、模式切换/异常drain。
- qwen2_public21_binding/test_source_gate.py、test_control_gate.py 和 Public21ReductionDispatchControlSpec：已有M16/M128/relocated程序，window_tag、drain_short、held_reset、abort_pending、future_score/probability、fetch/typed/scan/ordinary/resident abort、stray resident等。
- 新增实际生产kernel选路小harness：默认off与旧路径不变；QKV→Bias→Attention→resident→Down反复交接；sum期间resident/ordinary禁止准入；binaryAdd在resident为false；读/写/Matrix末ACK长背压；所有handoff反压/flush/错误同拍；检查一份Dense banks、一份Matrix service、一份SFU16、一个iDMA，无新增payload SRAM。
- 复用 PublicReductionElaboration/check_public_reduction_frontend.py 的结构/端口证明，但不能以CHIRRTL或用脚本响应的控制test冒充真实算术。
- 小控制片完成后才授权完整elaboration/RTL算术。先以canonical manifest固定输入/权重/表、模型观察值与外部reference身份，再完整M128运行。

## 原测试台与运行风险

tests/host_block_commands.cpp 的 initialize只读取host_commands/host_descriptors，之后自造weight/input/rope并算legacy oracle。其Dense increasing-K、RMS及BF16边界不等于当前model27。可复用AXI-only memory、只读保护、ACK检查、completion/fault框架；必须改为canonical payload装载与独立reference消费，并按resident/partial行为修正owner数/元数据读取/写字节断言。不能把reference作为DUT读数据或注入中间tensor。Attention虚拟观察值需观察hook，不新增硬件authority。qwen2_block.cpp的arena入口也不是原Host21路径的替代。

## 性能界及后续SFU

M128 causal query/head/key组合=12*128*129/2=99,072。原Attention每组合8QK steps，PV总计也8steps/组合，合计1,585,152 Matrix steps；packed候选是71,808。Qwen2Block每step等返回，实际更慢。

固定useful=6,014,828,544，peak4096，理想有效周期1,468,464。即使每原Attention step只1cycle、Dense满利用，Dense还至少1,462,272cycles，总至少3,047,424，利用率上界约48.2%，尚未计Scalar/SiLU/DMA/控制。功能基线因此完全不满足80/90。仿真wall无法由CPU模型推算；完整Matrix和串行scalar、重复DDR交易意味着高运行风险，应有进度/阶段计数，不随意宣称短时完成。

SFU16原BlockScalarFloat仍是DivSqrtRecFN_small(8,24,0)。71,680 SiLU vectors*最优正常division25cycles=1,792,000，单divider吞吐理想上界81.9455%；官方BF16边界不改变此界。现有resident Gate→Up→SiLU→drain串行，因此真实整块更差。

90%必需提升division吞吐或证明等价地消除相关工作，光去wrapper空拍不够。已审计options16候选14cycles、仍16实例，但增加第二trial/subtract/select组合逻辑，面积/关键路径须显式计账。随后需要微序列、合法context及bank/FFN-Dense重叠；full-exp非division22states*71,680=1,576,960已接近90%预算1,631,626又2/3。options16单独也不保证90。当前Python SiLU候选、类编译、协议PASS都不是实现/数值/STA验收。

## 交付

REMOTE_BLOBS.json：九项固定main身份，全部匹配。REPORT_CN.md：本审计及待审方案。没有创建工程patch；root审阅前不编码。
