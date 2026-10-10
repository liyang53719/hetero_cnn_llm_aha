# U00.2：复用原 ELF 的新激励官方 M1 核验

目的：把一组新生成、明确标识的两 token 原始输入送入原完整 Host DUT，
保存实际 prior KV、最终 KV 与输出，再对相同输入和实际 prior KV 执行固定
官方 layer3 的两次 M1 调用。原 run 38015586840 没有保全这些小 tensor；
本路线不能追认或冒充原 pass 的位精确复验。

## 冻结资源与依赖

- 生产 checkout 固定 `98c7d80f65c5f05b55726c5239a6e9ec15d1b53f`，工具 checkout 独立绑定本次触发提交。
- 原 build run `38015586840` 的包 SHA256 为 `1cfaf045ca58704016bfecff3f079b7fa708d1d7f7043b0fb014b5da61b7bfb1`。
- ELF SHA256 为 `f0f194342fe9ab70290069441f48b9863c6ed9ab9bcd5f3991c7f60168073263`；SV 为 `e8b6ab6640ef0b932a0fc976b00b64998094d692698b4f8e134ead0911611510`。
- 原 655 个构建源与包含额外三个官方参考脚本的 658 个完整源集合分别核验；现行工具源另行绑定，不重绑旧证据。
- 复用同一单线程 ELF、Matrix/iDMA/Scalar 资源和 strict-FP；不调用 Scala、Verilator 或 C++ 构建。173 个原 compiler JAR 身份仍按旧准入重建可验证环境，但不执行编译。
- 权重从原公开固定模型版本重新取得，只在 CI 本地使用；不进入 Git 或工件。

原函数的 GITHUB_SHA 检查假设只有一个 checkout。本入口先验证两个干净
checkout、各自 Git SHA 与工具触发身份，再仅在生产 worker 中移除不适用于
生产 checkout 的 trigger 环境变量，并独立保留原值；绝不把它伪造为 98c7。
生产 Git、全量源码和源字节检查继续有效。

## 一次执行顺序

1. 上传不超过 2 KiB 的 metadata-only canary，确认此时工件存储可用；失败则不进入模型或 RTL。它不保证数小时后配额仍可用。
2. 核原包、工具、ELF/SV、两个 source checkout。沿原工厂各执行一次 baseline/AVX2 capture，保留全部原 native 软件审计失败。
3. 在官方 M1 预检前保存 input_replay.zip：两个 raw hidden 共 4,096 B、原 trig 两行 256 B、受限来源/大小/SHA 元数据，ZIP 至多 16 KiB。此时标签为准备输入，尚未执行 DUT。
4. 用相同 raw hidden、trig 和原权重预检官方 M1 runtime、57 个 producer 边界及 cache 形状；接口或身份不支持时立即停止，避免先跑长 RTL 才发现参考无法执行。
5. 从 reset 真正执行一次连续 cold0→carried1 的完整 22 命令 pair。原 live session、物理 DDR 审计与 canonical 检查都保留；不注入中间量、cache 或 checkpoint。
6. 成功后先封存 49 文件实际数据包，再做官方比较。prior KV 取 carried command-0 的实际可写 DDR 快照，此时尚未 append；最终 KV 取末 DDR，全部 terminal 同时与真实 DDR span 对照。
7. 分开比较官方自有 cache 轨迹、canonical prior 条件参考与实际 snapshot prior 条件参考。原 operator `max_abs=0.03125, mean_abs=0.005` 和 block `0.05, 0.01` 不变。已有明确门限的实际 terminal/output/KV cache 超限时保存证据并返回 exit2；不以“测量完成”给出通过结论。
8. 核 final live/source/工具身份并上传明确白名单工件。配额或保存失败给出 RETENTION_FAILED，不自动重跑数值。compact 可回显日志，但原始 tensor 不编码到日志。

内部实际 GQA producer 目前没有导出，原未授予的独立 stage 门限仍未授予。
即使已有实际 terminal 均在限内，也只标记这些直接比较通过；不能关闭完整
native 隐藏节点门。原 M128 软件审计与这次实际 M1 对照分开，不删除旧失败。

## 预算和保全

只新增一个独立数值 job，最多 220 分钟（13,200 秒）；该数值入口仅由其专用
workflow/runner/tests 路径触发，不重启原 19 项公共 EDA。wrapper 总预算为
`min(12000, 13200 - 已过 job 时间 - 180)`，末尾单留 180 秒上传，wrapper
内部另留 180 秒失败检查/compact。实际 pair 最多 10,800 秒；启动前 active
剩余不足 9,000 秒就不启动，不临时延长。

成功数据包最多 256 KiB，其中 49 个 tensor 为 147,712 B，内部元数据最多
64 KiB。工件不含可下载权重、NPZ、完整 DDR、raw trace 或可重建 fixture。
compact 两份各最多 8 MiB，官方比较报告各最多 2 MiB，诊断尾部最多 12 KiB；
逐文件类型、大小、hash 与允许清单均核验。Git 只保存源码、测试、计划及摘要。

当前状态：源码集成和独立审查完成；185 项普通测试与 185 项 Python -O 测试
通过，真实 655/658 源闭包只读准入通过。尚未启动本路线的模型或 RTL，没有
新官方或硬件数值结论。M128、reset/restore、35B、完整 native 和 PPA 保持开放。
