# M2 identity-lookup 三臂诊断：源码与有限实际证据，不采用

本片只新增身份索引候选、必要 wrapper 差异、可移植源码组装器及脱敏证据。实际 variant 为 **selective_identity_r1**，不是原 R4 的重命名。已有 R4 运行、synthetic fixture slowdown、r1 BLOCKED、完整 M128 CPU 超限 FAIL 均保持原样；没有默认路径替换、稳定性研究、长跑重启或采用。

## 源码改变及其边界

候选 monitor 的 LINE 预筛选改为整数 id(code) 索引；每项保留 strong code reference 与原 frozenset points，并以 row[0] is code 校验。原 source/point 验证保留，新增拒绝 equal-but-distinct code、role identity 交换、selection map 替换和失配缓存。不是只信 ID 的缓存，不在 miss 时重建，不缓存变化中的 frame locals。事件 masks、预筛选之后的 capture body、_return、capture/lease/bridge 保持原语义；原来不支持的任意运行中私有属性改写没有被宣称全部解决。

五个 wrapper executable 的差异仅是公开身份/profile/GO action/status 及说明字符串，八个 executable 文件逐字不变；binding mock 同步标签。新的独立源码身份与原 r2 不混用。正常加载实际 candidate 的四个完整模块；敏感回调未包装，模块源码及 mask 生命周期由实际审查核对。

## 唯一实际运行及计时

一组固定顺序 off / original / selective_identity_r1 的 owner-through-terminal-ACK-and-monitor-exit CPU 为 **0.147838387 / 0.647338533 / 0.471684661 秒**。原 parent exit 0、无超时且 group_remaining=false；parent wall 6.283986124966759 秒，worker process CPU 6.226902891 秒。AS 1 GiB 是上限，不是实测 peak RSS。

同次 original→identity 区间少约 27.1348%，但这个完整候选同时包含 selective-LINE 策略和 identity cache；**不是隔离出来的 cache-only 收益**，不是稳定/因果 benchmark。R4 不在此三臂中，先前 R4 的计时不能作为本次同条件分母，也不能把跨运行差异当成 cache 的贡献。固定顺序受热身/缓存/先后影响，原观测器基线本身也会波动。本片不含后续稳定性研究结果，不据此采用或预测 M128。

off 仍有共同的完整 ServiceTrace；clean 区间无 count probe/profiler/callback wrapper，开始于 monitor 安装与 installed-mask 校验后，结束于实际 monitor exit。off/original ExitStack 与 candidate bridge 退出实现不同，额外 lifecycle 校验单列计时。输入/source hash、setup、封存/I/O、臂间审计及 reference 不冒充 owner 段，零 CPU 分辨率值不表示免费，不任意相加嵌套阶段。

## 实际审查范围

22314 项独立只读检查、零错误；1026 pins 与冻结身份未改。115 artifacts / 4239385 bytes 的外置 hash 清单保留完整原证据身份，但没有上传其 raw tensors、events、maps、weights 或私有 config/GO/claim。

三臂均有 1515 个完整生命周期事件、216 tickets，原 ticket 范围依次 1–216、217–432、433–648。只在跨臂比较时双射规范化；raw events 私有留存。三份 output/score 逐字等于既有独立 reference，writes 完整相等；两个 observer 的十字段 values/presence/shape 对照 reference，两个 observer frequency 相等。reference normalizer collector 重复 8/16 次、DUT 每值一次；只保证其值/presence 相等，**不声称 reference frequency 相等**。DUT report writes 是 unique first writes，reference writes 是全部 collector events，口径不同。

reference 是既有独立 AST recipe 与共享精确 RNE primitives，不是完整官方 Transformers forward。实际 recipe 位于三臂 terminal ACK/release 与控制验证之后；预检会读源码、提前加载共享 primitives，不声称 preterminal 没有任何 reference 源字节读取。只比较因果有效区域；future padding/sentinel 不当作观测值。独审未重跑 native/target、未独立重算算术，仅审查留存 bytes/hash、事件、源码和 metadata；四模块 compile-only 身份核验不是执行。

原 review scope 有 identity_identity_r1 的文字重复，公开投影逐字保留并注明；实际结果的 variant 仍是 selective_identity_r1，不能据 typo 重新命名运行。module/maps 是边界快照，不是完整 OS 访问记录。原 launcher 没有独立最终 seal 或完整原生 pre/post ledger；后补外置 ledger 不追认为运行原生 seal。所有完整 block/M128/RTL/cycles/有效 MAC/80%/90% 验收仍未由本片建立。

## 复现精确源码，不重复上传不变文件

pins/ASSEMBLY_MANIFEST.json 列出 20 个精确文件：13 wrapper executables、1 binding mock、4 observer modules、1 source gate、1 observer pins metadata。这里只新增 7 个逐字原始 Python 文件，另外 12 个 Python 文件和 1 个 metadata 以已发布相对路径及 bytes/SHA256 绑定，不依赖开发机路径。

在包含本提交的干净仓库中执行（FRESH_SOURCE_BUNDLE 的父目录须已存在，输出本身不得存在）：

```sh
python -I -B candidates/qwen2_attention_identity_diagnostic/assemble_sources.py --repo-root . --output FRESH_SOURCE_BUNDLE
python -I -B candidates/qwen2_attention_identity_diagnostic/test_assemble_sources.py
```

组装器只读取、验 hash 和复制，不导入目标。它先验证全部输入，拒绝路径穿越、重复 target、source symlink、已存在 output；normal/-O 各 10 个新 packaging-only 测试通过，两模式均组装 20 files / 210822 bytes 并与原目标逐字一致。此 20 次工具测试不是模型/mock/native 数值验收。公开 helper 是新编写的打包代码，不冒充历史运行源码。

这让源码快照可从仓库独立组装，**不是完整运行环境自包含**：316-file assembled target、原测试闭包、Python/NumPy、已有 native ELF、私有输入与新逐 hash runtime config/准入仍需另供。1026 逻辑 pins 保留顺序/重复/hash，无物理 locator，不是可执行配置。不要复用历史一次性 GO/attempts，也不要把 inherited cold_import.py 在清单里等同新增 cold 执行。

## 历史测试分别计数

候选 author 的 AST fixture 每模式 30 top-level + 26 nested = 56，共 112 cases；独立 source reviewer 的 126 executions 单列，不相加成独有覆盖。后继准备只新增每模式 22 binding + 8 admission/config，共 60 delta executions；独审 admission 14 executions 单列。旧 lease/resource 84 executions 和候选 112 是依 hash 复用、未再执行的证据，不冒充新增 real-owner 覆盖。原 candidate fixture timing/instrumentation 测试未重跑；helper 偶有时钟采样不构成 benchmark。打包不重跑任何上述目标测试或 native。
