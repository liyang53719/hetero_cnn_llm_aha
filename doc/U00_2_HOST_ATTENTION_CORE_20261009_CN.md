# 生产 Host 的 KV 追加与矩形 GQA core 接入

本项是 C03.2/C04.2/C05、S01/Q35A 的局部集成。默认关闭的 `bf16AttentionCore` 在既有 QKV、Norm256 和 partial64 RoPE 后接真实 KV 追加、矩形 QK/softmax/PV 和 core fence。当前实际 owner 小门禁与前端控制通过，生产整链数值 **PENDING**。未完成完整 Attention block，也未执行模型 cold128/carried128。

## 公开命令和同一物理资源

一个 launch 共12条 Command128、172条描述符和9次 owner 请求：前三个 Dense，Q/K Norm，Q/K RoPE，KV_APPEND，QK、softmax、PV，最后 core fence。QK、softmax、PV 在前端一起验证，再由一个 GQA owner 执行；三个公开 completion 仍按命令顺序发布。使用标准三根描述符与明确版本2的 ATTENTION_POLICY/ATTENTION_CONTEXT，未引入测试私有命令。

Q8/KV2、head256、context2048、BF16 权重和张量保持。KV 是 BF16 `[2,capacity,512]` 的同一 allocation，K/V plane 各1024字节每token；容量至多256，query 至多128。QK 是矩形 query×已有prefix加新token，PV读取对应完整可见长度。causal mask 绑定绝对 queryStart，不能用方阵或隐藏宽度替代 context 宽度。

所有 Dense、QK、PV 共享原 MatrixPipelineService 与八个 Matrix512 切片；Norm/RoPE/softmax 共享原 Scalar，所有传输走原 iDMA。新增 owner 仅使用这些服务端口。GQA 每次处理16 query行与32 key列；终值转换复用32个 BF16 converter，局部逻辑 buffer 50688字节。

## 写回与缓存发布

后继输入必须来自前面实际成功 ACK 的 producer。生产CI验收要求所有输出 allocation 以哨兵初始化，只预装原始输入、权重、gamma 和 trig。驱动已实现以物理地址为唯一索引、每个 completion 后复查整个DDR，旧输出、未使用尾部、逻辑score/probability保留区和guard均参与检查；实际生产执行尚待完成。

KV追加只能写旧length后的独立尾部，K和V两个span全部ACK才形成待提交proposal。GQA context 全ACK后仍处于待提交状态；仅终端 core fence 被接受后同时发布 cache root、length、generation、context及参数身份。V末ACK或context写ACK故障允许真实W字节留在未提交staging，但旧prefix和旧context保持；失败不发布第二个generation。reset清空可信checkpoint，尚未实现恢复API。

前一成功fence结束其Q/K/V、Norm/RoPE和逻辑score/probability临时区的生命周期，后继launch可复用这些scratch；最近已提交context、cache及参数身份继续受保护。生产两token驱动采用独立scratch allocations并检查旧输出共存；公开helper和RTL仍允许上述明确生命周期内的复用。

这里的 fence 只覆盖 core。完整block必须继续把发布推迟到 sigmoid gate、O、residual、postnorm、FFN/down和最后residual均成功写ACK后的最终fence，不能沿用本core的提前发布点。

## 数值合同与已验证边界

Norm保持原C1 reduce16/serial16/PWL32/Newton1和FP32(1+weight)。RoPE保持原B1：仅64维，所有乘积和终值BF16 RNE，其余192维不变。GQA按递增K做FP32 FMA并在QK/PV末端BF16 RNE，QK按1/16缩放后BF16，softmax使用冻结共享degree7指数和FP32步骤再BF16概率。参考入口要求独立integer/C复核所有QK/PV FMA及flags；当前已执行的检查是16384个合成FMA witness，实际官方输入的生产参考仍待CI。它是冻结硬件算术合同；新的native GQA stage门限尚未授予，官方context比较只作诊断，原完整native失败及所有既有门限继续保留。

KV owner的4项实际内存测试通过，覆盖cold→carried、双span末ACK故障、实际写入错误响应、reset后从真实DDR重试、32种非法job和合成128→128。它没有执行模型M128或生产iDMA。

GQA owner的5项实际共享Scalar、受控Matrix响应测试通过；35项独立Python参考测试通过。覆盖实际KV owner写回的cold→carried依赖、矩形部分tile、非有限和范围拒绝、scalar/Matrix/memory fault、最终ACK与reset。它没有执行实际Matrix阵列。Q17/K33跨tile门禁在本地编译资源守卫后、一次续编中出现cc1plus signal9，未开始仿真；原证据保留，不记数值FAIL或PASS，需持久CI执行。SIG9原因未被证明。

前端统一Scala编译及3项控制RTL通过，owner完成由测试替身提供；包含参数身份、跨launch缓存和旧context保护、错误字节/标签、末fence反压和默认关闭。原malformed测试把不poison的launch拒绝误写成poison，修正仅限测试期待，原日志保留。实际12命令Host数值仍待CI。发布前审查修正了测试serializer默认路径和公开helper的scratch生命周期规则：68项descriptor检查通过；仅测试路径变更后的Spec重新typecheck通过，先前控制RTL日志保留原Spec哈希，最终CI将执行当前Spec。

## 两token生产门禁与完整block下一步

目标在同一DUT进程中执行cold0→carried1两个launch。两条输入都来自同次官方cold_m128 capture中的相邻token0/1；第二条的carried指真实Host KV续写，不是上游GDN decode capture。baseline单来源投影参考仍是24头、10485760个独立FMA，不称全128参考。原cold0/carried127参考入口默认行为保留。

成功、V末ACK错误、context写ACK错误分别必须从真实前一launch的DDR/cache继续。只能由同次fresh CaptureSession及live projection/Norm/RoPE authorities授权生成和核验fixture；离线摘要或外部expected文件不能取得数值PASS。只上传紧凑summary和source/input/output hashes，不上传权重、NPZ或中间tensor。runner总预算18000秒，保留180秒失败证据窗口；构建和单个两launch进程分别最多7200/3600秒且受剩余总预算限制。整个live-authority执行位于独立进程组，退出、超时及中断均TERM后KILL清理后代，避免仅杀shell遗留构建进程；四种真实微型进程树测试已通过。编译driver显式O2，保留严格浮点选项，尚无提速结论。

完整layer3 block最小后续22命令：DUT input RMSNorm，现有QKV/Norm/RoPE与cache/GQA，BF16 sigmoid gate，O，residual，post RMSNorm，FFN gate/up，BF16 SiLU与乘法，down，第二residual，最终block fence。Norm和elementwise复用已接GDN的owner，Dense复用原Matrix。M128和carried128仍须实际全部128行、8Q/2K/2V heads，不以形状准入或首tile代替。

U00.2保持ongoing，U01保持to do，C02.2保持OPEN；S01/Q35A及三模型完整block不关闭。之前67e81的七命令CI与d7ce/67e81 GDN CI按各自精确源码身份记录，不用本次新源码重绑定旧结果。
