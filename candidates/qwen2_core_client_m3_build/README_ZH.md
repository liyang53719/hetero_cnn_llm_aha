# 固定 M3 源码与 single-TU build-only

**本批 PASS 只覆盖：** M3 harness/oracle/checker 的源码与小合成资格，及一次实际单 TU 编译/链接、静态表与产物闭包。**不覆盖 M3 模型运行**；后续运行即便存在也不纳本批。原真实 M1/M2 限定 PASS、所有旧 FAIL/STOP、canonical 任务状态不改，整体任务不置 done。

## 最小可复现源

5 个变更 Python 文件保持原字节。`M2_TO_M3_SOURCE.patch` 将已公开 `m2_main.cpp` 原字节变为 M3，反向可恢复；重建时命名为 `m3_main.cpp`。独立有理数 reference 与其测试复用公开 M2 refs。原 ABI/模型/SV/archive/runtime 不变，不重复上传。helper 只读取精确 hash 的源码与先前符号重建 ABI，不调用编译器/模型。

M3 新增 token2/head0 的实际 retire index 被动记录与 `[0,1,2]` 门；驱动、时钟、ready、队列逻辑保持。1728 memory、576 PV、1260 vector 行是闭式零输入/脚本接口描述，不是权重或真实 packet。`1/3 → FP32 RNE 0x3eaaaaab → BF16 RNE 0x3eab` 与独立直接整数 BF16 RNE 只在 1、1/2、1/3 上一致，不是一般双重舍入等价证明。

## 实际编译/链接（不是行为）

- 13 不变输入：7 个生成文本 header、原 36-member 模型 archive、2 runtime objects、新 M3 源/ABI/expected header。只新增 object、MMD、ELF；**16 文件 /10,759,877 B**。整个 run 为 28 文件 /10,782,937 B，计数不混淆。
- ELF **3,425,088 B**，SHA256 `f89687b5593c242325d88bba17048351cc9fde8d7fcb3662b666c1d4c0ada745`，仅 hash，不上传。
- 新 object 与 ELF 的 1728/576/1260 只读表逐字段静态核对通过，**不是运行断言或事件**。200 个 model-marker 函数名不是硬件模块数。5 个已知 native runtime/13 版本边匹配，不是动态 loader/dlopen 全轨迹。
- 无 make/codegen、旧模型 TU 重编、新 PCH 或模型执行。MMD 9 literal 依赖不是系统头完整闭包。空日志不证明 warning-free；stock 9 个 `-Wno` 保留。直接 shell exec linker 终态 0，间接 compile/assembler 各 exit 未独立序列化。
- CPU **25.199429895 s**，outer **25.493011227983516 s**，采样 RSS **474,587,136 B**；5397 前后 pins、19 inventories、1129 aliases、285 absences 及保存清理链通过。采样 RSS 非连续峰值，编译耗时不预测 M3 仿真或硬件频率。

## 新父 Python 门与旧缺口

新 build runtime **156+46=202**：42 当前 `module.cached` 候选及 4 stdlib source pin，root 前后字节记录相同，10 私有 loader absence 与 parent locale 门验证。42 并非 42 次独立观察到的 import opens；probe audit 含后续身份读取。`-I -S -B`、无 `-O`；`-B` 禁写 cache 而非禁读。当前 source/code 关联与已知端点资格不证明所有条件导入/持续隔离或完整父 Python 字节闭包，不能回填旧 M1/M2 build 的未 pin cache 缺口。parent locale 与 child 固定环境、parent 8 ELF 与 native 5 runtime 是不同层级。

## 不运行模型的重建

先依已公开 codegen helper 及其 transitive refs 重建 `ABI_OUT/harness/generated_abi.hpp`，再执行：

```
python3 -B candidates/qwen2_core_client_m3_build/rebuild_sources.py --repository-root . --abi-header ABI_OUT/harness/generated_abi.hpp --output NEW_SOURCE_OUT
python3 -B NEW_SOURCE_OUT/m3_source/test_m3_contract.py
python3 -B NEW_SOURCE_OUT/m3_source/test_reference_events.py
python3 -B NEW_SOURCE_OUT/m3_source/test_m3_build.py
```

用 `-O` 重复只验证这些小合成控制，非实际执行模式。helper 对既存输出/symlink/路径穿越/hash 漂移拒绝；生成失败可能留下新建部分输出，不修改输入。编译 recipe 只给 role 化 argv/环境及 pin，不是现成 runtime 或 GO。

**仍未知：** 实际 M3 行为、独立完整 Matrix FMA、通用 softmax、跨 16-key packed 边界、128 RTL/full29/物理内存/90% MAC。最大 3 keys 仍在首组内；所有 active QK 值同为 +0，顺序 index 门不能排除 j0/j1/j2 数值 alias 或一般 W005 风险。script accounting 2880 与 phase 数均非有效 MAC 利用率；旧 FAIL 保留。相邻 M17 下界/执行候选不在本包，也不获本包资格背书。
