# 原前端阶段诊断：RSS FAIL，5 个收到的标记

**实际仍是 `CONFIRMED_ACTUAL_RSS_FAIL_WITH_FIVE_RECEIVED_PHASE_MARKERS_NO_PLAN`。** 这不是 plan、lint、8×512 fit、provider 数值或整体任务 PASS。独立终态审核 2,257 项（含 5 个 cleanup 负控；normal 模式单次）绑定 `pins/ACTUAL_REVIEW_HASHES.json`；source/mock PASS 与实际 FAIL 分层保留。

## 本次确实观察到什么

- RSS 采样高水位 **2,149,695,488 B**，超过 2 GiB 门 **2,211,840 B**。不是连续峰值证明。root exit 1、正常 worker exit `null`、cleanup 直接 leader `-9` 是三个不同字段；清理完成限原锚定组和已观测身份。
- outer **14.320325599 s**；sampled group+parent CPU **13.467568583 s**，final parent+waited-child **1.832441821 s**。后者存在 reparent/direct-wait 覆盖缺口，**完整进程树 CPU 未知**，不能作差称阶段 CPU，也不能取 max 冒充总积分。
- retained plan 为空，terminal structure checker 未运行；无 retained C++/header/ELF 不证明历史瞬态生成或具体停止 pass。17 原硬件/config 输入逐字不变，actual auditor 仅对本次 staged 副本 fresh 哈希；本包不重读这些大产物。
- 21 个终态文件共 **48,426,887 B**，只公布角色/hash。log 为 51,806 B /335 行：5 marker 行，330 个已准入 LinkCells 明细行。原 log 包含节点地址，**不公开**。

| 最后收到的入口标记 | 官方源位置 | parent 收到时刻 s |
|---|---|---:|
| module_cell_link_entry | V3LinkCells.cpp:633 | 2.971090030 |
| link_parse_entry | V3LinkParse.cpp:917 | 3.378984116 |
| link_dot_primary_entry | V3LinkDot.cpp:4353 | 4.968318368 |
| parameterization_entry | V3Param.cpp:1534 | 7.281121144 |
| post_parameter_link_entry | V3LinkDot.cpp:4359 | 7.954066639 |

586 次资源 sample 调用只有 **120 个周期/切换保存样本＋另存 latest**。6 个 label 的 all-call counts/peaks 是冻结 observer 源与收据约束，不是从持久化 586 行重算；原始全量 586 行未保存。`PHASE_SUMMARY.json` 保留两层证据区分。

最后标签首样本 7.954916729 s /803,553,280 B，latest 13.504707562 s /2,149,695,488 B：同一“最后收到的入口”区间 RSS 增加 **1,346,142,208 B**。这只提示下一步只读源码诊断方向，**不是当前栈、分配热点、唯一根因或函数 CPU profile**。接收时间不等发出/函数时钟；parent elapsed 含 preflight/staging。未收到 deadifyModules/hierarchy/full Width 标记不证明没有进入相关工作。

## 改了什么、没证明什么

- 沿用原 17 硬件/config 输入，增加缺失 timescale 默认 `--timescale 1ns/1ps`、精确七组 per-file debug level 与被动 observer。没有 global debug/dump/stats/build 或警告抑制。ParseImp 方案因可能生成 .vpp 在源码阶段被拒绝，最终改用 LinkCells；不是一次实际失败再试。
- 本次中断日志 0 Warning /0 Error 头，不等于完整 lint 或 warning-free。旧 0334 的 48 TIMESCALEMOD、旧 DedupGroup/W005 和 flat4096 资源 FAIL 原样保留。
- timescale/日志/observer 会扰动工作；不能把本次 14.32 s 与旧 21.29 s 比作速度或内存改进。
- root launcher 本次 Popen 前 hash 绑定；56 endpoint /31 absence /13 alias /3 freshcwd 前后保存 expected+逐项 source-bound passed，**不是独立 observed-hash/syscall 轨迹**。不回填早前 CHIRRTL 门缺口。
- 首次 wrapper 错读 FREEZE.files 而实际为 members，在 root.mkdir/claim/Popen 前 KeyError；仅两行 schema 修复，不是 native 重试。历史记录保持。

## 可复现部分与公开边界

`source/phase_observer.py` 与 `source/test_phase_observer.py` 为原字节；可在该目录运行 `python -I -S -B test_phase_observer.py` 与 `python -I -S -B -O test_phase_observer.py`，各 30 项纯内存合成测试，不读取实际 log、不运行 Verilator。这些测试仅 observer 资格，不把 target FAIL 变 PASS。

`source/supervisor_role_template.py` 是原 supervisor **仅一个 HELPER 绝对路径字面量**换为 `${STRICT_CLEANUP_SOURCE}` 的源码模板；变换及原/新 hash 在 `SOURCE_PINS.json`。无自动变量替换，**不是可直接运行的 launcher、完整私有 manifest/runtime 或新 GO**。包检查只逆向逐字/AST 核验，不导入或执行它。`EXECUTION_ROLES.json` 给出精确 argv、工具/hash、caps 与角色化资源门；先前公开 refs 提供原 17 输入身份及小 adapter/config。

官方源定位/hash 和静态 release 资格仅引用；不复制 ELF、机器地址或反汇编，不声称完整 CFG/source-binary 等价。本包无真实 SV/FIR、class/JAR/ELF、输入/权重、原 log/dump、cache、私有绝对路径或后继执行候选。CI 成功只意味着公开包检查成功。

**整体主任务仍未完成；没有 provider 数值、real FMA、full128 RTL、full29 或 90% 有效 MAC 利用率验收。没有授权自动重试、加预算或进入后继阶段。**
