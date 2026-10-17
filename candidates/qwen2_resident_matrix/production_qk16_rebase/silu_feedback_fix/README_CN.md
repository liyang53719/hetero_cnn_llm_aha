# 原生产 SFU 反馈单表达式修复检查点

## 当前结果
真实 Kernel 的原 B1 firtool 在51.65秒报告resident/router/真实SFU loan组合环并退出1，没有完成SV。修复仅将FfnTileSiluBridge的silu.abort从bad改成io.abort||现有poison；tiles.abort仍立即bad。当拍bad仍阻写/新请求，错误结果当拍消费、poison登记；外abort不延迟。新增状态/存储/算术资源为0。

12+12布尔握手冷测通过。一次真实增量nsc成功退出0，但严格“所有ABI成员完全相等”后验因新反射helper而失败；该实际运行保持NOT_COMPLETED。随后固定字节码的独立离线兼容复核通过（5+5及独立重放），没有重跑Java。新CHIRRTL/SV尚未在此检查点验证，不能宣称实际组合环已消失，更不能宣称完整Host/数值/性能通过。

SAFE_RESULT.json是白名单投影，不是原receipt字节；只有原receipt hash、阶段统计和cleanup相对时差。没有IR、SV、class、jars、权重或机器PID/boot/group身份。

## 公共源重建
先按已发布 candidates/qwen2_resident_matrix/production_qk16_rebase/classcompile/README_PORTABLE_CN.md 重建原92源。其公开链为 production_qkv_reduction/replay.py（生产源）、attention_qk16_owner_route.prepare.compose（QK donor）及固定HardFloat20源；classcompile/reproduce_sources.py 接受显式生产/QK/HardFloat目录并校验完整92 pins。本包 PRODUCTION_SOURCE_PINS.json再次逐项校验相同92源，不能只下载一个leaf替代原闭包。

在本目录：
python -B reproduce_sources.py --production-source "$ORIGINAL_SOURCE92" --out "$FRESH_FIXED92"
加 --include-bench 可生成94源，包含这里固定的原真实Kernel bench两个源码；该bench只为后续m1/m17组件门候选，并非已执行数值证据。
python -B test_edges.py
python -O -B test_edges.py
python -B test_portable.py
python -O -B test_portable.py

源重建不启动编译。原公开compile_only.py固定原92源pins，会有意拒绝修改源；不要绕过其pins。本包没有授权或自动启动硬件编译。下一A/B1必须使用单独审核的新闭包runner和各自明确预算。

## 离线兼容可复核入口
如具备原实际557类和本次实际557类，可显式运行：
python -B verify_existing_classes.py --original-classes "$ORIGINAL557" --fixed-classes "$FIXED557"
该入口检查精确历史class字节hash，不依赖云端私有路径。没有这些历史字节时，仍可独立重建源并运行冷模型，但不能伪称重放了历史字节码证据；另行完整重编需要新的资格门。

保留553类逐字节不变，另4类SourceFile归属同源。Bridge新增reflMethod$Method72的public ABI；新helper8目标abort，旧8..71目标顺延新9..72，因此不能笼统忽略新增helper。完整72目标序列/Code hash/实际调用点固定，所有非Bridge类CP零引用这些helper；helper72唯一init offset2857实际目标silu。结构ABI比较保留父类/接口/全部成员与Signature，边界不包含所有annotation或方法体等价。

## tile路径为何保留原立即abort
bank.responseValid和bank.poison是寄存器；Dense对外response.valid另由已注册window/drain active门控，没有由abort组合隐藏。Dense resetRequired可经window/drain侧带回resident.serviceError，返回bridge.abort经过resident.poison或router.fault寄存器。此为已pin源/旧IR具体路径审计，后续实际firtool仍必须重新确认全设计无环。

## 范围
原top与固定4096端点资源配置、唯一Dense/Matrix/16SFU/iDMA保持。配置并非综合资源或90%利用率验收。完整M128模型与实际RTL逐项对齐、packed PV/scratch/panel和性能瓶颈仍待后续闭合。此检查点打包时未包含任何新A/B1结果；未来可以分批追加。
