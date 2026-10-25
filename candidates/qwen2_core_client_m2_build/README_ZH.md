# 固定 M2 源码与 single-TU build-only

**PASS分层：** M2 harness/独立有理数期望/log checker通过源码与小合成资格；实际只完成1个新C++ TU编译及链接。**M2模型未在本次build运行**，表被编入ELF不等于断言执行。原真实M1限定PASS、全部旧FAIL/STOP保持；无新M2 run候选、M3执行或整体任务done升级。

## 最小源码与可逆差异

`source/`8个文件为原字节：M2 harness、reference/generator、log checker和其小tests、single-TU容器checker及tests。原ABI、模型源码与build来源复用公开refs；原PackedClient/SV/36模型对象不变。`M1_TO_M2_SOURCE.patch`仅将复制出的m1_main.cpp原字节变为m2内容，可反向恢复（名字保留以便可逆应用，成功后另存m2_main.cpp）。

新harness保持驱动/时钟/ready/队列规则，新增被动memory/PV/vector比较。960 memory、288 PV、828 vector期望由闭式source生成；精确有理数FP32 RNE→BF16 RNE仅限1、1/2、1/3，通过独立直接BF16整数RNE对照，**不是一般无double-rounding证明**。这些都是零输入/脚本端点控制，不是隐藏模型权重或实物tensor。

固定M2只走一个packed组中的j0/j1，源码oracle的M3也不跨16-key边界；不外推M17/128。M2 log门可比较每个OBS含pre-edge max，但memory/PV完整字段是将来执行的冻结harness断言，不是外部rawpacket重播。M1事实不自动证明M2。

## 本次真实编译/链接

- 复用7个generated文本header、1个36-member模型archive、2个runtime对象；另有M2源/ABI/expected header，共13不变输入。仅新增1object、1MMD、1ELF，**16文件10,643,235 B**；全run为28文件，不混淆计数。
- 最终ELF **3,392,368 B**，SHA256 `bd6c2879bab1ae6d09f0e39640edc4f781d81a24ce7ac376d484020dbba3e03e`。只hash，不提交任何ELF/archive/objects或bulk模型C++/headers。
- 独审新object/ELF的960/288/828只读常量表逐行一致；200函数名按模型marker筛选，**不是200个硬件模块**。5个已知运行库静态版本闭包通过，非动态loader/dlopen/文件IO完整追踪。MMD9 literal依赖不代表系统头完整闭包。
- 不运行make、不重生成Verilator、不重编旧模型TUs、不生成新PCH、不执行模型。空log来自不echo的固定launcher，不证明无warnings；stock9个-Wno仍在。
- CPU24.925332959s、outer25.23725252004806s、采样RSS472,801,280B；5338前后pins/19inventories、1129 aliases/275absence与清理通过。采样RSS非连续峰值，编译时间非硬件周期或M2 runtime预测。

## 必须保留的父Python覆盖缺口

原build runtime156文件中没有.pyc；`-B`阻止写cache，**不阻止读取既有有效cache**。旧过程没有import-open/cache-byte trace，不能追认完整父Python字节闭包或全机隔离。后继只导入探针不证明旧build实际读取集合；不回填/重pin/重build旧证据。独立的16产物内容和native编译/链接事实仍成立，这不是篡改证据或编译FAIL。详见PYTHON_COVERAGE_QUALIFICATION。

## 不运行模型的重建与测试

先按已公开codegen包`rebuild_harness_metadata.py`及其transitive refs重建ABI，取得其`harness/generated_abi.hpp`；本包helper核该header精确hash，并从小generator原字节重建81,256B expected_m2.hpp：

```
python3 -B candidates/qwen2_core_client_m2_build/rebuild_sources.py --repository-root . --abi-header ABI_OUT/harness/generated_abi.hpp --output NEW_SOURCE_OUT
python3 -B NEW_SOURCE_OUT/m2_source/test_m2_contract.py
python3 -B NEW_SOURCE_OUT/m2_source/test_reference_events.py
python3 -B NEW_SOURCE_OUT/m2_source/test_m2_build.py
```

再用`-O`重复这些纯合成控制。helper与tests不调用编译器/模型，不含真实SV/ELF。运行时环境与绝对路径只给role recipe/hash，非现成GO。任何实际M2运行须独立冻结runtime（包含cache身份/absence）、root准入和终态独审；真实Matrix FMA、128RTL/full29/90%MAC仍未知。
