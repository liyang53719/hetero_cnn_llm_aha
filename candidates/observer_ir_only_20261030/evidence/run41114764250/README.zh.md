# run41114764250：原始 Chisel HIGH/LOW 与新增观察接口证据

## 真实结果与准确范围

source `97555642bee1b7a40047db8677d28f1f89185bce`，launch `ec198c27364fc537da06d6430bf27607d9865596`，attempt1。原始四份受控metadata逐字节保留，不改其中OBSERVED_UNREVIEWED / canonical_pass=false等声明。独立人工源码差异审计允许把本结果用作新canonical/LOW端口接受基线的候选事实；不等于SV、后端、完整数值或最终RTL通过。

九阶段native0/error0/complete。完整155源8覆盖Scala编译134.383487633秒（观测RSS1663705088 B），HIGH/official LOW 210.570589043秒（4158230528 B），descriptor29.056340970秒（2206941184 B）。原监督程序只有严格cleanup/EOF条件完整才将阶段标为complete；采样RSS不是连续峰值证明。

- HIGH：115925488 B，SHA256 `4c8260ff31d9d2c7e66ac66dede95b6d1b9f647b23606eeff356a7d6fbc51803`。
- official LOW：293360741 B，SHA256 `54a5095979077c541ac33861fd00203a735915c39d6852ef9e717ac83d6f6f45`。
- 完整canonical TSV：101108 B，SHA256 `00897fd49e82036e04195ef6fe2a671e0a3fd948d968de3e47c4dfa7388f6b5c`；circuit canonical `107bcbc0e17d430c2908666bdb750bcbc53b8b4caedc45ccbd9df612173ff872`。

此包不含HIGH/LOW、classes、annotation正文、原始日志或权重。metadata来自原helper实际LOW的hash绑定端口提取，不是本地重新解析完整LOW，也不是实际Verilator header验证。旧baseline位于candidates/ci_frontend_materialization_r2_20261029/fixed-canonical-baseline.tsv，保持原件，不覆盖。

## 独立差异审计

1056模块数量及顺序保持，恰8模块变化、1048个canonical hash逐项相同。8个变化为HostBlockCommandsV4、FfnTileSiluBridge、FfnResidentCoordinator、QwenOwnerKernel、UnifiedMoeRouterNumericalOwnerV2、UnifiedMoeRouterPipelineBindingV2、UnifiedMoeRuntimeExpertLoopV4、HostBlockTopV4。SOURCE_DELTA_PINS.json给全部8源old/new精确路径/bytes/hash。

逐源码差异只有新增观测Bundle/output、真实既有握手/数据输出、父级直连及in/out同时fire互斥assert。没有新增ready反馈、寄存器、SRAM读命令、算术、写回或原状态控制反馈；assert可在非法握手时终止仿真，不能把它当已覆盖回归。新电路增加观察输出与检查，因此不得称与旧电路整体语义完全相同。

实际LOW端口122：旧85个name/direction/type/width逐项不变；新增P0 27输出689bits、MoE10输出259bits，共37只读输出948bits。完整列表在observed-details.json。

实际annotations9022＝9021 DontTouch＋1 TargetDir。原8985条内容和相对顺序完整保持，只增37个Top观察target。重构raw1358737 B / SHA256 `ee6f1eb80ecf990a89e5c3457a14be74fb5e9ac5e0fa4789404e2d15ddc84dc9` 与去TargetDir后ordered SHA256 `8dd84536415d0f97aad603d1e0b9fbdadf8cae58a04d4ae5328105c9a844af39` 均和本次实际run一致。历史V1 partial只用作文本材料，不继承其运行终态/PASS。文件比旧本地IR小不能推断缩小硬件；路径SourceInfo差异只是合理解释，未量化分解。

## 重现与测试边界

reconstruct_annotations.py只读用户显式提供的P0 completed annotations、V1 partial annotations文本及R2已pin源，先核输入SHA，剥27/7恢复旧raw/orderedhash，再按真实顺序插last/rank/kind，最后必须同时符合本次raw与orderedhash。默认只写新summary；只有显式给--write-reconstructed-annotations才在本地新文件保存正文。全部open x，已有文件拒绝覆盖。历史输入不在本包内；可以依原source重建，但新环境生成也必须核pin，不能假定相等。脚本不会下载、运行模型/硬件、上传或授予接受资格。

命令参数：--p0-annotations、--v1-annotations、--r2-source、--summary-output，另可选--write-reconstructed-annotations。本轮原始已pin输入实际重构成功，raw/ordered双hash一致，没有写入或上传正文。

audit_artifact.py是可复现的只读metadata复核工具；仅把原审计的本地路径改为仓库路径，算法未改。--metadata指向仅含observed-canonical.tsv、observed-details.json、provenance.json三文件的解包目录；--summary指向原observer-ir-summary.json；--output为新的结果文件。实际四metadata重核的返回内容与ACTUAL_DIFFERENCE_AUDIT.json完全一致。

`python -B -m unittest test_audit -q`及-O模式各4项synthetic测试通过；这些测试验证错误身份、metadata篡改、虚假numeric声明等拒绝，fixture返回acceptance_authorized永远false。它们不能授权GO；本次限定GO依据是实际runmetadata核验＋8源人工差异审计。工具自动输出始终acceptance_authorized=false，避免把“检查工具通过”冒充独立批准。

## 尚待完成

新SV归一化与模块fingerprints、真实Verilator header/ABI及GCC依赖、共同后端执行、五块完整M128数值与最终冻结同刺激RTL回放仍待完成。旧4096 Matrix provider未改，不等于provider RTL数值通过；32-bank结构不等于全链II=1。五块完整数值0/5、最终RTL0/5，有效MAC利用率未实测，80%/90%目标保持。

原始运行：https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/41114764250
