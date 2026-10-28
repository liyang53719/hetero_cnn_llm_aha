# 五块 M128 字节提供器与程序元数据

**BYTE_PROVIDER_ONLY / TEMP / requires-parent。不是DUT运行或完整模型支持；五块完整Chisel数值0/5，同刺激RTL 0/5。**

## 原始实际结果与本次发布范围

原五块只读输运实际记录84个tensor完整逻辑流hash，共3,631,340,832 B；另有10个补齐后的command/descriptor表流hash，共94个RO allocation。exporter当时实际核验88份来源、3,534,006,784 B。C++与独立Python reader比较561个边界probe，覆盖全部94个RO allocation；它们是字节一致性，不是后端编译、AXI时序或DUT数值资格。

本次发布独审重新核验69项基线、21项export、3项cross-language封印，核probe文件hash/计数及来源size/mtime；**没有重新流式读取多GB权重，也没有重跑完整provider integration。** 不把历史hash记录说成刚刚重算。实际输运检查分别118/127/117/149/139项；RW测试数据仅存在可丢弃测试内存，不导出或预装真实计算结果。

只提交Python源、pin/hash/count摘要和中文计划。禁止提交真实权重/输入/系数二进制、npz、command/descriptor二进制、参考输出、expert IDs、任何字节转码形式。尤其不上传包含真实采样hex的READ_PROBES TSV。原bindings/export TSV含私有路径和上游shard/range定位信息，均不原样发布。当前包不包含C++后端源，也不继承后续独立backend冻结的资格。

## 真实字节语义

- 原 `memory_provider.py` 精确复制：RO不可写，RW按4KiB稀疏页和逐字节valid保存；未写输出/scratch读取失败，完整请求先检查再修改。
- 只允许显式冷history/state和明确声明padding为零。Qwen2的kv/cache_k/cache_v只有经核对精确几何后才声明RW别名；不允许任意重叠、RO alias或地址洞。
- Qwen2七矩阵的BF16仅作bits左移16的FP32容器扩展；其余reader只做已声明的转置、切片、逐行A/B拼接、input行选择及shared-gate后31列零padding，不执行Dense/Softmax/路由等模型运算。
- 35B输入是明确的独立实验M128 hidden输入，**不是embedding或上游层真实hidden**；0.8B L3是该block外部边界输入。只提供原始输入、权重和原始RoPE系数，不灌入被测block中间值/最终输出/官方expert IDs。

## 生成程序与父级依赖

已把此前未公开的Record128 encoder与policy源码纳入本包，避免引用不存在的公开`generated_v5`。profiles1–4在内存中重生command/descriptor和manifest并与冻结hash逐字节匹配；对应命令数17/22/13/18、descriptor数219/261/199/241。Attention明确使用既有C2契约，不继承历史prefix数值PASS。GDN scratch为rank3 `[heads,128,3280]`，绑定已发布共同准入Commands的精确SHA。

profile0仍复用原public21：21 commands /215 descriptors；三份精确metadata文件是明确的外部父级输入，**不声称本包能独立重建profile0的旧表**。本包不下载它们；`PROGRAM_PINS.json`给出全部三文件身份。

reader公开投影只把原私有路径改成SHA256到本地文件的显式映射，保留原绑定/source/manifest hash核验和布局算法。`EXTERNAL_INPUTS.json`列父级metadata和88份源身份；raw metadata中嵌套的provenance/fixture/recipe仍是精确requires-parent。所有旧机器路径由公开reader忽略，来源按hash从操作者本地map读取。没有假造可下载父级路径，没有完整归档图或fresh-checkout复现承诺。

### 本地复现（需要真实父级输入；不自动执行）

1. 安装兼容Python与NumPy；本次小测环境NumPy2.3.5，非完整环境锁定。设置`PYTHONDONTWRITEBYTECODE=1`。
2. 在**包外**创建本地JSON：`{"files":{"<sha256>":"<local-file>"}}`，用环境变量`BYTE_PROVIDER_INPUTS`指定它。不要提交该map或任何payload。每次解析都检查实际字节SHA；缺少/漂移即拒绝。
3. `python3 emit_cold128_programs.py --out <new-directory>`：profile0从父级复制精确三文件，profiles1–4由源码编码并核冻结hash；输出只在本地。
4. 将生成表/manifest路径加入本地map。`input_generator.py --output <new-file>`可生成已pin的实验输入；`rebuild_coefficients.py --out <new-file>`只重排两个已pin的外部系数，均拒绝覆盖输出。其余权重/来源必须原有精确数据，不由本包下载或编码。
5. `python3 run_provider.py --out <new-results> --profiles 0 1 2 3 4`会读多GB源并核所有逻辑hash，只输出hash摘要，不输出RW测试值。**发布过程中没有运行这一步。** 原affine/exporter及C++probe仅保留摘要/pin，完整重建那些外部配置仍需要其父级源码与metadata，不宣称本包覆盖所有backend复现。

### 小检查

在包目录运行 `python3 -m unittest test_memory_provider test_common_adversarial test_programs test_attention_moe_policies test_projection`，再用 `python3 -O` 重复；另运行 `verify_package.py` 和 `verify_summary.py`。测试仅用小型人工数据、抽象字段和内存中metadata，绝不打开真实权重。公开reader尚未以完整真实来源重新集成运行，不能把这些小测升级为历史全量结果的重跑。

## 历史与下一门

保留KV合法别名被初版拒绝、bool地址/长度漏拒绝、metadata hash/尾padding验证、Qwen35 offset64测试越界、export zero-view缺stride以及virtual输出误观察的失败记录hash。程序v1 MoE engine错误、后续C1→既有C2纠正也保留；不是新精度优化。MoE tie契约仍未结论，原Torch基线不变。

下一步将同一字节视图接入原Top非DPI实际后端，验证新共同准入后的结构与真实物理ACK/时序，再执行五块完整数值与同刺激RTL。当前没有周期、带宽、利用率或PPA结果；不能以byte-provider PASS替代这些门。
