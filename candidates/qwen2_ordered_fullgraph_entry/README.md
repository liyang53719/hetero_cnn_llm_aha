# 默认关闭的完整 block ordered Attention 接缝（TEMP 准备阶段）

**当前阻塞：正常 fullgraph import 因缺少已准入的 PyYAML（yaml）而失败，真实九方法绑定尚未到达。193 项控制测试四模式各 PASS 不等于正常源码加载或完整 block 数值 PASS。**

本片绑定已发布 `8b3c5a2ea6e9615f5a2a8c37ad5392c6d4a7941a` 的组件 Observation 证据；不继承其之外的数值 PASS。只新增独立候选，不改历史 pins、旧 M16 rawKV/PV2 入口或冻结运行。

## 实际执行路径

`compose.py` 精确复制 316 个已冻结 source 文件，仅给原 `ffn_public/fullgraph_execution.py::execute_public_suffix` 增加默认 `None` 的 `attention_dispatch` 参数及 pc12 分支。未启用时仍调用原 `execute_attention_owner`；禁止将新 dispatch 与 raw KV 模式混合。

新 `bridge.make_dispatch` 明确 opt-in 后，使用既有 `production_qk16_model.direct_transport.bind`，复用原 owner、physical memory、Matrix service、strict 16-lane work 和原 ACK 驱动。先安装 ordered adapter，再绑定正常 source observer；观测范围仅 pc12，不把 Dense/FFN 请求伪装成 QK/PV 服务事件。QK 使用 combined ELF profile2，PV 保持 legacy profile0。没有新增 ScalarService、算术实现或 tile cache。

完整编排复用原 DenseReduction prefix、Norm/RoPE、O、残差、FFN 和 suffix；不是以新 synthetic owner 取代真实路径。控制单测中的替身仅检查编排，不证明真实模型数值或运行时绑定。

## 完整中间值的诚实边界

registry 登记 19 个实际 suffix 输出、实际 SiLU phase4、10 个 Attention 字段及两个 KV 视图。seal 要求原 21 个 public completions、17 个 owner jobs、唯一 launch result 与资源清债。捕获 seal 失败不会替换已返回的实际 pc12 driver 结果，但最终验收必须拒绝。

32 条 inventory 不等于官方 29 个语义节点完整覆盖。registry 逐项列出未物化、未捕获、仅 causal 部分覆盖的区别；不使用参考补值，不重造 repeat K/V、cos/sin 或 mask 张量。Norm/RoPE 内部算术临时值亦未声称完整观察。

## 准入状态

本批只做源码组合、静态/控制冷测及 manifest 准备。不加载 Matrix ELF、不构造真实服务、不执行完整 M16/M128/native 算术、不编译、不生成 RTL。完整数值与硬件资格均为 TEMP。

`qwen2_fullblock_reference_m128/pins.json` 的 reference freeze 是 `NOT_CAPTURED_SOURCE_ONLY`，29 个 reference 哈希为空，不能作为真实 oracle。既有 M16 独立 block/pair 参考必须另核原始 provenance、payload 哈希及输入身份；不能借旧 PASS 放行。新准入准备状态不等于执行授权。

## 后续验收阶梯

1. 精确组合与全部源码/依赖正常 import 闭包核验，保持任务级 ELF/service/job/tensor 禁止。
2. 完整 provider14/raw13 与 M16 view 身份、同源独立参考、运行时闭包、可执行 profile 和资源预算独审。
3. 经单独准入后才考虑真实 M16；先实际 terminal/ACK/清债/捕获，后独立参考比较。失败保留，不将控制 fixture 当数值证据。
4. M128 需另审新观察器容量与完整 source/input/profile，不能沿用组件运行的 45 秒预算。

固定物理资源仍为 4096 MAC。legacy PV 路径给出的完整 block 理论上界仍为 63.57%；本片没有 80%/90% 利用率、硬件 cycles、频率或 II 证明。host step/tick 与 wall time 都不是硬件周期。

## 独审发现与修复记录

首轮控制 fixture 未覆盖 fullgraph Matrix service 的继承关系。真实 `ProfiledMatrixService` 继承 `OfficialMatrixService.acquire`，而组件 `ServiceTrace` 原构造器只接受基类 `MatrixService.acquire` 的代码身份。直接复用会被严格 source binder 拒绝。新片只添加实际继承方法的精确 source 绑定，沿用旧 trace 的事件回调与生命周期校验，不改服务方法、旧 observer 或其 pins，也不同时捕获 wrapper 与基类造成重复事件。该问题在静态独审时发现，未因此启动实际数值作业。

## 最短复现与前置条件

先提供与 `SOURCE_PINS.json` 全部 316 项逐字一致的 R2 assembled source root。该 root 来自已审 source assembly，不是任意 main checkout；没有此闭包时 composer 会拒绝，不能以忽略 pins 的方式“复现”。本片不包含原始权重、参考张量或 ELF，也不提供下载/重编译步骤。

```sh
python -I -S -B compose.py --source-root "$PINNED_ASSEMBLED_SOURCE" --output "$FRESH_COMPOSE_DIR"
python -I -S -B run_control_tests.py --source-root "$PINNED_ASSEMBLED_SOURCE" --output "$FRESH_TEST_DIR"
python -I -S -B runner.py --describe
```

`runner.run_actual` 是供未来独立准入 caller 使用的真实编排函数，不是独立安全/身份校验器。其 admission 字典声明不能替代精确 source/runtime/input/ELF 哈希、预算审核和唯一运行账本。当前命令行故意没有 numerical execute 模式。

已核当前 full provider14/raw13 与现存 M128 参考恢复文件共 76 项、222,602,223 字节全部匹配；这是只读 hash 证据，不是执行。M16 x view 与历史 M16 input_x 相同，其余独立 M16 reference payload 闭包尚未恢复，完整参考绑定仍未完成。准备器的 metadata-only 声明不因另行只读核查而被回写成 READY。

正常 import 冷门另需原已 pin 解释器/NumPy/runtime 与本机精确配置，不能仅凭公开 projection 重新生成相同配置 SHA。公开 launcher 只接受其已独审 config；路径迁移必须生成新的配置与审查记录，不改旧 receipt 或关闭映射核查。冷门允许原标准依赖初始化与 metadata 构造，具体禁止 custom Matrix ELF、服务/owner/Observation 实例、提交任务和用户 tensor 读取；它不是通用 Python 沙箱。

## 正常加载的实际终态

首次 cold v2 因审计误拒绝只读 Services 默认快照与重复 namespace 路径而 FAIL。原报告/账本不改；完成全量 metadata 默认参数检查与库存离线重放后，v3 通过这些兼容门，但完整 fixture 正常 import 在 `src/heteronpu/config.py` 遇到 `ModuleNotFoundError: yaml`，仍为 FAIL。九个真实 service 方法绑定未执行，本片不能称正常 runtime 接线已验证。

PyYAML 及完整 fixture 外部依赖准入将另开独立片，先核现有可信源码/version/ELF 与所有 transitive imports，再审新配置，不下载/重编译、不借旧配置放行。当前完整 M16、数值、运行时非干扰与硬件均 TEMP。
