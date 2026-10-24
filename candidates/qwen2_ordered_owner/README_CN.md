# 默认关闭的真实软件 owner hooks 接入

## 结论与计划
本包依赖已发布 5109c30ab9eda147f5127c42dbb0a55d33a66363 的 qwen2_ordered_schedule。仅追加候选 overlay，不修改原生产路径、历史 pins 或证据。默认 ordered_fold=False；开启时必须显式传入同一 ordered_work 模块的 StrictLaneOps。没有默认宽松 backend，没有新增 ScalarService。

1. 复用既有 source-only composer，核对四份输入后安装 owner hooks、既有 schedule/work。
2. 在真实 Attention owner.tick、原 PackedClient 和原 physical driver 中推进 work，完成小控制回归及独审。
3. 本批到此停止。完整 block 数值、真实 native Matrix/profile2、完整入口/observer 资格、M16/M128 与硬件行为均仍 TEMP，另批处理。

## 最小变化及生命周期
owner_hooks.patch 对四份 selected Python postimage 给出差异；SOURCE_PINS.json 固定输入/输出、19 raw sources 和 harness/composer。ordered_owner.py 是新增适配器。

- entry.install 与 direct.bind/run 增加显式 opt-in 参数，原 DirectBinding、债务、scratch 和 ACK stall guards 不变。旧模式不分配 work adapter。
- hooks.action 检查实际 client.active、held/delivered、标签、服务 result 和 value 对象身份。work 借用 live PackedResult，不复制结果 tile。
- owner.tick 在 client 之前检查真实 done valid 与 matching terminal，错误先 poison 并屏蔽旧未接受 offer；已接受 memory response 债务仍按原协议清理。done_override 不能制造 valid。
- client 返回错误结果或错误退休时，仅对 packed QK 阻止 generator 前进。legacy PV 保留原有异常优先级。
- client 之后仅在 pre-edge/current state 均为 ordered_fold 时推进一步。新交付结果同拍不扫描；score 退休由 schedule 消费真实 adapter response。最后 score 后仍由原 PackedConsumerAck、client 和 service 完成消费与 done，适配器不自 ACK。
- abort 取消未退休 work，原 client drain 清债；foreign done 不被伪装为合法退休。

算术沿用冻结 strict 工作项：16 stripe finite scan、每 key 有序16 Add、BF(dot)、strict Mul、BF(score)，NV/DZ/OF/UF 与 finite 检查不放宽。16 lane acc 与 sticky fault，后 key fault 延迟到原序退休。软件对象不构成物理资源或时序证明。

## 复现
在包含本包的完整 main checkout 根目录运行：

```sh
python -B -I candidates/qwen2_ordered_owner/prepare.py --source-root . --output /tmp/NEW_OWNER_SOURCE
python -B -I candidates/qwen2_ordered_owner/test_owner.py --source-root . -v
python -B -I candidates/qwen2_ordered_owner/test_direct.py --source-root . -v
```

组合目录保留父层 composition 记录以说明历史组合步骤；最终源码身份以新增 ORDERED_OWNER_COMPOSITION.json 为准，父记录不冒充新后像验证。

输出目录必须不存在。prepare 仅组合源码，不导入 runtime/native，不生成 RTL。四模式将 -I 分别替换为空、-O、-I、-I -O。实际本批每进程限制1 CPU、CPU20秒、地址空间256 MiB、wall25秒；原日志与精确结果在 validation。不要用墙钟时间代替模型周期。

运行接入需要从组合后的 production_qk16_model.ordered_work 导入 StrictLaneOps 并显式提供返回 value/flags 的严格 Add/Mul、BF 与 finite callbacks，然后向 entry.install 或 direct.run 传 ordered_fold=True, ordered_lanes=该对象。测试复用既有 exact Fraction 算术 helper；本包没有证明另一调用方提供的 backend 正确。

## 实测范围
normal/-O/-I/-I-O 各15 owner +4 direct，共76项执行通过。覆盖真实 held 生命周期、同拍 done/最后 ACK 优先级、later-key fault 前缀、abort 各阶段、实际 memory 债务和错误响应、packed 错误结果/退休、legacy PV 异常优先级、默认路径与错误 opt-in 拒绝。

M1/M2 owner 控制测试使用原 RoutedScriptedService。direct 测试运行原 physical-memory driver，经实际 owner.tick 推进 M2 work：scan384/add384/scale24/retire36，严格 Add576/Mul36/BF72，物理读768、写命令/数据/ACK各192，owner acquire/release各1，scratch为0。Matrix/Host/Dense endpoint 与折叠路径之外的 ScalarControlAdapter 都是既有 synthetic 控制 fixture，仅 ordered lanes 使用 exact 算术 helpers，libmatrix FMA调用为0。这里绝不是完整 Attention/native/fullblock 数值 PASS；上一包独立 M1/M2 真 Attention 算术资格保持原范围，不能拼接成全链证明。

本 Python PackedClient 协议也不是 Chisel 模块执行。相关已发布 Chisel core postimage为 9120b040016116ae400389fe027bdb26e4b6d450faeeef6dba058108d32ba48c，已有 compile-only 证据仍仅类型/类编译。无 elaboration/RTL/频率/完整 block 固定4096 MAC周期分母，更无80%或90%利用率结论。

## 保留真实失败
开发中曾对 legacy PV 扩大错误 guard，导致 error+NaN 从原 Numerical 变成 Protocol；回归先失败，现仅限 packed QK 后通过。source composer 也曾拒绝过期 direct postimage，随后重基到已发布 SHA 5ac7d734… 并保留原 guards。另有测试读取外层 generator locals 的 KeyError，修正测试沿 gi_yieldfrom 查实际 schedule frame，不是生产数值故障。失败摘要及原日志哈希保留于 validation/DEVELOPMENT_FAILURES.json，未覆盖历史证据。
