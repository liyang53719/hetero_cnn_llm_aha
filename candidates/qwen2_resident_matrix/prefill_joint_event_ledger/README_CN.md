# 联合资源第一窄片：metadata事件约束ledger

这是资源/端口约束骨架，不是整个六行有序metadata调度器；尚未覆盖M1/2、17-key尾块完整QK→score→softmax→PV依赖trace。它是单独的add-only候选，不修改已交付budget小包或冻结源。只处理外部事务事件，不生成数据、不运行浮点、不运行完整prefill、不编译RTL/EDA、不预测完成周期。冷测试使用synthetic_external标签；即使调用者选observed_external_unverified，也不自动升级RTL测量。

运行：在本目录`python -B -m unittest -v`及`python -B -O -m unittest -v`。使用Python标准库。SOURCE_PINS.json是源码依据身份清单，不代表消费者已验证原源码存在；root/path均相对，不含作者机器绝对路径。

## 已实现

- 16 bank读/写site约束与同址hazard；raw scratch一次只访问bank pair，写在accepted边沿物理提交，无RMW读。
- tile写在accepted边沿读16 bank并预约下一边沿write；下一边沿物理commit后直接retire/produced。实际tile写没有response/ACK端口，不伪造bank_return/ACK。
- raw scratch lease存活时排斥全部Dense/tile bank访问，不因地址不同而放行；begin与request不许同边沿。只有clean matching raw ACK且该边沿没有abort，written位才对后续边沿发布。
- 单Matrix group/context0；真实8 metadata、2 result credits。group→外部leaf command接受→step；各单一step/return/result ACK口每edge最多一次fire。done成功还需外部leaf completion接受、无metadata/result debt；未知completion时刻不能靠计数猜。
- abort前已经held的Matrix结果仍须排空；首次abort边沿仍按pre-edge非draining状态检查result credit并可能enqueue；下一edge进入draining后返回的emit才被丢弃，不占新结果slot；last尚未接受也允许drain后error done。
- SFU一个共享packet，不为Attention/SiLU复制资源；division在接受前预留active-lane返回槽；pulse必须匹配，不能重复/丢弃。最后pulse在前一边沿捕获后才允许包返回。
- ALU单包Add/Mul metadata持有。Attention通用ALU/SFU borrower全部proposed。仅固定16lane、完整SiLU且enableBinaryAdd=false旧held-result profile事件标actual-Chisel；subset mask或独立Div即使owner叫silu也标proposed。所选production enableBinaryAdd=true在abort时抑制外部result并私下drain，本骨架未复现该profile；report明确unresolved，不把旧held外部ACK流程冒充该生产模式。
- 每外层edge最多一次parent tick。ACK后不能同edge回收bank/SFU/ALU/lease/group。
- 所有ACK只发PublicationTicket，不同步返回success bool。必须advance关闭边沿后resolve_publication；无论abort在ACK前调用还是之后调用，同edgeabort都撤销发布。不可在edge中途提前依赖结果。

## 明确没有实现

- Q/K/V供数、重排、完整算术、FP32或BF16数据payload。
- Q128只在原Python schedule看见每次head/query读取一个128-word q列表；不证明可同时保存多head，甚至单head的物理寄存器映射仍未闭合。K256、V256、96-word panel同样未证明。can_supply一律False，并报告unresolved。
- 未执行任何真实Chisel端口；接口容量与禁止条件来自源码，不是仿真measurement。
- Matrix leaf返回延迟、DMA、Host最终ACK、普通owner完整状态机、bank电路STA均未知。
- 不提供feed_ready=True。新accepted与同edge abort是不合法组合，两种调用顺序均拒绝；可advance(edge, abort=True)预声明abort，仍提交前一edge已预约的RMW写。abort清scratch active/written但保留旧租约与债务供drain。Matrix error done还要求draining→finish的必要边沿，不允许瞬时结束。matrix_step_accepted只是重放外部声称已接受的事件，记录operand_feasibility=unresolved；它不是自调度器，不能据这些synthetic accepted事件证明可供数或可运行。
- 事件history、ids和PublicationTicket是软件审计metadata，不是新增硬件buffer；不记FP payload。ledger不模拟实际数值result稳定性，只维护匹配身份和占有权。
- 只单scratch context/6-row、context0和一个group；没有跨query缓存、双frame、FFN overlap或新FPU。

## 来源标签

SOURCE_PINS固定实际MatrixPipeline、VectorSilu、Qwen2Block、TransposedDenseBanks及raw扩展patch。report附源清单、manifest hash和event/latency provenance：

- actual-Chisel：已存在源码端口/容量，仍不是运行证据。
- source-candidate-not-wired：raw scratch源候选，未接生产kernel。
- proposed：通用Attention vector/SFU borrower，以及SiLU subset/独立primitive接口。

原始设计中把所有写都叙述为response/ACK过于宽泛；本实现明确区分raw写ACK与tile写次拍commit即退休。独立review指出并已修正：单口不能一edge多fire、raw lease全局互斥、Matrix completion与abort-drain、SiLU原端口不支持mask/独立Div、abort与ACK需edge级确定性。

## 停点

冷事件约束测试与独立review完成后交root小提交。所有输出固定numerical_execution=false、rtl_measured=false、accepted_80=false、accepted_90=false，不输出wall_cycles。下一片必须先解决真实operand/staging与owner接线，不能直接把ledger扩成周期预测器。

第二轮review修订：raw lease release同edge仍禁止Dense/tile重用；acquire要求当前bank site安静；abort与新accepted互斥；scratch stop清active/written；Matrix error done不得跳过drain/finish。ACK publication ticket仍以整个edge封闭后判定。

第三轮review修订：首次abort边沿Matrix不可提前绕过full result credit；仅下一edge的draining状态丢弃返回。tile accept与次拍commit均排斥全部Dense服务，不因另一物理口/不同地址可用就允许并发；反序Dense→tile也禁止。
