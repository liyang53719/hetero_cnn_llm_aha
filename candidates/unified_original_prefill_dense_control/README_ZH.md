# 原始 prefill Dense 公共接线 r2：9 项短控制回归

此候选包含原字节 8 份 Scala：公共 runtime Dense 解码、真实原
StreamingDenseOwner 客户端及 group lease 桥、Qwen2 public21 数值边界与
legacy tag 适配，以及对应测试。它不是新的模型专属算术阵列。

## 实际完成与边界

- 8 源 fresh typecheck 成功，新增 31 类，原 642 依赖无类覆盖。
- 同一次测试命令的 4 个 suite、9 个短控制 case 全通过并独审；含五 profile
  同一 DUT 解码、B1 当前/既有 fault 与终态、B2 held job/result 在 stray 下保持、
  Qwen2 PC / storage / K split 元数据、非回绕 epoch 谓词。
- 这些测试模拟 Matrix lease/completion，未实例化完整客户端 SRAM / feeder
  ACK 数据通路，未执行 retained endpoint 算术。Qwen2 ordered reduction 检查
  是元数据契约，不是完整数值回归；没有五块 M128、RTL 回放或利用率通过。
- 公开的 Qwen2 92 源原入口已有 M16/M128 prefill FSM。公共 plain StreamingDense
  客户端必须拒绝其 route1，不能替代 QKV 两段 K / pairReverse / transposed
  resident vector fold，也不能把 BF16 数值误当 BF16 存储。
- 已 valid 的 job/result 不因 late fault 撤回或改 payload；父层必须合看 sticky
  resetRequired 和真实 final fence。未知/错 identity 不能假退债或伪造 drain，
  某些失联路径需外部隔离 reset，不声称有界自行恢复。

原 B1/B2 STOP、原冻结及失败证据均保留；本包是独立 r2 overlay，不表示根目录
生产入口、当前已发射统一 SV 或完整 block 已切换。新模型 backend / GDN / Scalar
候选不混入本包。用户主顺序保持：五块原始 Chisel 完整 M128 数值先；冻结同源、
输入和参考后，再生成同一固定 4096 MAC / 同接口 RTL 并回放五块。

## 重建而非隐式执行

`REPRODUCTION.json` 是经过精确逆投影的角色化命令与原预算。
`${PINNED_CLASSPATH}` 必须按引用的固定 106 JAR 顺序和 hash 还原；625、642、673
类分层需逐项无 shadow。角色化命令本身不是已执行的 hermetic 环境。
`SOURCE_REFS.json` 引用既有公开 admission / preserved ABI / overlap 依赖链；
不上传原 classes / IR / runtime / 权重。任何新的运行仍需独立资源与一次执行准入。
