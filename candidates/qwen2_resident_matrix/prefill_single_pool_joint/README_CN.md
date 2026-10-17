# 单池 production loan 与资源账本的有界整合

仅 metadata 冷事件约束，不运行数值或 RTL，不产生周期预测或 80/90 通过。此目录是独立候选，三个此前冻结包未修改。

## 单一原子提交入口

Joint.tick(edge, abort, loan_signals, events) 是唯一变更入口。先检查输入形状，把两个状态与输入深拷贝，在暂存副本计算 loan 与资源事件，所有检查成功后一次替换两份状态。任一侧或批次后半段拒绝，原两侧状态均不变。snapshot 返回深拷贝；重复/跳跃 edge、嵌套 abort、旧 API、同边身份冲突均拒绝。所有 request_id 在适配层要求精确正整数，拒绝 bool/float 与已有整数键相等导致的错误退休。每个事件预绑定精确方法签名，位置参数和关键字参数中的任何显式 abort（含 False）都拒绝，避免 ACK 入口绕过全 edge 声明。

每个外部 tick 只触发一次原 ledger.parent_tick。events 仅允许已有 bank、scratch、Matrix 接口；事件列表的处理顺序是候选模型顺序，不是已证明的同周期 RTL 调度。延迟/返回/ready 全为外部未验证或合成观察，不能据此声明完整可执行 schedule。

## 一个 SFU16 池

唯一 SFU 活跃债务存放 LoanContract(PRODUCTION_PRIVATE)，ledger 的旧 sfu 字段永远为空。旧 sfu_accept/return/ack/divider_pulse 入口关闭，不可并列制造第二个池。原建议 ALU 入口全部关闭。报告中的 SFU 数量来自同一 LoanContract，physical_sfu_pools=1。

仅原 SiLU 和 enableBinaryAdd=true 已有 BinaryAdd；没有 Attention masked/Exp/Div primitive。request tag/result token 是审计身份，原硬件 ABI 没有新增字段。

abort 在全 edge 预声明，传给生产 loan 和父 ledger。已接受向量继续内部计算、预约 divider debt、收 pulse，到实际内部 vector result 才 private drain；外部 result 在 abort/poison 下被抑制。已消费 error 的 loan poison 同 edge 阻止 ledger 新接受并禁止 publication，这是保守的候选整合规则，不声称已有 Host RTL error 传播时延。

## 复用与源映射

ledger_base.py 是已独审资源包 model.py 的字节副本；loan.py 是已独审两 profile loan.py 的字节副本。UPSTREAM_PINS.json 固定这两个候选身份，SOURCE_PINS.json 固定原源码证据，逻辑根由消费者指定，未假装已完成消费者验证。

原 loan 握手来自 VectorSilu.scala:165–199；生产配置来自 QwenOwnerProtocol.scala:143；bank raw/RMW、Matrix credit/结果保持语义沿用原账本引用的冻结 source pins。整合 adapter 标 candidate，原握手标 actual Chisel contract with unverified external events。物理 Q/K/V staging、真实 bank→lane 供数与数值仍 unresolved；can_supply 恒为 False。

## 冷测

python -B -m unittest -v test_joint
python -B -O -m unittest -v test_joint

覆盖双方非法输入回滚、批次后段失败回滚、重复 tick、关闭旧入口、共享身份冲突、abort 与 result 同 edge、迟到内部 division/pulse、error poison、单池计数和 snapshot 隔离。此目录不包含完整 M1/M2/M128 数值或资源 schedule 验证。
