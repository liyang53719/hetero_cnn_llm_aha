# 原始 mode-0 Attention 的共享 A KV 供数模型

默认关闭。此批次只实现软件传输模型和源代码约束，不修改 Chisel。

## 计划与状态

- 已完成：绑定原始 OfficialAttentionOwner 的 PV16 地址顺序、原始 Qwen2ContinuousBlock 的 K/V 读取点及 official_bf16 两处 Attention 数值策略补丁；固定来源散列。
- 已完成：使用 ParentLoan、原始 DenseReductionOwner 及同一个 A Banks 的传输状态机；独立核心请求、DDR 请求和 raw 请求债务。
- 已完成：26项测试在普通 Python 与 -O 均通过（各约2秒），source contract 检查通过；4096 条容量映射及原始位模式填充/命中检查；M1/M2 小规模源顺序轨迹；故障、背压、ACK、释放及排他控制测试。
- 进行中：独立审查软件模型及后续接口契约。
- 待完成：真实 mode-0 消费端连接、父模块 RTL 生命周期验证、M128 执行及数值/性能验收。这里没有这些 PASS 结论。

## 边界

数值锚点为 official_bf16/owners.py 的 OfficialAttentionOwner._attention，PV 每次16个元素。不能用 ResidentPV32AttentionOwner 替代。source_contract.py 固定完整原文件及方法 AST，并零模糊应用原有两处 Attention 策略补丁后固定 Attention 区域；只投影 K/V 地址循环，不执行或改写算术。保留 QK/PV Matrix 边界、BF16 物化、softmax 标量顺序及输出物化。当前 source checker 不是全块编译器。

Binding 关联已接受的 Attention 作业、owner、K/V 地址和输出跨度。M1..128，每个 K/V token256个 FP32 元素；全部地址64B对齐且 K/V/输出不重叠。K 占 line0..2047，V 占 line2048..4095；实际可访问范围由 tokens 限制。每次绑定/释放/故障清空有效位，不复用跨作业缓存。原始核心读 tag 为64位，允许0；内部 raw serial 为非零32位，耗尽即报错，永不绕回。

有效位只有4096bit（512B）。模型保留有界身份、请求和债务元数据，没有新增 payload SRAM 或512bit填充影子。唯一数据存储为原始 A Banks，命中响应引用其已有 raw held response；DDR miss 数据只在 raw write 接受的同一拍被消费。填充 ACK 后才发布有效位，再从 raw bank 读回供核心消费。Python对象/计数器不是 RTL 寄存器面积证据。

## 故障与完成契约

首次核心 KV 请求被接受后才申请贷款；必须等原父模块债务及 retained-A 失效完成。贷款成功后才发 DDR miss，Dense/Tile 排他由实际 ParentLoan 执行。DDR 返回 ready 事件与 fill 接受严格相同。匹配 DDR error 不填充，产生一次原 tag 错误回复。已选中的 supplier 在没有 DDR 债务时收到回复也会消费并毒化；默认关闭时忽略该未选中接口。DDR miss 一旦 offered，valid/身份在 abort 下仍保持到 ready，接受后等待匹配回复排空。外来/畸形 DDR 回复被消费并毒化，但不清除原 DDR 债务；仍须等真正匹配回复才能排空。若真正回复永不返回，模型不会虚构完成。

作业绑定后、首次请求前的父模块故障允许接受一次原核心请求并返回带 tag 错误，避免等待贷款造成死锁。任何 accepted 请求均保留债务到对应退休事件。abort 不取消已接受 DDR/raw 事务。held 成功回复在故障下仍保持内容、tag、error 不变；reset_required 为额外粘滞故障信号。

重要：现有 Chisel 核心没有独立 reset_required 消费抑制接口。本模型要求的该侧带是后续新增契约，尚未实现。消费者必须在它为真时抑制算术/发布并消费 held 回复以排空；不能假定原核心已支持。外来 DDR 回复不得直接送入原 memRsp 的 mismatch 处理路径。

terminal 是核心完成已可见的通知，不依赖 host result.ready；它关闭新请求。核心响应 valid/ready 消费后即撤回，不等待 raw ACK；ack_wait 仅保留 raw 债务元数据直到 matching ACK，禁止重复供数及提前释放。done_ready/released 是模型 tick 的退休事件，只有核心请求、DDR、raw ACK 及贷款释放都结束才产生；未来 Chisel 必须用稳定 completion gate 保持 active/mode0，直到所有债务释放。没有全局 Matrix idle 条件，Attention 可继续使用 Matrix。

## 短测试

从仓库根运行：

    python -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_model
    python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_model
    python -m candidates.qwen2_resident_matrix.raw_kv_attention.source_contract

M1/M2轨迹分别192/576个核心 KV 请求，32/64个唯一 DDR miss；计数来自接受事件，不将核心请求字节当成 DDR 节省。4096条覆盖是容量传输测试，不是 M128 Attention 执行。无硬件周期、利用率或数值准确率声明。

## 原始数值模型桥接准备

numeric_prepare.py / numeric_pins.json 固定52项原始依赖；test_numeric_prepare.py 供普通测试发现运行。numeric_bridge.py 为单独 opt-in 数值入口，使用原 OfficialAttentionOwner、ScalarService、MatrixService 和原独立参考，只替换 K/V 的供数路径。源码、构建回执和库必须全部验证；缺少 MATRIX_SERVICE_LIBRARY 时以 NOT_RUN 非零退出，不回退到新编译或模拟算术。

本地尚未运行数值桥接：缺少已验证 Matrix 库及真实 git checkout。实际 M1/M2 数值比较、故障消费者排空及其 PASS 均待后续；准备测试不计作数值测试。详见 IMPLEMENTATION_PLAN.md 的桥接章节。

准备验证：8项 preparation 测试在普通 Python 与 -O 均通过（约0.3秒）；包含源码漂移拒绝、缺库 CLI 非成功退出及纯协议 DDR 解码检查。未调用数值入口的执行分支。

    python -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_numeric_prepare
    python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_attention.test_numeric_prepare

后续显式数值入口为 python -m candidates.qwen2_resident_matrix.raw_kv_attention.numeric_bridge；需要已有已验证库。入口设置120秒协作式墙钟检查和每次200000事件上限；已准备在既有 Matrix CI 中显式调用；未增加新工作流或触发范围。

CI扩展已准备、尚未运行：在既有 qwen2-matrix-interface-frontend job 的普通 contracts 后运行一次 opt-in wrapper；继续复用已构建库，120秒总预算含清理，保持20分钟 job 上限。只保存 summary.json/source_hashes.json，不保存原始子进程输出。此准备状态不是数值 PASS。

CI wrapper 的15项冷测试普通/-O通过（每组约1.4秒），含真实短睡眠子进程组清理、严格摘要、输入漂移和缺库路径；与26项传输、8项准备测试合计49项普通/-O通过（每组约3.4秒）。这些测试没有载入 native 数值库。当前 wrapper 冻结58个仓库输入以及库/回执散列，114秒工作预算加5秒清理和1秒回执写入，最终绝对上限120秒。
