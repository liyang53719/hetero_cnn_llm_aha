# Qwen2 QK16→softmax/PV 对应关系进度与下一片

## 当前结论

整体仍为 **INCOMPLETE**。本次只完成源码绑定、整数坐标及静态拓扑小门，
不是新的模型层、Scala/Chisel 行为或 RTL 数值验收。

- [x] 普通 Python **55/55** 测试通过，`-O` **55/55** 通过；独立复核一致。
- [x] 真实 Python 请求/结果选择与 Scala 初次/保留结果选择，在尾块长度
  1..16 上完成 **2,176** 次有序整数坐标比较；完整块为 **256** 个唯一单元。
- [x] 核对 16 项有序归约、dot materialize、缩放、score materialize、
  同一 score 写入与 max 更新、score-minus-max→ExpNegative 的源码连接。
- [x] 补齐独审发现的请求/结果转发、初次选择循环/索引位宽、exp 终点检查，
  并加入对应变异反例。固定源码身份门也拒绝任何输入字节变化。
- [x] 两种 CLI 均返回 **INCOMPLETE / exit 2**，报告逐字节相同。
  不求值 BF16/FMA/exp，不比较缩放常数数值，不声称算术或时序等价。

代码与证据：`candidates/qwen2_qk_softmax_correspondence/`。
精确测试与输出见 `validation/VALIDATION.json`、`validation/GATE_REPORT.json`。
报告 SHA256：`86b13f748916d2f8eb30e900f1e74f70c02550d2b5affe483fa28a9a290f8ab8`。

## 不混淆历史、主线与模型结果

源码参考提交为 `cacc259d8893754b8cae968b5355ccf37e5b79cf`。
本门选择的历史 production QK16 postimage SHA256 为
`31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68`，
对应 `production_qk16_rebase/POSTIMAGE_PINS.json` 中的 Qwen2Block 条目。
同提交裸主线 Qwen2Block SHA256 为
`9572763a636e77362f82d9fb6d8d9bc823be2ef1beda88929e227abd78a4b2d4`。
二者 **MISMATCH**：裸主线没有该 production QK16 选择路径与 official
materialize helper，attScore 正文也不同。历史快照不能改名当作当前生产实现。

这里裸主线与选定 postimage 的 MISMATCH，是既有 source recipe 组合产物与裸源码之间的预期身份区别，不能据此说仓库缺少该架构或需要重写完整 block。既有 `production_qk16_rebase/classcompile/README_PORTABLE_CN.md` 已说明重建入口：`production_qkv_reduction/replay.py` 生成生产输入，`attention_qk16_owner_route.prepare.compose` 生成原 QK16 donor，再由 `production_qk16_rebase/build_source.py` 组合并按精确 92-source selector/pins 核对完整闭包。原 classcompile 的资格也只限于已钉源码编译，不是 Scala 行为、elaboration、RTL 或数值验收。另一路历史完整 M128 Python entry 使用 PackedSchedule 与已验证 ELF，未执行 Scala；其模型层结果不能替代这个 Scala 源码组合/启用路由的证据。本静态门仍保留原冻结 `GATE_REPORT.json` 的 MISMATCH/INCOMPLETE，不改写成生产闭包通过。

历史真正 cold M128 模型层结果继续保留：提交 `8ba333c7`、run `39017864296`，
`PASS_FRESH_SAME_HOST_M128_ASSIGNED27`，27 项 assigned / 28 项 observed。
这不是两个 M1，也未被本门重跑或继承。完整 29 项仍缺 explicit mask tensor；
softmax_fp32 仅为已观察的诊断项，没有获准的官方 FP32 逐元素容差。

## 尚未关闭的清单

- [ ] 当前生产完整五文件闭包与实际启用路由，而非单个历史 postimage。
- [ ] 六头调度与逐头 softmax/PV 的对应关系。
- [ ] 共享 bank scratch 的 ACK/release、384B panel 的真实资源约束。
- [ ] PV6 供数、保留 context、全部最终债务汇合。
- [ ] Scalar 异常策略、完整 mask 观察及官方 softmax_fp32 验收。

## 下一工程片：接回既有生产路径，不重写完整 block

1. 以现有 `candidates/qwen2_resident_matrix/production_qk16_rebase/build_source.py`
   及其 SOURCE_PINS / POSTIMAGE_PINS 为入口，在新的隔离候选中明确完整五文件
   闭包。只核对所需增量：HostBlockTop→QwenOwnerProtocol→Qwen2Block 的选项传播，
   packedQk→MatrixPipeline/PackedAttentionStreamClient 的既有端口连接。
   不直接覆盖裸主线，不把已钉历史文件冒充完成集成。
2. 以 Qwen2Block 的 `attNextKey→attExpRead→attPVStart` 为最小控制接入边界，
   对齐 Python `attention_packed_owner/schedule.py` 经 M16/M128 patch 组合后的
   六头 score/softmax/PV6 阶段。先把“哪一个头、哪一块 score、哪个已确认 bank
   写入允许进入下一阶段”接到真实接口，并验证阻塞时不提前推进。
   原 rebase 明确保留逐头 softmax/PV，不能仅靠本次坐标 PASS 宣称已具备六头/PV6。
3. 在上述控制与资源义务有真实证据后，才接回已有
   `portable_same_host_m128_launch/run.py` 与 `attention_packed_m128_same_host/entry.py`
   的完整 block prefill 路径。继续复用已钉官方 Qwen2 L0 来源与原阈值，
   不编造 mask 数据、不增加容差、不用单 token 循环代替 M128。

以上下一片尚未执行；本次没有启动新模型、native、Scala、RTL、EDA 或 CI 作业，
也没有重启旧长 RTL 运行。顺序仍是 Qwen2-1.5B 完整 block 优先，随后
Qwen3.5-0.8B 与 35B-A3B 各 L0/L3。
