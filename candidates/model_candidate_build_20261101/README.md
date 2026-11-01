# MODEL_CANDIDATE 七文件打包（SOURCE-ONLY）

本模块只冻结本次真实构建字节及观测；`UNREVIEWED_MODEL_BUILD` 是永久构建状态，不是数值准入、完整 block PASS 或最终 RTL PASS。数值评估必须由包外独立 `model_candidate_review` pin 绑定本次身份与观测，不能回写包为“已接受”。

七件仍是 `dut.bin`、`hardware.sv`、`driver.cpp`、`source_manifest.json`、`tool_manifest.json`、`build_receipt.json`、`frozen_artifact.json`；总解包量 ≤4GiB、source manifest ≤16MiB、receipt/manifest 各 ≤64KiB。ELF 复制后 0600，不执行。没有第八份 review 文件，不收权重/NPZ/参考/原始日志。

`pack(original, b, built, host, overlay, out, budget_check, observation_pin)` 保留五阶段真实 argv、严格 native0/cleanup/EOF/gzip，另从同一次输出目录核全部 20 阶段原 RESULT 文件 pin。首阶段显式 `compile_model_sources`，真实源数量来自经过审查的 source closure（当前 159），不冒 155 源。

打包时调用新 `model_source_evidence.record(original,b,built)` 形成完整角色/生成/实际依赖链，不调用旧硬锁 P0 的 enrich。观测由独立 pinned collector 提供；打包验证其实际 source/overlay/SV 和结构声明一致性，**不将观测 digest 自赋为 accepted digest**。后续真实消费侧还必须完整验证 candidate producer 源锁、Make、GCC `.d`、122 header、链接收据以及包外结构审查。

当前纯源码/合成测试，尚无真实 MODEL_CANDIDATE artifact。

外部审查 scope 固定 `MODEL_CANDIDATE_EVALUATION_NOT_PRODUCTION_OR_FINAL_RTL`。`verify_candidate_compilation(manifest,source,receipt,payloadroot)` 只验证编译证据，不授予该外部审查。生成器固定实现 SHA 映射在源码冻结前为空并拒绝，必须由独立源码审查固定，不能从包内观测学习。

最终消费边界：`verify_candidate_seven` 仅同 builder 源的 export/receive 快捷核验；先将已 pin manifest 的 observation.source_closure.source_pins_sha256 与本地 SOURCE_PINS 全字节 SHA 绑定，再逐字节核 pack/proof 后按同目录显式文件导入，不使用同名 sys.modules。异源 executor 使用独立受审 catalog 与 `verify_candidate_compilation`，不得沿此快捷路径假称同源。

轻测 39 项 normal/-O；另旧闭合 O1 元数据的完整 Make/.d/五阶段算法回归双模式通过。`synthetic_complete_candidate_fixture.py` 用旧元数据作语法模板，重建 122 端口 header 并同步依赖 pin，15 合成阶段加 5 模板阶段；真实 checker 与七件校验完整执行，无 mock checker 返回。此包全部 candidate 身份/新 header 是 **ALL_SYNTHETIC_CANDIDATE_EVIDENCE**，不是实际新构建资格；不发布构造出来的 payload 目录。新 P0 source evidence 由集成测试提供真实格式合同 fixture，构造器占位不授权该独立门。

实际 helper 层次首根只接受唯一首行 `{path:"",module:"HostBlockTopV4",defname:""}`，非根/外部 provider path 仍必须非空，模块集合/32-bank 子树/17 provider 与实际列举一致。该结构一致性不替代构建后的独立架构审查。
