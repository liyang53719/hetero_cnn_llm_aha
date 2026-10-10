# U00.2：Attention 完整 block 连续执行与 CI 拆分

2026-10-10 UTC。本轮修改仅涉及构建产物交接、运行预算和 CI 调度；RTL、
C++ driver、FP 算术、原数值门限及完整 cold0→carried1 数据依赖均不改变。
完整 Attention 数值仍 PENDING，U00.2 ongoing、U01 to do、C02.2 OPEN。

## 原执行的真实结果

精确提交 `79bbe751b7b221023b02546860e213c16c07b2ea` 的
[run 38003994774](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38003994774)
于 01:27:04 UTC 失败。失败发生在 pass 进程的 3600 秒上限；总运行预算
18000 秒当时仍剩 11092 秒。总已用 6907.883 秒，减去名义 3600 秒得到的
约 3308 秒包含构建、捕获、参考、前缀和校验，不能称独立实测构建时间。

最后保留的完整日志事件为 run0、pc18、cycle 2512781 的读取；最后 ACK 在
cycle 2512775，error=0、final=0。pc18 是 FFN SiLU×up，已 ACK 79/112 拍，
尚余 1056 个元素；之后还有 down、最终 residual、fence 和整个 carried1。
尾部 ACK 间隔 2020–2034 周期，显示持续前进。日志末行截断，不能把该周期
当真正终止周期，也不能把前面的命令升级为独立数值 PASS。

两次同候选 ELF 的 4096 周期前缀事件/状态哈希一致，各耗时约 6.2 秒。
这是候选重复性，不是与旧 ELF 的同激励 A/B，也不是完整 block 验收。
两个数值 case 都未获得完整终态，MAC profile 没有成功全程分母，利用率留空。
原 native 完整门仍失败：baseline 11 项、AVX2 13 项，未改变精度阈值。

工件 `11654561907`：173023 字节，SHA256
`c5362f32ddf9b99b8182b45750cd42353a68339d5ddf7068d2456c732aaaee3b`。
已独立核对 656 个源码路径、769 次仓库 SHA 引用。工件只保留两份 compact
JSON，没有原 ELF、完整日志或输入字节；无法从 pc18 恢复原仿真状态。

## 一次构建、两套完整 pair、一个汇总门

新的公开 runner 保留原整体调用方式，并增加显式 build-only 和受信构建包的
单 case 入口。build job 只构建一次；pass 和 fault 各使用同一个封存 ELF/RTL，
各自从 reset 完整执行 cold0→carried1。fault 仍在 carried1 pc20 的最后写 ACK
注入，两个 token 之间没有 reset、checkpoint 注入或参考中间值预载。

构建包固定允许 15 个 ELF、RTL、源码/工具身份文件及 manifest；原始源码由
不可变 commit+path 引用，消费端独立 checkout。包中没有模型权重、NPZ、
fixture tensor、golden 或编译中间件。接收方使用 build job 输出的独立包 SHA、
commit、ELF/RTL/receipt SHA；拒绝缺件、额外文件、链接、越界路径和摘要漂移。
工具、编译 JAR、iDMA、HardFloat 在消费端重取并按原路径/字节复核；不重绑
receipt，不重编 DUT。新 emission 必须精确等于已记录生产 RTL SHA：
`e8b6ab6640ef0b932a0fc976b00b64998094d692698b4f8e134ead0911611510`。

每个数值 job 独立生成 fresh 官方输入与独立参考，保留实际 source/input/output
哈希及 native 失败。跨主机 raw hidden 可能不同，本次明确将两 case 视为同模型、
同权重的独立合法样本，不宣称跨 job 同激励故障对照。汇总要求权重、trig、
模型版本和完整源码/ELF/RTL 相同，并列出 raw hidden 是否实际相等；不以放宽
hash 比对隐藏输入变化。每个 case 内的两个 launch 仍使用真实先前写回的 KV。

预算为 build job 120 分钟、pass/fault 各 220 分钟、汇总 10 分钟，四个 job
timeout 上界共 570 runner-min；并行壁钟不能按此总和解释。构建内部预算
6300 秒，单数值 runner 12000 秒，其中同 DUT 连续 pair 上限 10800 秒，
保留 180 秒失败保全。基于旧不完整运行的约 8.7–10.0 ks/pair 只是规划敏感性
估计，不能称完整实测或稳定吞吐承诺。此方案显式改变阶段资源预算，不把它
描述成仍在旧 18000 秒总预算内。

汇总从可信 CI job 输出取得两份 compact 的 SHA，验证完整 mode 清单、原
数值/故障审计、实际输出与 MAC profile 日志绑定。任一 job 失败、缺失或身份
不一致都不能授予通过。失败时额外保留至多 48 条公开 MAC 计数记录，明确
complete=false、utilization=null，避免只有日志尾部导致早期计数丢失。

## CI 触发边界及未完成项

七个其他 Host workflow 增加狭窄的显式 diff 分类 job。只有列明的本次 Attention
调度、包交接、测试和中文记录修改可以不重复昂贵作业；未知/缺失 base、
删除、重命名、模式变化或任意 RTL、driver、其他数值源码修改都运行原全套。
既有 job 定义除逐字可剥离的 guard 接线外有变化也全跑，guard 自身失败时全跑。
每次分类记录 base/head/全部路径及原因；新 SHA 未重跑的门必须引用旧 SHA
同功能源码的证据，不能笼统称新 SHA 所有数值均重新通过。原 79bbe 作业保持
运行，不取消、不重启。本次除四个实际路线 job 外还有最多七个 5 分钟轻分类
job，以及原 payload/model-goal 轻门；这些 timeout 上界不是实测成本。

原完整 GDN 双 M1 已通过的历史证据保持不变；本次没有新的 GDN M128、
Attention 完整数值、native 完整精度、reset/restore、35B 或 PPA/90% 验收。
生成 RTL 前的 GDN M1 0.09381854% 乐观架构上界保持原定义，未冒充实测。

## 本地发布前核验

轻量回归普通 Python 与 `python -O` 各通过 540 tests、132 subtests，
分别耗时 28.79 / 28.67 秒。独立审查确认七个既有 workflow 除精确 guard
接线外逐字不变，并发现汇总环境缺 NumPy/PyYAML；已固定安装依赖并加回归。
原 173 个编译 JAR 路径全部满足固定 official Maven 来源检查；其重取接口
只收原 SHA，设置数量、字节和时间上限，不将 JAR 加入构建包或 Git。
这些是源码、调度和证据门的核验，完整数值结果仍待新精确 SHA 的 CI。
