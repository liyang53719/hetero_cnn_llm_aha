# denseAcc：真实 AST 的有限存储校准（TEMP）

**保留的实际结果：** 2026-10-27 `2159` 唯一运行、`2202` 独立审查通过；17 个时钟周期、49 次全域扫描，401,408 次两支比较、401,408 次 witness 检查、200,704 次高行位别名检查。两支都保留 4,096 个 32-bit word。**五块完整 M128 Chisel/RTL 数值验收仍为 0/5。**

## 这次验证了什么

从真实 `Qwen2ContinuousBlock` high AST 机械抽取原存储与实际 transform 后存储；不是手写软件 DUT。原 `16×256×32` register 改成 `16×8192` memory，保留 16 个并行写口、异步读、原三处 bulk-write 的 last-connect 优先级和原索引。校准只把三处写谓词抽象为独立输入。driver 覆盖八种谓词组合、边沿前/后保持、写/清零优先级、reset 时保持/写/清零及原 `denseRow[4]` 别名。

原 driver 逐字保留：`threads(1)`、`randReset(0)` 与 reset prelude 是固定 two-state 仿真条件，**不是硬件上电清零或 reset 正确性的证明**。driver 中的数组只是运行时观察快照/程序生成的 witness，不包含任何权重、输入或参考数组数据。

不宣称 formal equivalence、任意输入/全生命周期证明、完整 Host 控制/AXI 等价、provider RTL 验收、M128 性能、物理 SRAM 推断或 PPA/QoR。完整 Host emitter 的源码用于保留 transform 集成来源，不表示它已完成整机仿真，也不应在本有限校准 replay 中执行。

## 不能抹去的历史

- `1311` 旧 warning-fatal codegen 失败保留。
- `1335` 为 `-Wno-fatal` **诊断完成**，不是无告警通过：全部 **65,520 条 WIDTHEXPAND** 已分类（ADD8 16；EQ4 32,752；EQ8 32,752）。未隐藏类别，未修改 RTL；独立审查读取全部索引 warning header，不冒充重新 hash 全部原始日志。
- `2141` native compile/link = 0，但 outer = 1、原 receipt **FAIL 保留**。checker 错把 DPI 旧 PCH 的重复 `verilated.h` token 预测迁移到无 DPI 校准；当前全部 28 个 MD 实际无重复。`2150` 不重编译、不运行，只通过独立纠正后的 exact57产品 / MD / ELF / runtime postcheck 接纳保留产物。
- `2151` runner 错读 pin 文件名且未强制 CORE soft/hard = 0；`2157` 修正后仍误绑定旧 prepare；`2159` 才修正当前 prepare 绑定。旧拒绝来源保留，不称为 DUT 失败或成功运行。

## 源码与重建入口

基线固定为 `67b8888f46941736a7af759406e37207d8568297`；`PUBLIC_REFERENCES.json` 固定已经公开的 source recipe、来源与 Git blob/SHA，而不是引用移动的根目录源码。

- `source/`：实际 denseAcc transform、校准 emitter、原 driver，以及 Host 集成 emitter / FIFO lowerer。
- `SOURCE_PINS.json`：所有原始/发布源码 hash。transform、FIFO lowerer、driver 无改动；两个 emitter 仅将各一个私有路径改成 `inputs/...`，算法与检查未改。原类 hash 是历史记录；路径可移植版重新编译后必须重新取得类身份，不能冒充原运行。
- 先按已公开 `candidates/original_host_official_lowering/REPRODUCTION.json` 恢复源码和固定的 `original-high.fir`。`extract_core_input.py` 流式核对完整父文件及唯一 Core hash，再提取 4,429,273 B 原模块；父文件与模块均不随包发布。打包时已只读核实它等于实际校准输入。
- `CLASS_RECOVERY.json` 明确 `883−3+16+3=899`，实际三源码产生 37 类，emission 共 936 类；`DEPENDENCY_PINS.json` 固定 106 个 Maven JAR 的顺序与 hash。类/JAR/运行库字节不随包发布。
- `REPRODUCTION.json` 保留实际 typecheck / emission / codegen / build / run 的 role 化 argv、环境和资源上限；`reproduction/compile_link.sh.in` 是原 28-TU 串行编译/链接命令的路径替换模板，不调用 Make。

这是**源码 + 明确依赖/输入闭环的手动重建包**，不是已在新机器验证的 hermetic launcher。需另行准备并验证工具/动态库/header closure、输出目录、CPU/内存/日志/进程 ownership 与清理边界，再分别准入 native 阶段。不能把这里只读检查或 synthetic parser 测试算作新一轮 DUT 成功。

纯文本检查（不调用 JVM、编译器或 DUT）：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 verify_package.py
PYTHONDONTWRITEBYTECODE=1 python3 -O verify_package.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_public_helpers.py
# 可加 --repo <固定源码 checkout> 逐个核对公开引用。
python3 extract_core_input.py <重建的 original-high.fir> --check-only
# 输出父目录须事先存在；只允许新文件，绝不覆盖。
python3 extract_core_input.py <重建的 original-high.fir> --output <fresh>/inputs/Qwen2ContinuousBlock.raw.fir
python3 check_calibration_output.py <另行准入后的 calibration.log>
```

`ACTUAL_FACTS.json` / `EVIDENCE_PINS.json` 绑定既有证据；`MANIFEST.json` 约束全部小型文本。包内没有权重、NPZ、数组数据、IR、生成 SV/C++、ELF、类、JAR 或批量日志；打包阶段未启动 native、未清理旧文件、未改其他项目、未推送。
