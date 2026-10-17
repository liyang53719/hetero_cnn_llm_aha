# 原SFU loan两种profile的原子边沿契约

独立后继小片，不修改已固定的budget与resource-ledger候选。仅metadata冷模型，明确覆盖当前production enableBinaryAdd=true的private-drain分支；同时保留false旧profile对照。没有数值、完整prefill、RTL、EDA或wall-cycle/80/90验收。

## 原源码合同

来源冻结production v2 VectorSilu.scala:165–199；QwenOwnerProtocol.scala:143将enablePublic21QkvReduction传入enableBinaryAdd，实际生产reduction选true。

- false：p.result.valid=loanActive&&vector.result.valid；内部result.ready仅由外部ready驱动。abort置sticky loanPoison，但held外部结果仍须外部ACK排空。
- true：p.result.valid额外要求!loanPoison&&!abort；内部result.ready=外部ready||loanPoison||abort。因此abort时外部result被抑制，已accepted向量继续计算，到内部result出现后私下消费，不等待外部ACK。
- 两者request.ready都受!loanActive&&!loanPoison&&!abort及vector.request.ready约束；active结果退休同edge不接受下一request。
- p.drained只表示!loanActive；即使drained，loanPoison仍使busy/resetRequired保持，必须协调reset后才可重用。

Profile枚举为构造期选择，API没有运行时setter，不能把已接受的false事务改成true。一个LoanContract代表同一个SFU16池；不能并列实例化两profile充当两套可并行硬件。

## 原子edge输入，防止调用顺序伪造协议

每个tick一次传入完整edge的request、ordinary_idle、vector_request_ready、vector_result_valid、外部result_ready、abort及内部divider/pulse观察事件。先验证所有输入，再用pre-edge active/poison计算fire，最后一次更新状态。

abort与result/ready同edge的两profile行为由同一次tick决定，无Python先后调用差异。true抑制外部result并private_drain；false可外部fire但publication_allowed=false。新request在abortedge和旧result ACKedge均不接受。

ready默认False，调用者必须显式供应来源；不以默认ready伪造bank/staging供数。vector_result_valid是外部观测/合成测试刺激，模型不预测其出现时刻。

## 既有divider债务

内部事件只表示已接受full-SiLU的原phase2，不是新增外借Div端口。完整16lane一起接受内部division，逐lane pulse只可退休已预约bit，不能重复、丢失或在接受同edge返回。正常full-SiLU结果必须见过这一步且所有pulse已退；错误terminal允许在尚未进入division前结束，但不能跳过已有pulse债务。

wrapper abort不会取消已接受向量的内部FSM，因此旧事务可以在abort后到达division phase；这仍是同一原事务，不是新外部工作。true-profile直到内部vector结果真实出现才drain，绝不按预估周期提前清loanActive。

仅允许原SiLU和true配置已有BinaryAdd；没有新增masked lane、独立Exp/Div或Attention primitive。BinaryAdd不能接受divider事件。外部gate/up payload与BF16/flags数值不进入模型。

Request.tag、result_token是测试审计身份，原FfnSiluLoanPort没有这两个新增硬件字段。本片不扩展原ABI；token一致仅证明metadata保持，不能替代16lane实际数值payload稳定性验证。

## 测试与范围

在目录运行`python -B -m unittest -v`及`python -B -O -m unittest -v`。

13项normal与-O冷测均PASS；请求mode要求精确str，拒绝重载相等或str子类伪装，非法输入原子拒绝。

覆盖两profile同刺激对比、abort前/后已held结果、abort+外部ready同edge、迟到内部divider接受/pulse、部分pulse/重复/未预约、early error、原BinaryAdd、不免费ready、held身份、poison后禁止新工作及禁止runtime profile切换。

SOURCE_PINS.json只有逻辑production_source根下的相对路径与SHA；不是消费者已经验证的声称。独立review按冻结字节核对。算术值/flags、真实返回延迟、bank供数、Q/K/V物理staging、完整Host、与资源ledger的接线均仍unresolved。此模块是后继adapter候选；整合时替换旧SFU adapter，不能与其叠加出第二个资源池。
