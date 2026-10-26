# 产品接口恢复与同 SV 离线有限 PASS

本批仅提交最小复现源码、公开依赖引用、声明元数据重建器及独立实际审查的安全摘要。**不是完整五 profile block、provider 实施、4096 物理阵列数值/资源 fit、综合时序或 MAC 利用率验收。** 产品仍是 `UnifiedSharedResourceTop`；collection 和四个 FMA 兄弟仅为命名空间，不能替代产品接口。完整块 `mode0` 仍返回 UNSUPPORTED。

## 历史与新结果分开

| 阶段 | 精确结果与边界 |
|---|---|
| 已发布原 1020 SV | firtool 生成成功，但产品物理接口只有 4597/4599，原后验 **FAIL** 保留；旧 SV 与收据未改。 |
| 新产品源码 | 唯一 16 B `dontTouch(io)` 插入，Top 4542 B；可逆恢复旧 4526 B 源。其他八个增量源未改，不增加数据通路或缩小阵列。 |
| 新九源类型检查 | 真正编译 exit 0，68 类 / 568634 B，67 类逐字不变；仅 Top 类增加 119 B。不是行为或 RTL 结果。 |
| 新 CHIRRTL | 9678877 B，212 模块 / 211 实例；精确 9213 DontTouch＝collection 4616＋产品 4597，另 212 DedupGroup。去源码位置后的 212 个模块 body 与旧版本相同，只是受限文本比较，不是形式等价。emitter 日志为空，不代表完整 warning 覆盖。 |
| 新 1150 SV | firtool exit 0，22169147 B，SHA256 `d6eae625aaf4120e31e3e39aa3bbccced3acd8e3856f02e47a33c4bcc33f1fa1`；独立实际审确认产品 4599 口与七组 9308 ABI 完整恢复。但原 checker 期待标识符 `integer`，实际为 `integer_0`，原后验 **FAIL** 仍保留，不能重标为 PASS。 |
| 1227 同 SV 离线新门 | 不重发射、不改 RTL；仅把 `scalar_direct_families` 的一个精确 key 改为 `integer_0`，其类型与其余所有期望字节不变。独立实际审确认该同 SHA SV 经原 parser 的严格声明/ABI/资源层次门 **有限 PASS**：产品 4599、七组 9308、31 定义 / 65 实例。 |

固定官方 CIRCT 源说明 `integer` 为保留字，且无冲突、初始编号为零时精确得到 `integer_0`；本次实际新旧 scalar 模块均为此名字。**不允许任意后缀白名单、不忽略缺失子模块、不放松类型/端口/实例计数。** 新离线记录单独追加，不覆写原两次 FAIL。

## 通过和未通过的边界

- 严格声明图保留 8 个 512-slot endpoint 合同、8 ICG、16 vector ALU＋1 scalar ALU、单 Matrix service 和 state owner。外部 provider 的实现定义没有在此 SV 中闭合；8×512 合同不是已执行/有效完成的 4096 MAC 证据。
- 原 1150 有 **1 条实际 DedupGroup warning**，按 warning 类去重；不是只剩一个注解或 warning-free 的证明。离线 Python 不会消除该警告。
- 原 scalar/state/FIFO 受限字节/声明对比、ROM 常数与 32768 B FIFO 声明都不是数值、时延、存储映射或全芯片面积证明。
- 单 global lease 是串行资源资格化，不是最终 Matrix/vector 重叠完整块调度。Matrix 错误保留未 drained、poison/resetRequired；state 错误身份不 ACK。外部 exactly-once/no-stale、父层 fence/联合 reset 契约仍必需；无跨 job epoch 或失联 watchdog 保障。
- 本批没有 provider RTL 执行、完整五 profile block、SV 仿真、综合/锁存/组合环证明、4096 fit/PPA/时序、数值或 MAC 周期利用率结果。

## 复现源码与小控制

`SOURCE_REFERENCES.json` 固定已发布旧包及其他必要源的 commit/blob/SHA。其他八源、92-source 基线复现链、106 依赖顺序和 provider 身份继续引用旧包，不复制工具、类或大表。原 20 个 HardFloat 外部快照依赖仍须按 pin 恢复，不能把裸仓库目录当完整实际源树。

新 Top 是原字节源；`source/TOP_DELTA.patch` 可逆。新 CHIRRTL checker 与其 44-test 合成源也是原字节。`checks/chirrtl/STRUCTURE_EXPECTATION.json` **只把说明性源路径改为仓库相对角色路径**，映射记录在 `EXPECTATION_PROJECTION.json`。操作性期望字段未改，但 parser 返回的整个 expectation hash 因元数据投影会不同；不能冒充原私有配置或原报告字节。

在完整已核仓库布局中，仅运行纯 Python 小控制：

```sh
python -I -S -B candidates/unified_product_preserved_abi/checks/chirrtl/test_check_chirrtl.py
python -I -S -B candidates/unified_product_preserved_abi/tests/test_public_contract.py
```

两者也应分别加 `-O` 验证。新的元数据重建器复用固定旧 helper，重建原期望后只改一个 key；输出必须是新路径，拒绝覆盖及符号链接：

```sh
python -I -S -B candidates/unified_product_preserved_abi/checks/sv/reconstruct_expectation.py --output NEW_EXPECTATION.json
```

输出 1868091 B，SHA256 `c434688a68bab15900a0f109fd1b75566c4f095c7daa8ef404d02211a8adc31a`。这是类型/声明表，不是 RTL、权重或输入。可在独立临时目录复制旧包的 `check_sv.py` / `test_check_sv.py` / `derive_ports.py` 与此新生成的 `STRUCTURE_EXPECTATION.json`，运行原 46-test **纯合成**测试；不要指向实际 SV。包内 `PUBLIC_CONTROLS.json` 单列本次 normal / `-O` 各 44＋20＋46＝110 项，不等同硬件测试。

`REPRODUCTION.json` 的 compile/CHIRRTL/firtool 角色 argv 已和各原实际小元数据做逆向逐项核对；新增 68 类必须从新九源生成，classpath 只有原 557 baseline＋106 JAR，不得退回旧 68 类；625 类分开无重名合并。公开角色路径可重定位，不冒充原两物理依赖目录布局、原私有 launcher、GO 或完整运行闭包。它们不是自动串行执行脚本；真实工具/大文件重新检查仍需独立的限额、身份与执行准入。

## 证据层级

`ACTUAL_SUMMARY.json` 和 `EVIDENCE_ROLE_PINS.json` 分层绑定 source / typecheck / CHIRRTL / 新 SV 后验 FAIL / 同 SV 离线 PASS。原根门保存 expected rows＋source-bound passed checks，没有独立逐项 observed-digest map；这些根 launcher 是事后归档，**不是预启动自哈希绑定**。编译阶段采样 CPU/RSS 不是完整总量/连续峰值；CHIRRTL/SV 的终态 wait accounting 也不升级为完整资源证明。离线整进程 CPU 1.568084982 s、外层 1.7429658600594848 s，未保存 RSS 测量；配置的 256 MiB AS 上限不是实测 RSS。

独审复用已冻结同 SHA SV 缓存，未再次读取原 22 MB SV；其额外 24 个小系统端点哈希不等于全部 153 pins 重哈希。清理限定原进程组及已观察身份，不是全系统逃逸进程证明。所有旧 FAIL、证据缺口与 canonical 任务状态保持；本批 CI 仅检查公开包策略，不把目标变成整体 PASS。
