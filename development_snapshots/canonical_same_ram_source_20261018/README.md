# 独立输入 RAM 源码小包

本包只包含源码、源码校验值、中文说明和脱敏数值摘要。没有可执行文件、用户 tensor 数据、完整环境日志或旧机器审计文件依赖。当前派生版本尚未进行新的 C++ 编译或运行。

## 文件用途

- `initialization_ram.hpp`：生产候选 v2，180 行 C++17。命名空间是 `canonical_load_storage_v2`。它不是缺失的历史 `host_memory.hpp`，也不是完整 HostMemory。
- `v1_initialization_ram.hpp`：仅用于已知漏洞回归正控。v1 会保留 caller vector 元素的可写别名，能被缩短输入长度绕过覆盖封存；禁止作为生产实现。
- `test_initialization_ram.cpp`：同一翻译单元的合成小 RAM 测试，同时包含两个不同命名空间的头文件。v1 正控只缩短合法范围，不触发越界或未定义行为。
- `run_behavior.py`：独立复现入口，仅读取同目录三个固定源码文件。编译器由 `--compiler` 或现有 PATH 中的 `c++` 选择，不安装工具。
- `test_runner_cold.py`：纯 mock 的失败处理与相对路径检查，不启动编译器或 C++ 程序，不发送真实信号。
- `BUILD_INPUT_PINS.json`：三个编译输入的精确字节数和 SHA-256。
- `PROJECT_SOURCE_HASHES.json`、`MANIFEST.json`：本包源码/说明/结果的完整性记录。
- `SOURCE_DELTA.json`：三个 C++ 文件逐字节复制映射，以及两个 Python 文件的有限派生改动；其中七个核心 runner 函数与已执行版本逐字节相同。来源路径仅用于说明，不是执行依赖。
- `BEHAVIOR_SUMMARY.json`：此前使用完全相同三个 C++ 源码文件得到的有限真实行为结果摘要。

## 真实功能与限制

生产候选拥有一个连续 payload allocation 和独立逐字节 initialized mask。构造时先验证容量、名称、重复项、重叠和几何边界，再深拷贝 vector 元素及其 std::string 名称，最后分配数据和 mask。Caller 保留的元素指针、引用、名称字符指针不会改变内部输入白名单。

初始化只接受输入白名单内非空片段；整段边界和重复初始化检查通过后才写入。覆盖封存检查全部声明输入字节；读取返回同一 allocation 的 const view，并复查输入边界和 mask。未初始化、越界、重复初始化、提前读取、重复封存、封存后写等错误都会永久 poison，不能重开。返回的旧 const 指针无法被撤销，实际接入时必须保持私有。

封存只证明复制字节覆盖完整，不证明 canonical SHA、receipt、原始 stream framing/EOF 或 launch readiness。本包没有业务输出写、B 退休、SSA、prefix 生命周期、PhysicalObserver 或 resident DDR 授权。元数据 Gate/Up 分配不能因此获得 DDR 权限。

一般容量上限为 256 MiB payload，mask 另占同样大小；复现测试真正实例化的 RAM 最大仅 64 字节。超过上限的测试在分配前拒绝。标准 C++ 要求 source 指针在调用期间有效、无数据竞争且不强行修改 const 数据；本实现不是恶意进程沙箱。

## 已取得的有限实测

此前在 Linux、GCC 14.2.0、C++17 下，完全相同的两个头文件及测试 TU 得到：

- 190 checks 通过，编译和运行退出码均为 0
- v1 已知别名漏洞被安全复现；v2 保留原始覆盖要求并拒绝该绕过
- 24 字节合成数据从实际同一 RAM buffer 读回，与独立固定向量一致
- 合成数据 SHA-256：`f9919dde286ccd8649e31e2b2ebf19856e7de7725605d83d134180ca144a5392`
- 所有启动的测试进程组均确认收尾

这不是完整 Host、canonical payload、RTL、EDA 或性能结论。Portable runner 的新路径/编译器选择尚未 native 重跑；上述结果对应原 runner 的真实运行，不能扩大为本派生包装已经实测。

## 冷测与复现

包可以整体移动；不需要原 workspace、原审计目录或固定安装根路径。

纯 Python 冷测：

    python -I -S -B test_runner_cold.py
    python -I -S -B -O test_runner_cold.py

明确决定执行新的有界 C++ 复现之后，使用一个尚不存在的输出目录：

    python -I -S -B run_behavior.py --compiler c++ --output ./fresh-results

这里的可移植性指源码包位置独立；runner 有意限定 Linux 的 waitid/WNOWAIT，不提供跨操作系统兼容层。需要现有的标准 C++17 编译器。测试使用标准 scalar operator new 的只读分配探针，必须准确识别两个 64B backing allocation，否则失败，不猜测分配次序或对象布局。

编译墙钟/CPU上限均为 30 秒；测试运行墙钟 10 秒、CPU 5 秒；每个子进程地址空间上限 256 MiB，文件上限 4 MiB，禁用 core dump。编译器版本查询另限墙钟 5 秒、CPU 2 秒。所有输入先按同一份字节校验，再复制到新的 result/build。

子进程终态先由 WNOWAIT 观察并保留未 reap leader，确认原身份后处理原进程组，最后 reap。清理共用最多 5 秒；reap 后只读查询、不再向旧 PGID 发送信号。只有 reaped 且 group absent 才确认清理；未知状态保留为 FAIL。成功或失败都保存逐 stage 参数、输出、退出码、异常和收尾记录，并保留 build 供诊断。

测试自身只输出很小的合成数据。新的运行会动态读取所选编译器二进制，向本地 RESULT 写入实际 bytes、SHA-256 和版本。静态源码包不预置当前环境的这些值，也不删除未来执行的身份记录。新的运行记录可能包含执行者当前机器的编译器路径、二进制身份和工作目录；发布结果时应只分享需要的数值摘要，不直接公开整个结果目录。
