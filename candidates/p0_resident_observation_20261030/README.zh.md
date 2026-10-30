# TEMP：P0 Gate/Up 真实 SRAM 只读观察候选（未选用）

**此目录不是当前 active fixed155/backend 的源码选择；未替换任何 active manifest 或实现。** 五个 Scala、共享 driver/header、比较 helper 保持已审候选字节不变。旧源码/ABI/canonical/RTL哈希与门禁全部保留，不迁移旧PASS。fresh-host pin-only更改尚未合入此候选。

## 实现范围

- 五个 Scala：FfnTileSiluBridge、FfnResidentCoordinator、QwenOwnerProtocol、HostBlockTopV4、HostBlockCommandsV4。
- 只采 `tiles.response.fire` 的 sealed SRAM FP32值，经过 Bridge→Coordinator→Owner→Top 的固定 Valid-only sideband。无 ready、不多发SRAM读、不改变原算术/调度/DDR。
- ownership来自实际call.gate/up/act.tag及已有cfg.profileId。driver检查launch、fault、profile、epoch、identity=gateTag+1、真实命令阶段、坐标范围、owner稳定和exact-once覆盖；整块clean terminal之前不发布完整观测。
- `row=(index/160)*16+lane`，`col=ng+index%160`；两stage总143,360beat/2,293,760个FP32值。
- 参考BF16位型左移16后与actual原始FP32位型精确比较。actual不舍入，参考值不进入DUT刺激。

## 最终源选择及consumer

基线执行源码为 `04be815f803ab45876f0e687146b96281ed857e4`。基线 actual fixed155 由 `fixed_sources.checked_paths` 输出，经 `one_job_entry_fixed_r2.py` 的compile155使用；其中HostBlockCommandsV4选择attention_policy_count_fix版本。本候选对应这些最终文件，而非未选择的preimage。

driver基于最终 `five_profile_execution_v3_20261029T0148/host_axi_driver_non_dpi_final_dump.cpp`。数值接入采用实际链 **numeric_tail → connect_owned.py → numeric/consumer_owned.py**，不包含未选用的祖先run_compare副本。owned环境、ABI、启动证据与终结/INCOMPLETE/exit2语义保留。`SOURCE_DELTA.json`仅提议相对路径及hash，不是active选择器。

合入时必须单独更新真实connect_owned consumer pin与helper输入闭包，并重新审查新源码选择、ABI与canonical资格；不可删除旧门禁以强行运行。

## 验证结果及边界

`evidence/LOCAL_TYPER_EVIDENCE.json`来自真实LOCAL typer回执的白名单摘要：
- native exit 0；耗时55.460118529998秒；observed RSS892080128 bytes；errors空。
- cleanup精确为COMPLETE_OWNED_GROUP_ABSENCE_BEFORE_LEADER_REAP，pipe EOF及gzip finalized均为true。
- 155源，仅五个候选替换；107个已pin JAR（含插件）；`-Ystop-after:typer`。
- 本地Debian OpenJDK21.0.12.1，与CI Adoptium21.0.13+9不同。

**以上为先前typer检查当时的范围；下方新增实测已覆盖完整字节码与HIGH/LOW IR。该typer检查本身不含Chisel插件typer之后阶段、完整字节码编译、Chisel elaboration、真实端口ABI、IR/RTL生成、CI资格或block数值验证。** 新RTL哈希待定，完整M128/五块数值未通过。

打包后重跑的微型检查：4项BF16位型比较测试、C++ synthetic collector负例及完整shape映射、mock-port完整driver语法、7项原owned-consumer mock生命周期测试。没有运行实际DUT。详情见 `evidence/TINY_TESTS.json`。

## 固定接口与资源

候选统一增加689 bits、预计27个flattened输出端口（实际生成ABI未核；原85口约定下预计112），无ready；使用已有cfg，无新硬件寄存器、tensor RAM或MAC。观察扇出/组合门及物理QoR未验证。host collector约9.18MB payload和143,360B覆盖表，不是硬件资源。五块仍须使用同一硬件、接口和后续新RTL哈希。

P0真实读口是16-bank；这不是整个设计lane数声明。producer中的literal vector_lanes=32不构成32-lane每周期发射证据。P0 ScheduledSiluOwner实际连接SiluVectorUnit(16)；另一路GdnRuntimeElementwise的32项BF16 bank使用scalar逐lane流程。此候选不升级或缩减lane，不改变4096 Matrix定义；用户要求的Vector32全链实现/重测仍是独立工作。

## 明确未完成

- 其他required stage仍有仅长度检查；本候选只闭合P0 gate/up观察实现。
- MoE raw FP32 selection score尚未导出；同分小专家ID参考契约未获批准，原PyTorch路由不变。
- 模型完整通过、同源码/输入/配置冻结、随后同刺激RTL回放尚未完成。

## 微型测试复现

从仓库根运行（`$P`为本候选目录）：

```sh
python -B "$P/tests/test_compare.py"
python -B "$P/tests/test_mapping.py"
python -B "$P/tests/check_driver_syntax.py" --repo "$PWD"
python -B "$P/tests/test_consumer_owned.py" --baseline candidates/same_job_execution_20261030/numeric/consumer_owned.py
```

mock-port测试不是实际ABI资格；collector生成的合成输出只存临时目录并在结束后清除。这里不提供机器本地绑定、运行环境库存、原始日志、权重、二进制或tensor数据。

## 2026-10-30 新增实测：完整字节码与原始 HIGH/官方 LOW IR

状态：**PASS_LOCAL_COMPILE_AND_IR_STRUCTURE_ONLY；候选仍未选用。完整 M128 block 数值 0/5，最终 RTL 数值 0/5。** 证据见 `evidence/LOCAL_FULL_COMPILE_AND_IR_EVIDENCE.json`。前文“预计接口”现仅对 SV/Verilator ABI 仍待验证，LOW IR 端口已取得以下实证。

- 实际155源、五文件覆盖的完整Scala字节码编译 native 0，120.928179834秒，observed RSS 1,589,428,224 B；861个class、17,950,177 B。新Bundle出现 `_usingPlugin` / `_cloneTypeImpl` 插件生成方法。不是仅typer；本地Debian JDK不构成CI工具链资格。
- 原始helper实际HIGH/官方LOW发射 native 0，151.342637576秒，observed RSS 4,318,490,624 B；两次任务均errors空、严格原进程组清理先于leader reap、pipe EOF及gzip finalized。RSS是采样观测，不是资源上界证明。
- HIGH：122,731,862 B，SHA256 `0beb67704eca597275afea1aa688601996aca4ffb5dfc5e2fc728b17d6179afc`。LOW：313,044,298 B，SHA256 `f52a49582417a849ea3c0d63082c5e9bbdb117aec6d79993eacc783c917ddde3`。这是新IR身份，不迁移旧canonical/RTL PASS。
- 独立流式解析实际LOW：Top共112端口；原85端口无删除、方向/宽度无变化；新增27个输出、689 bits，逐项匹配提案。**只证明本次LOW IR接口；没有生成SV或Verilator ABI资格。**
- 模块图95定义/1,056可达实例与hierarchy TSV一致。`moeArithmetic.bank.alus_0..31`为32个可达HeteroFP32Alu，但全图合计81个，另49个在原scalar/vector/element/Silu路径。不能称全设计仅32 ALU，更不证明统一32-lane每周期发射或90%利用率。
- `owner.matrix.leaves_0..7`为8个Matrix endpoint；外部端点可达性不是4096 MAC底层实现、综合或数值证据。候选不改变既定4096资源要求。
- 清单列13文件合计439,001,203 B；实际临时目录14文件752,045,501 B，另有313,044,298 B的 `HostBlockTopV4.lo.fir`，与official-low同SHA。**未删除任何文件**；本包仅提交摘要/hash，不提交IR/class/原始日志/机器本地路径。

仍未做SV生成、真实DUT执行、PPA、完整block数值或最终RTL回放。模型/ABI/canonical及五块同硬件资格仍须分别完成；没有更新active源码选择或放宽任何旧门禁。
