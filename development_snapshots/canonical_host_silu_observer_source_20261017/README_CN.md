# canonical Host SiLU observer：纯源码小 checkpoint 候选

本目录保存 SiLU 观察算法与可便携合同冷测试。状态是 SOURCE CHECKPOINT CANDIDATE；不是已提交、已发布或 Host 验收通过。

## 文件与来源边界

- silu_observer.hpp：原 observer v2 的原字节 C++ 源码，未改写。SHA-256 为 4517356fae02531b1eab19d825423440c197bfeb0f5269475dda501da1225245。
- cold_contract.py：同一 v2 的原字节 Python 合同反例 oracle。SHA-256 为 12ba721acd31087e8b0efa5288dafe603eaf18782bc95ed6599135f9f6640032。它不会生成或代替实际观察数值。
- BINDING_REQUIREMENTS.json：派生的逻辑合同，非原字节副本。保留 15 组字段/宽度/语义要求，将原 source 位置替换成逻辑 module 名；所有 generated_cpp_symbol 仍为 null。
- SV_LOGICAL_LEAVES.json：从已审实际 SV 来源索引提取的派生投影，非原索引或原 SV 字节。只留 member、module.signal、width、direct/alias 四列，含 468 个 pre 与 13 个 post 条目。没有 C++ 可访问符号、运行绑定、源文件位置、层级访问路径、声明文本、SV 行号/偏移或工具链信息。
- test_portable_cold.py：派生便携测试。保留原合同的资格/负例检查，用本目录原字节散列检查替代外部 source-pins 依赖；不再把未携带的 Scala 文件检查算作已执行。新增逻辑投影、未绑定边界和独立目录检查。
- README_CN.md：本说明。

原 C++ 头文件内部的 qualified 与 Observer 是算法/事件账本；GeneratedBinding 是四入口全部抛 Incomplete 的未绑定 stub；ActualHostObserver 固定使用该 GeneratedBinding。为了保存原字节，二者仍放在同一头文件。两类代码不能被混同为可运行 Host 绑定。

## raw SiLU 的联合资格

raw tap valid 只是必要条件。必须同时有实际 resident 路由选择、已匹配的 group 与 loan、真实 active、无 poison/abort/router/bridge/group/reset 故障、非 binaryAdd、vector issue/phase5/allReady、无 vector error、锁存 gate/up 操作数匹配，并且该 loan 尚未捕获 raw 事件。源码中的 qualified 是这 17 个布尔条件的联合门；完整 Observer 还检查真实握手和账本状态，不能单靠一组布尔值证明完整事件合法。

group identity=(7<<16)|17，gate tag=(7<<16)|16，up tag=(7<<16)|17，act owner tag=(7<<16)|18。17 不是 Act owner，也不是事件数证明。每个响应必须匹配此前上升沿已接受的 tile read。Gate/Up 依次来自 slot0/slot1 的真实返回，up 响应与 bridge、router resident、router shared、owner loan、vector request 五段请求握手及各段原 payload 必须同一 edge 一致。

每个实际上升沿先保留稳定低电平 pre 快照，再在真实上升沿及组合稳定后核对 high post 状态。fire 和数据都来自 pre；post 只验证真实状态转移与故障。重复、跳跃或错配 edge、缺少真实贷款、操作数变化、重复 raw、same-edge/late abort 均拒绝。before_rising、after_rising 及 coverage 任一入口出错都 sticky failed，捕获异常后不能补事件恢复成功。

raw 数据为既有 phase4 materialized 寄存器在 phase5 issue 时的原始 16 个 u32 字，逐字等于 vector.value；仅检查有限 BF16 扩展位形，不计算 SiLU、不转浮点、不补零、不回填预期值。phase5 的乘积结果只用于路径一致性与贷款退休，slot2 的 Act 乘积不能代替 SiLU 中间值。

坐标由已匹配 loan 的 ng/index 与实际 bridge call.cols 决定：lane i 对应 batch0、row=(index/cols)*16+i、column=ng+index%cols。完整 provisional coverage 需要 56 个 ng 分片、每片 1280 个真实贷款，共 71680 个合格 vector 事件、1146880 个 u32 字，以及真实 Act18 成功 group 终态；这些数值是约束，不是已观测计数。

## 派生 SV 投影的精确限制

投影逐行由原 pre_leaves/post_leaves 的 member、module+'.'+sv_net、actual_width 派生；只有 EXISTING_SV_WIRE_SOURCE_ALIAS 转成 alias，其余为 direct。它是 source 层逻辑清单，不承诺完整实例路径、C++ 名称或优化后的可访问性。

唯一 alias 是 pre.bridge_call.cols -> FfnTileSiluBridge.io_tiles_control_bits_cols（8 位）。来源 Scala 无条件将 call.cols 赋给该控制线，已检查的 SV 保留这条现有线。这个结论只适用于已审的固定来源，不能改为 C++ 常量 160，不能推断不同模型、未观测 edge 或 reset 语义；实际符号若缺失仍必须 INCOMPLETE。

## 冷测与未完成范围

在本目录运行：

    python3 -I -S -B test_portable_cold.py
    python3 -O -I -S -B test_portable_cold.py

测试仅使用 Python 标准库及本目录六个文件，无需外部源码、源索引、模型、工具链或网络。枚举 qualified 的全部 131072 种组合，验证 raw-only、每项否定、非布尔值、身份/slot/ng/index 错配、缺失五段握手、payload 错配、重复 raw、乘积替代、late abort 与 sticky coverage 失败等负例，并检查 71680 个向量基坐标的完整分解。

冷测只执行明确标注的 Python 合同 oracle 与源码/清单检查，没有编译或执行 C++ 状态机，没有运行 EDA、Java、RTL、Host、producer，也没有重跑完整加载。没有利用模型参考张量来冒充物理观察。

尚未完成：实际 GeneratedBinding 全字段/位宽/唯一模型实例绑定及 runtime 可访问性验证；真实同 edge 采样；PhysicalObserver 的 11 方法与其他 26 节点；17-owner 账本、DDR B 退休/readback、prefix memory-SSA/generation、Host 终态和全部 27 项数值资格。所有 provisional 数据在完整生命周期通过前都不是最终 canonical 结果。

本小片不改变 Host 外部 ABI、RTL 算术、tap、MAC 或 SRAM，不报告硬件利用率、时序性能或完整 block RTL 通过。源码保存、冷测通过和运行绑定完成是不同的验收层次。

## 安装与批准

建议目标为 development_snapshots/canonical_host_silu_observer_source_20261017。上级 INSTALL_MAP.json 仅供本地安装/审查交接，列相对候选路径、相对目标路径、来源类别与逐文件散列；它和 CONTENT_SCAN.json 不属于安装载荷。六个载荷文件可复制到任意普通目录后重新执行上述冷测。

本候选没有 commit、远端写入或发布动作。基线 main 为 0830087d19e506bb1614888c94c647d4ac5ddf78，发布仍需根任务审查与授权。没有携带环境/工具链清单、绝对宿主路径、生成 SV/classes/IR、权重、原 receipt 或原审计 manifest；待批准的元数据不因本投影而获得发布许可。
