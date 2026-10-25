# 冻结模型 C++ build-only：编译/链接与静态闭包

**PASS 仅为原 selected core/PackedClient 生成模型及冻结 normal_m1 harness 的实际编译、链接、静态 ELF/容器闭包。模型未执行。** 不是 M1行为、reset/握手/探针/数值、full128 RTL、full29、真实Matrix FMA、硬件时延或90% MAC利用率通过。原软件观测域PASS、全部Treadle/NoCSE CPU FAIL、SV checker FAIL/STOP 与 canonical todo/ongoing/done均保留。

## 实际结果（不上传二进制）

- 单次固定 `make -rR -j1`，原始45个active C++/header/Make字节不变；旧codegen的2个d/dat元数据单独park，不进入active Make。原harness/ABI/36 generated C++来源复用前一公开包，未重跑Verilator。
- **129 active build产物 /204,109,468 B**：45不变源、39个ET_REL对象、1个36成员普通ar、2个PCH、41个MMD及1个ELF。这里只发布hash/角色，不提交源bulk、对象、PCH、archive或ELF。129不是整个run根目录文件总数；其他监督/park/wrapper记录另由实际identity审查绑定。
- 最终ELF **3,338,824 B**，SHA256 `728664bc753d91099d20e9ce2ea4625cc6c971f518b8494290a486015d532b76`。独审静态entry映射、main/198模型函数定义、DT_NEEDED及递归5文件版本闭包；没有ldd或执行模型，不能替代动态loader/dlopen/文件读取全追踪或未来运行准入。
- 实际39个`-c`编译、2个`-x c++-header` PCH命令、1次link；MMD41份/182记录/58独特literal路径，**不是完整系统头闭包**。GCC完成magic/同checksum只证明PCH格式身份，不证明每次编译实际用了PCH或全部GCC兼容字段。
- 前后5,365 pins、12旧inventory+7 lstat inventory、1,129 aliases、275负端点与清理回收通过；不是持续全机隔离。CPU **185.996499036 s**，outer wall **186.32318790903082 s**，采样RSS高水位 **544,808,960 B**（非连续峰值），不是硬件block周期/吞吐。
- stock Make的**9个-Wno类别原样保留**，无额外抑制；可见warning/error行0不等于warning-free或启用全部warnings。`--assert`由原生成选项继承，不证明断言被运行/覆盖。

## 两条不能误称“编译失败”的历史

1. root2227预启动错误比较requirements文件SHA，发生于Popen前，没有worker/approval/claim；正确核对后另行正式准入，原预启动记录保留。
2. 独审第一次将所有41编译命令都要求带`-c`，错误拒绝合法的2条`-x c++-header`命令。修正仅审查分类器，保留初稿/小checkpoint并第二次有界只读审查；目标源码/产物不变，**没有重新build**。此处不是目标编译或数值FAIL。

## 最小复现材料

`source/`为实际原字节 `check_build.py` / `test_build.py` / r2 `inventory_guard.py` / `test_inventory_guard.py`。测试只创建小合成ELF/ar/PCH/文本与临时目录；其中标记`NOT_EXECUTABLE_SYNTHETIC_FIXTURE`的字节从不执行，不是保存真实模型二进制。

```
python3 -B source/test_build.py
python3 -B -O source/test_build.py
python3 -B source/test_inventory_guard.py
python3 -B -O source/test_inventory_guard.py
```

检查器是受限容器/格式门，不是通用ELF/ar/GCC语义或执行保证。`pins/BUILD_EXECUTION_ROLES.json`保留role化argv、环境、39TU/36archive/2PCH方案、工具/转发wrapper hash；旧Make默认warning策略、源级依据、私有supervisor和完整manifest只提供hash/role，不复制运行时缓存。已有公开harness、ABI重建、codegen证据见精确refs，勿用当前模型运行结果反向升级本次build范围。

新环境须另行审核完整编译工具链、默认搜索/loader/headers与别名/缺失槽、原__ver.d parked规则和相对布局、预算/清理。下一次模型运行必须独立冻结/准入/实际独审；本包不含未执行run候选。harness的3-reset初态差异、脚本化Matrix、owner字段/背压覆盖缺口和864 accounting非MAC边界仍沿用原源级审查。
