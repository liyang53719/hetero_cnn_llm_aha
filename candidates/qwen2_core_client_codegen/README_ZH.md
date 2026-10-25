# 官方 Verilator codegen-only + 冻结 M1 harness（未运行）

**PASS 仅为实际 C++ 文本生成、固定 public ABI 与选定 Make 源文件闭包。** 尚未 C++ 编译/链接、执行模型时钟或验证 M1 行为/数值，更不是 full128 RTL、full29、有效 MAC 80%/90% 达标。保留所有原 Treadle/NoCSE CPU FAIL、SV checker FAIL/STOP 与先前 limited PASS；canonical 状态不变。

## 实际 codegen 的精确范围

- 官方固定 Debian Verilator5.032-1+b2，对同一原始 SV（26,251,369 B，SHA256 `77f61549b4aebd109362d30164f95422b9192d0a8b2b1599942a9360852f9225`），原 20 类来源而非 NoCSE 17+3；不重新生成 SV。
- 47 个实际文本文件 / **27,712,886 B**：36 C++、7 headers、2 Make、1依赖与1时间戳元数据。这里只发布逐文件 hash，不上传 bulk C++/headers，也没有对象/归档/可执行模型。实际全目录50文件 /27,756,163 B，另外3个工作目录为空。
- 独审核对 **8,859 public ports（8,250 input /609 output）**，名称/无符号位宽/方向/存储宏/引用形式；36个 C++源恰好一次列入 Make 分组、109个literal include边。不是完整预处理器/系统头/编译器/链接闭包，不证明函数体类型或语义。
- 实际 aggregate CPU **19.796118074000002 s**，root wall **19.975004745996557 s**，采样 RSS 高水位 **862,093,312 B**（非连续峰值）。前后3,754自动 pins＝3,752 manifest roles +2；12 inventories、13 aliases、24缺失槽、helper此次已纳入自动前后核验；清理/回收通过。端点证据不是全机动态隔离。
- `--cc --exe --assert` **没有 `--build`**。显式 assert选项已绑定 argv/原生元数据，但6个STOP调用点和两种断言拼写零匹配不等于完整断言清单/覆盖或运行成功。未运行harness。
- 日志“model needing 11.579 MB”是 stack+VarScope 静态估计，不是模型运行 RSS；CPU0.000不是实际零CPU。36 C++ /26.405 MB对应 C++加headers总字节27,687,931，不含全部47文件。8.618 MB/26内部modules不是实际SV大小/25声明数。VM_PARALLEL_BUILDS=1、threads1、verilate-jobs1含义不同，不是OS线程普查或后续build资源保证。无Wno但未Wall，不宣称全部warning类别覆盖。

## 未运行的 harness 与源级控制

发布原字节 `m1_main.cpp`、`generate_abi.py`、`check_m1_log.py`、原小测试，以及 `check_generated.py` 与合成文本测试。248＝52作者+196独立 **source/contract控制**，不是248硬件实验。正常M1仅零数据、脚本化Matrix，不是FMA实现；864 accounting512Steps＝96×8+96只是记账，非有效MAC/周期利用率。M2/M3/故障/foreign-tag以及W005 j1–7未覆盖；maxScore仅范围诊断；owner结果不是全部字段独立期望值验收。

新启动约定：先零全部8,250输入、randReset0，再3个reset上升沿，之后READY；原框架曾在test清零前reset1，READY后另reset2。不能推两者初态/未知态/时序位等价。源约定最多99,997 body edges +3 reset、408 OBS；这些都是尚未运行的契约，不是当前codegen观察到的行为。

## 只重建符号 ABI，不重建权重或真实模型文本

在完整仓库根目录运行：

```
python3 -B candidates/qwen2_core_client_codegen/rebuild_harness_metadata.py --repository-root . --output /path/to/fresh-output
```

输出目录必须全新。helper只读取已pin公开小CHIRRTL类型、原期望模板和源代码，调用纯ABI生成函数；精确重建 STRUCTURE_EXPECTATION、TOP_ABI、generated_abi.hpp、ABI_MAPPING，并复制7个原源/控制文件到输出/harness。大符号ABI不进Git；没有读取原始SV、运行Verilator/C++或含权重数据。原生成器与测试保留历史相对布局，由helper建立该离线布局；不直接执行其main去覆盖已有输出。

小检查可在输出/harness执行 `python3 -B test_source_contract.py`（及 -O）；codegen合成也在输出/harness执行 `python3 -B test_generated.py`（及 -O）。不运行任何真实模型。原私有supervisor/manifest仅hash与role描述，不冒充完整可移植运行环境。新build必须单独冻结/独审/准入，精确处理原__ver.d绝对路径、VM_USER_DIR相对深度、编译工具链闭包和预算；不自动执行。
