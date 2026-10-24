# Vector16 默认关闭的 finite-Mul UF 后端接入

日期：2026-10-23。范围仅为既有 `Vector16` 的主机软件算术选择与 GDN
完整驱动的身份检查，不是完整 block、RTL 或性能验收。

## 实际接入

- `build_library(..., arithmetic_backend=...)` 与 `Vector16(...,
  arithmetic_backend=...)` 均默认 `legacy_host_postfix_uf_v1`。原有 legacy
  回执仍可使用，不从回执自动选择实现。
- 显式选择 `finite_mul_tininess_r2` 才使用仓库内既有
  `qwen35_uf_predicate_r2/vector16_tininess.cpp`。两份 C++ 源码均未修改，
  各有精确 SHA pin；新实现单独命名输出，不覆盖 legacy 库。
- 后端版本、源路径/SHA、ABI、ELF SHA 与原有编译器/完整参数/回执检查
  同时绑定。新后端缺少元数据、版本/ABI 不符、库或编译器改变均拒绝。
- 保留原 `Vector16` 类型、16-lane 缓冲、独占租约及全部计数。
  单独 `op` 与 `mul_add` 批调用仍经同一 C++ `compute`；批调用是分别
  舍入的 Mul 后 Add，不是 FMA。Mul 失败时不执行 Add。
- 异常策略独立选择：默认 mask30；显式 IEEE 策略仍为 mask28。选择新
  后端不等于放松异常策略，也不改变 Scalar、`prepExp` 或物理资源。
- GDN `full_driver` 新增默认 legacy 的 `--vector-arithmetic-backend`；
  冻结所选 C++ 源码，并报告版本/源/ELF/ABI。准入验证对象自构造时保存的
  只读基线，不接受重新贴标签；同时冻结真实函数、参数/返回类型与
  `errcheck`。快照重新验证磁盘库/回执与原构造身份一致。
- 回调返回后及生成报告前再次检查资源。最终回调篡改不能产生通过报告；
  即使报告校验也抛错，外层仍保留原错误及 FAILED 摘要。

这些 Python 身份检查防止意外替换，不宣称能隔离可任意修改 Python
进程内存的恶意代码。源码 SHA 与编译回执也不是外部签名或可信执行证明。

## 本轮证据

安全限定回执：`backend_selection_qualification.json`。

1. 独立复核的 58 项源/回执/控制测试全部通过，23.295 秒，
   1 CPU、512 MiB、120 秒上限；使用 CDLL tripwire，没有加载 Vector
   原生库。控制测试明确使用合成 owner/Scalar，不能作为数值通过。
2. 单次有界实际主机资格：两次顺序 g++ 驱动调用，构建两份
   既有 C++；3 项测试全部通过，0 跳过/错误/失败。测试 0.234 秒，
   含构建 payload 0.690314 秒，父级监督 1.001870 秒。
3. 数值覆盖为 70 个固定有限输入 × 两后端 × 两异常策略，共 280 次
   单操作检查，以独立 `Fraction` 精确运算/舍入为参考。另有 7 组场景 ×
   1/7/16 lane × 两后端 × 两策略，共 84 组单独操作与批调用对比。
   同时检查结果、flags、失败阶段和逻辑 issue/lane 计数。
4. R2 的正负 minnormal 边界保留相同舍入值，但得到 flags3；legacy
   为 flags1。mask30 在 R2 的 Mul 停止，mask28 可继续 Add。精确
   subnormal、阈值等号、overflow 和非 FMA 顺序均在上述小测试范围内。
5. 父级回执实际记录 exit0、未超时、leader 已回收、原监督进程组已
   观察到不存在。该观察仅覆盖该监督组；不是 `strict_cleanup.py`
   全身份扫描 proof，不推断其他进程或历史任务已清理。g++ 驱动可能
   创建工具链子进程，“两次”不表示整个执行只有两个 OS 进程。

## 已保留的失败与未运行项

早期独立冷测试在 512 MiB 上限下运行 51 项，20 通过、31 项 setup
发生 `MemoryError`/NumPy `ArrayMemoryError`，5.667 秒，无断言失败或
跳过；其中 13 项回执/源检查、5 项 coordinator 控制、2 项身份检查通过。
这是合成大缓冲与回调引用环的测试资源失败，不是算术失败。未覆盖原失败结果；随后明确
释放测试引用环，并移除控制 fixture 原来隐含的 Scalar 环境检查。
一次中间 CDLL tripwire 诊断还明确拦截原控制 fixture 的 36 次
初始化调用，这同样不是数值失败。最终 58 项复核不再依赖外加 GC 或
Scalar 补丁。

本轮没有执行完整 M16/M128、16-head 长任务、checkpoint/权重下载、
PyTorch 全模型对比、Chisel/HardFloat 硬件执行、RTL、面积/时序或 MAC
利用率验证。此前五类 block 的完整验收状态不因此升级。

发布内容仅包括源码、测试、说明及限定 JSON；不包含 ELF、机器绝对
路径、原始日志或私有输入。回执中的 ELF SHA 只是本次构建指纹，不能
替代在新环境重新显式构建和通过现有准入检查。
