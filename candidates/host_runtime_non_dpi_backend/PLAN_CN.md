# 非 DPI 后端：仅源码、字节运输和 Scala 编译证据（TEMP）

本批不更改 31 源硬件闭包。实际 R2 只编译 7 个 carrier/helper，得到 32 类、212672 字节；1001 类 baseline 保持不变。首轮缺 helper 的 14-error 失败保留。静态 24 输入端口契约来自原 companion，与 45 个物理端口核对；没有编入软件 FunctionalModel。

实际 C++ 检查仅 `HOST_DRIVER_CONFIG_ONLY` 和字节内存小测试：五份配置、561 个 C++/Python 边界探针；**Simulation 分支尚未编译，更未执行 DUT**。只引用已发布字节 provider，不上传源权重、探针字节或原始输入。

公开 6 份 Scala 源与实际编译字节一致；capture 另有一处旧未调用 validator 的私有路径，公开为单字面量脱敏模板，**该模板未编译，不宣称全行为等价**。`verify_capture_inverse.py` 可接收私有原字面量验证历史 SHA，但不输出或保存它。完整复现仍需原 capture、1001 类、31 源中的 5 个缺失父源、原工具和物理 provider；不是 fresh-checkout 复现。

真实 driver 源使用只读 affine 映射、同一 mmap EVP 全哈希、稀疏写回。512 MiB 是稀疏 payload 上限（还需元数据），不是缩小 2 GiB 地址窗口；模型非 LPDDR 时序。fstat 不保证不可变，必须外部独占只读；截断仍可能 SIGBUS。覆盖/重叠检查有 lazy 边界。模块 inventory 不是链接器，不允许据此去重。

下一门：先单独冻结预算与实际输入，再执行 capture/原 FMA provider emission、真实 Verilator/DUT 编译及协议验收；本包不会自动启动这些步骤。独立新 emission preflight 不属于本批。不得继承修改 admission 前的结构 PASS；全部五模型 M128 数值与 RTL 仍 **0/5**，MoE tie 未关闭，无性能或利用率结论。

公开轻量检查：`python3 -S -B verify_package.py`、`python3 -S -B verify_summary.py`、`python3 -S -B tests/test_assembler.py`、`python3 -S -B tests/check_layouts.py`，另用 `-O` 重复。它们不编译 Scala/C++、不读取全量权重、不调用 Torch。C++ 小测试源仅作为复现材料，发布阶段不重新编译；真实 fixture 仍由本地已发布 provider/父输入提供。
