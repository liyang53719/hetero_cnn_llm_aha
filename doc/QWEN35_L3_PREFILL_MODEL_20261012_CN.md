# 0.8B L3 完整 prefill 模型接入

当前目标是实际128-token完整Attention block的软件模型，随后才在Chisel接入并重放冻结RTL刺激。前一项0.8B L0的cold128→真实carried128完整typed模型已在37b7de的记录中完成全部已分配数值门；对应Chisel/公共Command128仍有明确缺口，不能混为五block总验收完成。

## 官方BF16参考入口

新增capture入口使用固定模型2fc06364715b967f1860aea9cf38778875588b17、Transformers 14e738b5d0cc69aa27a95dde272aea41fde44f2f、Torch2.10 CPU DEFAULT和原checkpoint混合dtype。它运行原TextModel.forward，从真实BF16 embedding经过完整GDN0/1/2到完整L3，在L3输出后才停止；未执行其余层、最终norm和LM head。没有候选算术替换或向模型注入中间golden。

同一个原DynamicCache连续执行cold和carried调用。M16的fixture取0..15和128..143，真实cache长度是0→16→32；RoPE position有显式间隔，不能把它描述成128-token历史。M128才是0→128→256且位置连续。causal mask使用实际cache长度，保留原GDN history/state和Attention K/V的完整前后哈希、形状、dtype与原始字节。

模块钩子与ATen观察只读取实际输入/结果，不替换算术、mask或返回值；未观察到的内核归约树不补造。原57-producer契约与旧FP32门不变，此入口只采集官方数据，不授予数值PASS。后续需要把实际共享owner数据链逐项映射到这些观察，并沿用全部已分配数值阈值。

## 失败保全与环境恢复

每个raw tensor先写完并fsync，再追加并fsync一条带key/shape/dtype/bytes/hash的JSONL索引。只读恢复默认逐文件验证，拒绝完整坏行、重复key/file或内容漂移；仅可忽略未换行尾行。没有索引的raw文件保留，但不能猜key、造tensor或据此继续执行。模型构造前保存已核验的源码身份；普通异常保存失败回执，部分证据不算成功。

进程内120秒CPU硬限不能保证异常回执，SIGALRM也不是原生库内部的严格墙钟限制。调用者必须外部监督退出码/信号与墙钟/内存。已准备的单次监督为150秒外层上限、3GiB地址空间上限和256MiB捕获字节上限；这些是宿主预算，不是硬件资源或周期。

20:08 UTC原环境的M16官方采集曾正常退出，226个实际tensor共14,402,048B，manifest SHA4a22043eed901f9e959a63e76e2f75542cfb21e39ef1e1e12f1eb666de38dec2；随后唯一M128采集启动。20:10工具返回executor key changed/transport disconnected，原工作目录在当前环境不可见，M128没有可恢复退出回执。不能归因人为删除，也不能将其算数值失败或成功。原始M16/M128数据当前不可验证，因此旧采集结果只作历史记录，不复用为当前数值通过。

已在独立新目录从远端恢复精确37b7de及原CI工件。两份capture源码从可访问创建内容和补丁逐字恢复，最终SHA与旧版本一致，随后在新环境重新跑11项小测试；python -S也通过，证明该小门只需标准库。旧L0/L3权重可逐hash复用；固定runtime和额外29份prefix payload分别重新核验/恢复，不重跑已完成的GDN长模型。

## 2026-10-12 20:53 UTC：四阶段实际 typed 软件链

恢复后的新官方采集已完成。M16为226个tensor/14,402,048B，manifest SHA97f0ed29d5e3d7734ce3ed0648c91b2a2f60601176f5cff06d2d3db041e7f172；M128为226个tensor/73,176,064B，manifest SHA5e797279a26c9384122023b94c8541d925843ae02f8a5e263c234f344cfb152b。全部原始字节、23源码、29 runtime项及54份固定payload已核验。它们是本轮新的输入身份，不继承旧不可见采集。

同一 TypedMemory、三 A bank、MatrixService、Vector16 Add 和 Scalar 实例已真实执行：原始 L3 hidden→input RMS→packed Q/gate→K→V。每一阶段仅读取上一阶段已经实际写回且完成ACK的数据；启动前只初始化原始hidden、固定权重与输出哨兵。packed Q/gate是每头[Q256,gate256]交错的4096列，K/V各512列。输出需要真实终态被消费者接受后才发布，末V完成才返回前缀完成。

投影使用独立命名的 attention_l3_v1 通用分块参数：K1024分两段K512，段内BF16成对反序、FP32顺序累加，两个partial通过原共享Vector16 Add合并，最后BF16 RNE。参数不是所有模型的硬常量，旧GDN默认模式保持原合同。12组M16/M128、cold/carried、Q/K/V的独立完整形状参考共1,474,560个BF16值与该冻结官方CPU后台逐bit一致；本数据未覆盖FTZ/DAZ等全域边界，不据此宣布跨后台普适位等价。

实际M128 cold/carried前缀一次177.338秒正常EXIT0，8个真实accepted terminals、1,572,864个输出BF16元素逐bit等于各自原manifest绑定的官方节点，全部原max_abs≤0.03125/mean_abs≤0.005门通过且实测误差为零。独立审查重新核验了8份actual原始输出、40份源码快照、11份输入/权重/ELF/receipt/manifest快照和物理权重转置哈希，未重跑模型。摘要SHA8441936e5b90dbab00adcff2b6eefc34dda860d849e17a6a8ab6c5620c25d672。

每窗记录671,088,640个Matrix FMA、40,960次Vector16 Add（655,360 lanes）、1,572,864B真实写ACK，以及1,094,686个软件调度tick。4096个固定Matrix MAC资源不变；这些tick不是硬件周期，不能据此算完整block利用率。此前缀未执行KV owner；cold/carried只描述官方输入来源，不能称实际L3缓存续写已经验收。

M16原运行79.138秒已完成8个数值终态且逐bit相同，但最终元数据检查EXIT1：fixture运行时依赖循环覆盖了manifest局部路径，导致报告将最后依赖文件的hash误填为manifest hash。原FAILED摘要保留。只修变量绑定，新增回归；独立后处理核验原source/input/output预存hash和正确manifest，恢复为明确的POSTHOC身份验真，未重跑算术、未改原文件。完整M128随后使用修正fixture正常通过。

异常测试另外发现：Matrix失败排空后会保留poisoned lease等待reset，协调器原先错误要求失败终态也无lease。现成功仍要求清lease，失败只在全部物理请求退休后允许带poison隔离状态返回；真实首Q tile abort、hold完成、未启动K/V及拒绝再次acquire均有测试。之后仅补源码快照闭包和失败保全兜底，保留M128真正执行的runner源码快照；第三C++源原未复制到快照，其运行前compile receipt与ELF已有绑定，本轮独立补证，不描述为原已存在的快照。

## 当前清单与下一接线

- done：新官方M16/M128参考采集；实际typed input RMS→Q/gate/K/V双M128四阶段前缀；实际输出与官方8门通过；失败发布/模式切换/输入角色和形状前置拒绝小门。
- done：最终干净源码目录按workflow顺序新建Matrix/Vector小库，26项L3与316项原GDN测试全部通过，26个suite无skip、34份102,262B紧凑工件逐hash核验；全部12,885源码前后无漂移。首轮独立验证额外施加512MB虚拟地址空间限制导致25个MemoryError，原FAIL保留；移除该非workflow限制后137.40秒通过，最高单进程RSS约1.79GiB。未改实际数值或重跑M128。
- done：8ca23b28 三CI与L3/GDN紧凑工件逐源/hash闭环。
- ongoing：C03.2/C04.2/C05中的L3模型子链继续，不能关闭父项。
- to do：同实例Q/K Norm256→partial64 RoPE→KV双span fence→矩形QK/Softmax/PV→sigmoid gate→O/residual/postnorm/FFN/residual。Norm256原PWL/NR算术及原native失败/门限必须保留，新增数值差异要明确阻断。
- to do：公共Command128和Chisel接入，包括新RMS归约、投影分块、共享Scalar IEEE选择；当前软件通过不冒充这些硬件接口已经执行。

2b21d738的参考源码CI38304400698与payload CI38304400709成功，11测试、3源码/contract身份及1116B紧凑工件逐hash核验。本批新增CI只构建小共享软件库，运行全部source/synthetic测试；不采集模型、不下载权重、不生成RTL。实际大张量仅在本地保留，Git只提交源码、固定版本/hash、紧凑验证摘要和必要历史纯源码。

Qwen2完整cold M128、0.8B L0完整cold→carried M128维持各自已完成软件模型范围；0.8B L3完整block、35B-A3B L0/L3、Chisel/RTL及五block联合验收均未完成，S01/Q35A/U00.2/U01继续open。

## 2026-10-12：同实例 Norm256 / partial64 RoPE

8ca23b28 的三个原push CI均成功：L3软件门38308654550（26测试/4suite/50源）、旧GDN门38308654539（316测试/22suite/49源）、payload38308654572。7006B和21593B紧凑工件的ZIP digest、每项源对应精确commit、suite日志计数/hash与Matrix三源/Vector单源receipt均已核验；没有重跑M128或RTL。

下一批复用同一prefix、TypedMemory与Scalar，真正追加Q Norm256、K Norm256、Q partial64 RoPE、K partial64 RoPE。Norm保留原C1归约、32项PWL和一次NR，Gamma是FP32(1+原BF16weight)；RoPE保留原B1的四产品各BF16 RNE后再相加，后192通道逐bit搬运。没有使用head_trace/pair_trace的结果驱动owner。Norm输入/weight的原有限范围和NV/DZ/OF/UF拒绝策略保留；NX原flags可观察。

Q Norm的norm/gate分属两个真实物理span。新增publish_many先验证两个span全部实际write/ACK及guard，再一次发布；第二span错误不能先暴露第一个。每阶段必须收到实际accepted terminal才启动下一阶段。明确的软件abort边界：未被consumer接受的held success可被当前事务abort取消；普通背压保持结果稳定；已经接受的success不能追溯撤销。该软件sideband不冒充原Chisel拥有abort端口。

默认关闭的只读observer直接记录Scalar实际返回值，开启后保存Norm squares/mean/epsilon/inverse/gamma/scaled/weighted与RoPE两个产品/旋转/输出节点。开关两路输出、请求及计数一致的小门已通过；callback失败只能返回Observer错误，不能发布成功。宿主观察数组不是新增硬件资源。完整capture原始文件可在prelaunch做hash和finite完整性检查，但native中间值不进入执行输入；只有原hidden、checkpoint权重、已验证trig常量进入owner，数值比较在实际终态之后。

最终同源实际M16 cold/carried一次143.816秒模型执行、supervisor144.165秒EXIT0，共16真实终态；每窗425,984B写ACK、671,088,640 Matrix FMA、5,120次Vector16 Add。60份当前/执行源码、4 library/receipt、15输入快照、18actual输出、52observer文件及226native tensors已独立核验。每窗4个前缀门与后段22/57 producer＋5个gate/布局检查通过，BF16全部逐bit相同；FP32最大差2.86102294921875e-6、最大均差9.685754776000977e-8，原0.03125/0.005阈值不变。

这些是八阶段模型前缀的数值与控制证据。其余35/57尚未纳入这份统一producer观察集合：其中input RMS最终输出和Q/K/V四节点已有单独前缀门，RMS内部节点尚无本批因果观察；KV复制/追加与最终root fence、矩形Attention、sigmoid gate和O/FFN尚未执行；未据末输出或部分节点关闭完整block验收。同冻结60源M128于21:29:44 UTC启动一次，600秒软件墙钟预算；需以实际终态和独立原门比较决定结果，不能把M16扩大为M128。

完整后继接线优先复用既有Matrix正常模式与L0尾部，而当前正常模式仍固定旧Qwen2 mask1/QK8步，需显式矩形profile扩展且保留旧模式；cache采用新的K/V staging真实copy＋append，完整block末fence才更换外部root/length/generation。O为2048→1024，FFN为1024→3584→1024，可复用L0已验typed Dense/RMS/Elementwise。上述为待实现清单，不作为本批通过范围。


### 软件预算失败及检查开销修复

第一轮双M128在600.001秒内部墙钟预算处受控退出，supervisor600.434秒EXIT1。cold128已经完成八命令，carried128完成RMS/Qgate/K/V四命令，在Q Norm中断；没有owner数值异常，尚未执行最终官方比较。全部60源前后相同、失败保全无错误，已完成输出、未发布staging、观察片段和原FAIL摘要保留。没有用这些部分输出恢复或注入下一轮。

原因之一是纯宿主验真：Norm/RoPE driver每tick对全部已发布输入做raw副本与SHA，并重建coverage集合。M128 Q的1MiB输入和512B权重每tick产生2,098,176B临时payload副本、SHA扫描1,049,088B以及四次frozenset构造。这不是硬件传输或MAC周期。修复在接收时冻结完整guarded字节，每tick仍逐字节严格相等且检查同一coverage；异常容器仍走原frozenset规范化，bytearray基类比较与buffer视图防止自定义比较伪造。接收SHA与末终态前SHA均保留，字节/guard/身份/ACK发布门没有削弱。

这只消除重复拷贝/hash等常数开销，完整比较仍是每tick O(input bytes)，不能宣称解除平方扩展或硬件性能优化。新增的约1,049,344B Q+weight快照是宿主诊断存储，不计为新硬件bank。24项driver回归通过，覆盖实际producer非空coverage、字节/guard篡改、伪造容器、末SHA拒绝和背压下输出/请求计数一致。旧SHA附加检查对照并非执行 untouched 旧driver；原M16及失败M128的真正driver/test源码另行封存，旧PASS没有重绑到修改后源码。

第一轮干净workflow已完成82项L3/316项GDN，398个结果全部OK、无skip，12,911源及40份119,326B工件核验。上述仅两文件检查修复之后，在同一干净环境/已验小ELF上重验完整L3，旧GDN49源未变，316项原证据单独保留。新实际双M128按cold368秒阶段实证和检查成本，以900秒软件预算从原始输入重新执行一次；其终态尚待记录。


### 21:51 UTC：完整双M128八阶段前缀终态

唯一修复后运行522.223秒到达16个真实accepted terminals，supervisor522.733秒EXIT0、峰值单子进程RSS315,448KiB。cold/carried八命令分别260.033/254.122秒；每窗3,407,872B实际写ACK、671,088,640 Matrix FMA、40,960次Vector16 Add，以及Scalar Add1,016,704、Mul1,155,840、MulIeeeRne393,344、Div128、Sqrt128。软件tick每窗1,210,434，不是RTL完整周期，仍不据此报告MAC实测利用率。

每窗四个prefix gate、Norm/RoPE统一22/57 producer和五项gate/布局检查均过原门。RMS/QKV仍逐bit相同；新增Q Norm和Q RoPE最终BF16输出cold各4/262144、carried各1/262144处相差1ULP，最大绝对差分别0.015625/0.0078125，仍在原0.03125最大差/0.005均差内。不能称M128全bitexact。第一FP32差异在Q Norm mean，全部FP32节点最坏最大差2.86102294921875e-6、最坏单节点均差1.0628718882799149e-7；原C1/B1算术和门限没有修改。

独立只读审计重新核验60份执行/当前源码、226native raw、23source/29runtime/11payload pins、18actual outputs、52observer文件、七项seal和全部真实terminal/ACK，并重新比较原门，结果PASS。完整summary SHA3d60e35d0278fc1c09a902929949d24415e7fcfad842cb2b8c120cc52c1c3f02，独立审计SHAebdf1f2fabaed46b79a3db6ddda3290dce29e275fc1442d1d56e5ea60c1057d4。修复前失败run里完整cold的九份实际输出共3,407,872B也与新cold逐SHA一致，未将它们作为新运行输入。

最终L3轻门在原干净目录/已验ELF上90测试/10suite通过，14份工件和12,911源前后hash一致；原GDN316/22和49源同身份复用，未重建或重复运行。Git只保存紧凑指标/hash、源码和必要旧纯源码快照，实际输入/观察/输出留在本地。远端本批CI尚待提交后核验；本次只完成C03.2/C04.2/C05模型八阶段前缀子门，公共Command128、Chisel/RTL、实际KV续写及完整L3仍未完成。
