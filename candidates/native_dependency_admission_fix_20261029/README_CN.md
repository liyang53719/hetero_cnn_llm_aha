# 原生 Verilator dependency 准入修复（TEMP，未执行编译）

原 LOCAL_DATA run40856253077 在 conditional_admission.py:113 失败，literal `previous compiled/dependency product`36B、SHA c7300115137928620cfee0cca32dbde94e706eca5d1f2c0734aa80585b99853a 与摘要一致。**原 CI 具体 offender 文件仍未知**，不能追认是某个 .d；archive/link 未执行。修复依据是已保存 native-only 输出真实含合法 .d，现 blanket 拒绝逻辑必然误拒此类输入。

官方 v5.032 V3File.cpp writeDepend（137–159行）输出单规则 targets、冒号、buildDepBin、source paths、LF；可选 makePhony 不在本固定合同支持范围。来源：https://raw.githubusercontent.com/verilator/verilator/v5.032/src/V3File.cpp 。本地已 pin 官方 verilated.mk 358–360行会 include wildcard *.d，因此不能不加验证地允许所有 .d。

新 gate 仅允许已知 Top/三个 child 的 __ver.d 与 Top __hierVer.d，内容仅支持无转义绝对安全路径的一行规则。拒绝 $/命令/recipe/include/赋值/分号/注释/模式/续行/额外冒号；目标限同一生成目录的 prefix 文件、精确 lib-create wrapper 或顶层已知 child args。外部 prereq 必须在已有 source/tool/actual gate pins；生成路径另冻结 hash。所有 .d 同时进入 derived pins 和 make closure pins，逐构建阶段原检查不变。继续拒绝 .o/.a/.gch、任意其他 .d、symlink 和 ../路径。未修改 frontend/nativeargs/硬件/driver/math/caps。

具体拒绝另写 generated_tree_failure.json，白名单摘要保留 relative_path、suffix、bytes、sha256、typed code，不靠绝对路径 sanitizer 解释错误。

测试：8项单位正/负例 normal/-O；1项摘要字段/恶意元数据测试 normal/-O。保存 Down 56690B __ver.d（71targets/329prereqs）和 micro 层级三份 __ver.d/__hierVer.d 正例 normal/-O。这些实际 fixture 的 prerequisite hashes 由测试读取实际文件得到，**仅证明语法兼容，不是生产来源独立资格**。生产依赖已有审过 pins。首次实际正例暴露 lib wrapper 与顶层 child args 名称，与真实生成文件逐项核后只加精确名称支持。无 compiler/EDA/CI/上传。

BASE.json记录精确已发布 source3185 原文件hash。旧包不覆盖；新源需独立审查后再组合唯一 LOCAL_DATA 启动提案。完整数值仍0/5。
