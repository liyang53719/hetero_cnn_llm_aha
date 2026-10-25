# 原 selected-on Core：SV 生成事实与离线结构恢复

**新增 PASS 仅为固定留存 SV 的声明、top ABI、named-instance 闭包与声明存储容量门。** 不是通用 SystemVerilog 编译/合法性验证、表达式等价、完整 RTL 行为、数值或硬件利用率通过。所有旧失败和原回执保持不变。

## 四个独立阶段，不覆盖历史

1. 官方固定 firtool 1.62.1 处理原 selected-on CHIRRTL，**native exit 0**，实际留存 26,251,369 B SV，SHA-256 `77f61549b4aebd109362d30164f95422b9192d0a8b2b1599942a9360852f9225`。但原 Python postflight checker 拒绝多行声明 RHS，外层仍 `FAIL_FIRTOOL_SV_RETAINED`，root return 1；不是 native 编译失败或资源耗尽。CPU 29.336009772 s，outer wall 29.468828517012298 s，sampled RSS 545,742,848 B。
2. 离线 R1 接纳部分续行后，真实解析仍因 procedural assignment RHS 形式失败，`FAIL_RETAINED_SV_OFFLINE_RECHECK` 保留。一次专门语法 inventory 的 seen counts 没有执行全部 post-loop 门，不能回写成结构 PASS。
3. R2 只在源审/微型负控发现 reserved-word LHS 误接纳，**STOP 且未运行真实解析**。其冻结、STOP 和缺失的实际运行不能伪装成另一次实际失败。
4. R3 绑定固定 exporter 的 243 项/242 个不同保留名，保留词法上下文和全部 post-loop 门。独立的新 Python-only 实际运行 exit 0，`PASS_RETAINED_SV_STRUCTURE_ONLY`；aggregate CPU 1.7562658240000002 s，outer wall 1.869317336997483 s，sampled RSS 29,134,848 B。854 runtime pins、4 inventories、清理闭环。没有重新生成 SV、重跑 JVM/native/EDA 或执行 DUT。

原输入来自已公开的原 20 类/670,644 B 所产 selected-on CHIRRTL，**不是 NoCSE 17+3 类**；既有 probe 副本范围不扩大。native 和 parser 的 CPU/RSS 是软件资源记录，不是硬件周期/面积或 MAC。

## 实际结构结果与限制

| 项目 | 有限结构门结果 |
|---|---:|
| module definitions / syntactic instance sites | 25 / 88 |
| top ports（输入 / 输出） | 8,859（8,250 / 609） |
| 全模块 port declarations | 17,908 |
| named input connections 非空 | 4,921 |
| reachable modules / hierarchy depth | 25 / 5 |
| unresolved module/named port / dependency cycle | 0 / 0 |
| fabric 声明容量 | 16 × 128-bit × 2,240 |
| scores / probs 声明容量 | 各 32-bit × 1,024 |
| 另有可达存储 | 16 × 128-bit × 48 |

独立 actual 审查另作一次受限流式声明/实例/存储提取及五个 CHIRRTL top 类型的独立展开；它不导入或重跑原 checker，也有意不解释普通 RHS。完整 exporter-tail 词法门来自另审过的实际 R3 checker，二者都不是 SV compiler 或等价器。本发布阶段不再次打开/解析真实 SV、IR 或实际日志。

**未证明：** RHS 算术、连接表达式宽度/等价、中间 net alias、ROM/初始化内容、memory 读写时序或 latency、reset/行为/数值、综合、M1/M128 硬件通过、full29、物理时序/面积/功耗、有效 MAC 周期利用率或 90% 目标。12,387 个 continuation 只是词法计数，不是事务、MAC、进度百分比。无 initial block 的观察也不构成初始化语义证明。

checker 的 plain-lvalue 与独立括号/begin-end 余额只提供有限词法隔离，不证明 LHS 已声明/type 正确或确实归属 always/initial；平衡的 module-level 赋值文本也可能被接纳。固定 native exit 0 是独立编译事实，不能把该来源资格泛化为所有任意 SV。保留名集合是固定 exporter 的名称排除表（含宏与重复 PRINTF_COND），不是全部 IEEE 版本文法。

## 最小可复现代码与元数据

- `check_sv.py`、`worker.py`、legacy/reserved tests、`RESERVED_NAMES.json` 与 `source/ReservedWords.def` 为原字节。官方 commit 和三个源 blob/hash 见 `pins/FIXED_EXPORTER_KEYWORD_PROOF.json`。
- `derive_ports.py` 只去掉原带私有绝对路径的 `__main__`；所有解析/展开函数逐字不变。`test_procedural.py` 改用同目录 fixture，并以两个明确的合成 statement 替代实际 SV 摘录；其身份差异完全记录于 `pins/SOURCE_PINS.json`，不称原字节测试或实际 SV 重放。
- 不上传 1.05 MB 展开表：`EXPECTATION_TEMPLATE.json` 与已公开 CHIRRTL review 的五个 top 类型可精确重建原 `STRUCTURE_EXPECTATION.json`。输出必须为 **1,055,045 B**、SHA-256 `5bdfb398ac02c250ff40cb092dcbbb326b42236acae6da5cd4a059d8ed4e1e1a`；只读取小型元数据，不碰 FIRRTL/SV。新 helper 是包装程序，不是原 runtime 执行器。

从仓库根目录将本包复制至一个**新工作目录**，再在副本中执行：

```sh
python rebuild_expectation.py --repository-root /path/to/checkout --output STRUCTURE_EXPECTATION.json
python test_check_sv.py
python test_procedural.py
python test_reserved.py
```

`/path/to/checkout` 是用户自行指定的通用占位符，非实际私有路径。输出必须不存在；正常与 `python -O` 小合成模式分别覆盖 46 + 20 + 247 项。测试只能说明小型文本 gate/control 范围，不代替真实目标或硬件验收。已有完整输入的复现者须在独立、受限、已授权环境下使用 checker；此包的角色 argv/pins 不是完整私有 runtime config，也不授予新执行许可。

SV、ELF、loader 库、JAR/classes、Scala 源副本、用户输入/权重/参考张量与私有配置均不在本批；生成脚本、工具和大输入/输出仅角色/hash 绑定。下一阶段的 Verilator/harness/driver 尚不属于本包，不提前赋予 PASS。canonical 历史 todo/ongoing/done 不变，整体继续 **ongoing**。
