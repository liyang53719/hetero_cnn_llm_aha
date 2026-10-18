# Canonical runtime RAM：纯源码 tiny 行为复现

8 个生产候选 hpp、两个测试 TU 和 runner/cold 原字节来自已实际运行的 runtime gate v2；本目录没有 native 重跑。10 个 C++ 输入由 BUILD_INPUT_PINS.json 固定，19+19 Python mock 冷测可独立复现。项目源码来源见 SOURCE_PIN.json，路径相对 repository root，仅为来源证据；编译只依赖本目录固定文件和使用者现有 C++17 工具链，不读取旧 attempt 或 payload。

## 已观测的有限结果

原实际运行的 O0、O2 -DNDEBUG 各通过186次 check，结果相同。是同一测试逻辑的两种构建，不是372个独立case。四个生产默认构建的负编译均实际 exit1，且匹配其目标 private API；九个 stages 全部 cleanup确认。安全数值见 BEHAVIOR_SUMMARY.json；摘要不替代独立实际审查。

该结果只覆盖1024 B合成 arena、私有测试 adapter。adapter_runtime_bound=false、canonical_input_sha_verified=false、full_host_ready=false、launch_ready=false。新版未实际加载真实 canonical16；旧14.69s加载PASS不继承。没有真实模型/Host/EDA执行。prefix=true/generation=1 复合负例先被 workspace allocation 门拒绝，不能宣称独立覆盖 permit 门。

## 实现与权限边界

RuntimeOwner::canonical() 固定四区、38 allocation、16 expected输入；单一 payload allocation+mask。输入 RO；仅 N0 allocation 有候选写权限，guard/virtual/GateUp/其它owner/workspace fail-closed。istream 按序、精确长度、SHA、EOF；seal/token复核同RAM。AW/W仅暂存，私有 B退休门全事务预检后noexcept提交，completion发布后才允许读N0。

生产默认无可构造退休事件或公开写/成功bool；私有嵌套adapter完整定义。CANONICAL_RUNTIME_UNIT_TEST 只在正测试TU定义，不得用于产品构建。真实生成模型到private adapter的连接待后继审查；旧 namespace/friend 适配及 fullHost fatal 未解除。对象借用要求 owner 比 session/adapter 活得更久；不承诺抵抗任意C++ UB/ODR破坏。

## 复现命令与预算

先运行只含 mock 的冷测：

python -I -S -B test_runner_cold.py
python -I -S -B -O test_runner_cold.py

经相应执行授权后，使用现有编译器和不存在的新输出目录：

python -I -S -B run_behavior.py --compiler c++ --output /absolute/fresh-runtime-attempt

runner 不安装软件；未来每次实际运行动态记录 compiler 真实SHA/长度/version。本包未携带本次系统编译器路径/SHA库存。输入先校验，再将同一已验bytes写入新build；不接受caller自报hash替换expected。

公共flags：-std=c++17 -Wall -Wextra -Werror -pedantic -fdiagnostics-color=never。正TU分别-O0与-O2 -DNDEBUG。四负编译分别-O0 -UCANONICAL_RUNTIME_UNIT_TEST -DNEGATIVE_CASE=1..4 -fsyntax-only，不编译正TU。环境仅固定PATH=/usr/bin:/bin与LC_ALL=C，不继承CXXFLAGS。

九stage串行，首个compiler_version wall5/CPU2；两次compile各wall30/CPU30；两次tinyrun各wall10/CPU5；四负compile各wall30/CPU30。每child AS256MiB、每文件FSIZE4MiB、core0、接受日志≤64KiB；每stage原WNOWAIT/kill-before-reap/5s清理保留。stage wall算术和205s、CPU算术和192s，另最多45s清理；不是父进程整体硬截止或整个系统内存上限。

正输出只接受严格八字段JSON、实际正整数checks、arena1024、scope全false，O0/O2结果必须相同。负例要求正常exit1、确认清理、恰一个来自固定负TU的对应private诊断；拒绝额外error:、已知资源/fatal/driver文本。解析只覆盖当前固定英文诊断形态，未分类普通上下文仍可能被忽略，不宣称完整compiler-output grammar。SOURCE里原8条构造混合诊断已进入cold；这些不代表实际compiler曾误PASS。

失败停止后续stage，无自动重试、不调hash或预算；RESULT/receipt/log/build/ELF保留在使用者本地新attempt。stage receipt PASS仅代表预期退出和清理，负例最终还需diagnostic判定。ELF/完整log/当前系统身份/生成metadata/真实payload均不在本源码包中。

## 投影说明

SOURCE_PROJECTION.json 固定原gate/source身份及逐文件投影；执行逻辑与C++不变。原SOURCE v2 manifest的total_bytes_excluding_manifest误记86061，按其真实成员应为86657；原资产保留，此处单独记更正，本包manifest按实际成员重新汇总，不继承旧汇总错误。
