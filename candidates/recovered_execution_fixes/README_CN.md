# TEMP：恢复后执行链纠错候选（2026-10-28）

基线 main `897f08f77b6c31fd567b32904079cf1ab20ee986`。这是两个可复现最小纠错候选，不是新的通过冻结版本。旧夹具、源、证据不覆盖、不删除。环境恢复已丢失实际权重、编译产物及运行结果；旧 PASS 不继承。

## 1. Qwen2 原生权重刺激和字节提供者

已独立确认源契约错误：原五块 profile0 的七个 Dense B 是 dtype7；原 public21 Commands 要求 dtype5，首个 Dense PC1 会触发 Unsupported（静态推演，不是仿真故障日志）。复用原 `pack_owner_bf16_weights.py`，仅七个 Dense B 改原生 BF16。激活、输出、bias、Norm、RoPE 仍原 FP32；不改 FMA、舍入、归约。

新描述符 SHA256 `1e4d35da18b21a4d9de05d2f3129e5bd9717cd923837c83c8d5eb320bfcddb02` 替代旧 `d5ef2c75f7c8f790993a9aef04ff0af96209365af3df85b33fae9ff8d8cb3086`；命令字节不变，仅七个 dtype 字节改变。新生成 manifest SHA256 `c5fcd45a4cee53b084a0915753186b06540342bb0620a783f528fefb83b9b561`。

候选 provider 取消七种矩阵权重 BF16→FP32 扩展，仅接受精确二维、只读、dtype5、大小匹配的 storage_bytes。旧分配上半区保持不可读 guard；未写 RW 不能预载。元数据读取使用原 table_sha256。旧 source spec/真实权重尚未恢复，`build_readers` 未验证；旧 PROGRAM_PINS、LOGICAL_HASHES、BYTE_PROVIDER 及后端导出全部必须重建，不能仅替换描述符或迁移旧字节 PASS。

## 2. MoE Down 单 K 块前缀工作区别名

P3 PC11/P4 PC16 的首个 Router Dense 为 M128/K2048/N256，splitK2560。region3 prefix workspace 覆盖其 D；旧普通 Down 无条件 prefixAliases 会静态推演 Bounds。K<=splitK 无前缀 spill/restore，故最小硬件候选仅添加 `j.k>w.splitK`。K>splitK 原别名保护、A/D、W/D、workspace 容量/代次/对齐及所有特殊 window/drain 保持不变。

补丁及重建脚本精确校验旧源 SHA256 `485af859775994bd1b130aeb6e30b4c331c5a4fc6985e3ea09c1c4170efc8eb3` 和候选 `961f4e650b499fc1f15918d2e0f6aa51b4905431ba35ba681a609c98b42c5d14`。不在本提交修改旧候选目录。新硬件未经 Scala 编译、Chisel elaboration 或 DUT 测试，全部五块都须重测。

## 复现与精确证据范围

在完整本仓库 checkout 运行 `python candidates/recovered_execution_fixes/reproduce.py`。生成的命令/描述符/临时源仅驻留 TemporaryDirectory，完成后由脚本删除自己创建的可重建文件；不生成权重、不下载、不启动 CI/EDA、不触碰已有证据。

PASS 仅：191 项合成读取/guard/RW 测试，18 项独立负向/元数据测试，5600 个合法 BF16 K/split 控制谓词案例和两个实际程序地址反例；重建七字节差异及精确源 SHA。测试含 assert，明确禁止 `python -O`，不把优化模式空跑当证据。独立审查另覆盖 FP32 K16 边界，仍仅源码/合成控制范围。

`parent_inputs.py` 是原显式 SHA→本地路径绑定工具。该包只包含更改相关 provider 部件；作为旧 five_profile_byte_provider 的 overlay 使用，原 bundled 输入生成器/配方仍从旧包取得，不是独立完整字节提供者。脚本仅合成测试，不调用真实 build_readers。

**完整 M128 Chisel 数值：Qwen2、Qwen3.5-0.8B L0/L3、35B-A3B L0/L3 均 INCOMPLETE，0/5。最终同刺激 RTL 0/5。没有有效 MAC 利用率实测。4096 Matrix MAC 不变；32-lane 方向仍候选，MoE 同分契约仍待用户明确。**
