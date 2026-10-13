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

完整后继接线优先复用既有Matrix正常模式与L0尾部。旧正常profile固定Qwen2 mask1/QK8步；23:04增量已完成显式矩形profile的模型小门，完整前后链仍待接线。cache采用新的K/V staging真实copy＋append，完整block末fence才更换外部root/length/generation。O为2048→1024，FFN为1024→3584→1024，可复用L0已验typed Dense/RMS/Elementwise。这些后继与完整block不由局部小门授予通过。


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


### 22:00 UTC：78e2f52 CI闭环与下一门的上游误差传播

78e2f52eec3b96c09d8552bb1cde0062e3f18426的L3 CI38313580146、GDN CI38313580056与payload CI38313580178均成功。L3为90测试/10suite/70源码，GDN为316/22/49；12,522B与21,585B紧凑ZIP的GitHub digest、精确commit逐源码、全部suite日志/退出/计数、Matrix三源与Vector单源构建receipt均已复核。此CI没有实际大模型或RTL重跑。

随后使用已封存actual Q-RoPE/K-RoPE，仅执行一次固定Torch全形状BF16 QK单算子诊断。先用native Q/K逐bit复现原cold/carried QK，确认该重放在本机与原capture一致；再仅换成真实前缀输出，carried K由真实cold+carried K拼接，完全等于原native cache。cold QK出现10/131072个1ULP差异、最大绝对差1.0；carried出现8/262144个差异、最大0.5，均超过原0.03125最大差门。乘1/16并BF16物化后cold仍有一个0.0625超限，carried最大0.03125通过。最坏cold的query87/key86属于实际因果范围，不能以future masking忽略。

这证明已知Q Norm四个/一个BF16差异能传播到下一原门失败；并未执行实际Matrix owner，也不能称其硬件缺陷。前缀自身的原门PASS不变，完整block质量门明确保持open。正在用全形状单节点反事实区分mean归约与C1 PWL/NR逆平方根误差，不替换官方输入来授予PASS，不降低阈值、不做单点调参。诊断原始结果与完整身份在本地保留，metadata SHA2319f512db9b20afd927312b2c1b9b0aa3f9dddd1a1d0a04e479b3b43e7c56d6。

### C2：修复已证实的归约与 inverse 差异

下一全形状官方 QK 条件诊断证明，旧 C1 前缀的 cold 4 个／carried 1 个 Q Norm BF16 差异会传播为 QK 的 10／8 个差异，最大绝对误差 1.0／0.5，超过原 0.03125 门。cold 最差位置 [0,3,87,86] 因果有效，不能靠 mask 排除。该诊断使用真正保存的实际投影、K cache 字节与全形状官方同输入运算；不是实际 Matrix QK owner 执行。旧局部 Norm/RoPE PASS、后继条件 QK FAIL 同时保留。

对全部2,560个Q/K head定位：2个原BF16误差来自均值归约顺序，另外3个来自PWL/NR inverse；只替换其中一项仍有差异。新增显式 C2 Torch210CpuDefault256 策略，按固定 Torch2.10 CPU DEFAULT V8/ILP4 的 H256 路径计算：每lane四个residue，每residue八项按32*t+8*r+lane递增求平方和，先fold residue0..3，再fold lane0..7；均值和epsilon保持FP32，复用现有Sqrt3再Div2(1,root)，其后FP32 gamma=1+weight和最终BF16 RNE保持。未注入官方mean/inverse，未按坐标分支，未放宽原有限输入域或阈值。C1仍是默认独立策略。

Add0/Mul1继续要求真实raw flagsValid和原fatal0x1e。现有Div/Sqrt只有result/error，C2按该真实协议消费并校验类型/finite，未伪造零flags；返回的root/inverse真正驱动下一请求。52项新旧小门覆盖C1 Q→C2 Q→C1 K→C2 K、opaque gate、成功返回值扰动、错误/末ACK/held终态及真实双span发布。C2真实双M16八命令已16终态成功，模型151.983秒，监督152.333秒，61源/全部输出与观察hash复核；22个已观察官方producer的FP32和BF16均零bit差。M16仍是0→16→32实际cache语义，不能称128-token历史。

独立全形状条件诊断从已保存实际M128投影计算通用C2，再执行原B1和官方QK；冷131,072／暖262,144个QK与scale字全部精确一致，旧18个QK差异归零，并复现保存原C1失败。这个条件诊断没有执行owner/Matrix/完整block。C2完整双M128实际前缀正在原冻结61源下执行一次，900秒为有依据的宿主预算，终态待验。

对应Chisel采用同一QkNorm256Owner的纯源码overlay，enableTorchDefaultPolicy默认false，C2显式开启；复用原treeValues(0..1)、lane和共享DivSqrt，不新增浮点单元或数据bank。操作状态寄存器从4增至5bit，选择/控制逻辑增加，面积与时序未测。六项静态/符号调度检查及独立源审查通过；没有可用的离线Scala/Chisel依赖，本批尚未编译、展开或仿真该overlay。它尚未替换生产源，也未接Host C2，因此当前模型通过不能称生产Chisel同策略通过。

干净源导出顺序复现：固定Python3.12+NumPy2.3.5+PyYAML6.0.3，重新构建共享Matrix与Vector小库，然后全部137项／13suite，无skip，116.086秒、最大单子进程RSS261,528KiB；源码及全部工件集合核验。没有读取原work数据、下载模型或运行RTL。新增KV staging候选34项仅合成控制门，覆盖真实地址copy/append、末双span ACK、poison后精确drain和新重试；仍需接实际K-RoPE/V及完整block末owner凭据，不能算实际M128 cache完成。

### 固定资源的精度路径风险

按当前模型每笔请求逐一映射到既有单BlockScalarFloat，C2每M128窗共有2,599,424次Scalar请求（C1为2,566,144）；基础请求启动间隔至少3拍，Div/Sqrt更慢。完整launch到terminal的保守下界为7,798,272拍，仅用于条件架构上界，软件tick不是该周期。

全L3逻辑Matrix MAC：Dense为128×(1024×4096+2×1024×512+2048×1024+3×1024×3584)=2,348,810,240；加QK/PV的2×8×128×keys×256后，cold keys128为2,415,919,104，carried keys256为2,483,027,968。沿仓库矩形逻辑MAC口径包含causal-zero项，是偏乐观分子。固定4096 MAC/拍、所有等待均计分母，U≤MAC/(4096×7,798,272)，即冷7.5635%／暖7.7736%；未计后续存储/softmax/FFN等只会更低。它不是RTL实测、完整周期预测或通用架构天花板。Matrix重叠不能越过同一Scalar服务的下界，今后的Vector映射需要重新给资源、端口、精度及完整周期证据；当前先完成数值链，不把此串行保精度路径当80%目标终架构。

### Matching-input QK 顺序FMA仍阻断后继验收

C2消除上游差异后，不能直接把“官方算子吃相同输入”的条件PASS当作当前Matrix配方PASS。对原Chisel Bf16CausalGqaOwner规定的d0..255逐次FP32 FMA、末BF16 RNE做独立C fmaf全形状预检，cold仍1/131,072、carried仍2/262,144字不同，最大绝对差1.0。暖[0,5,26,64]是有效因果位置（绝对query154/key64）：末FP32为131.49998474121094，BF16为131，官方为132；其独立精确有理点积也舍入到131，不能以更接近数学精确值豁免原官方门。其余两个差异位于future mask位置，仍保留原中间节点要求，不偷删门。

这个预检仅0.54秒、42.2MiB，FE_TONEAREST、无FTZ/DAZ，所见仅inexact；输入、源、编译器、ELF、输出及三条逐FMA见证已保全。没有改QK归约策略或资源，没有Matrix owner/完整Attention执行。后续必须定位通用且可映射到Chisel的归约/后台差异；当前完整L3数值项继续阻断，原max_abs0.03125/mean_abs0.005不变。

### 22:30 UTC：C2真实双M128前缀完成

同一冻结61源、原hidden/weight/trig重新执行完成16个实际终态，534.495秒模型／534.957秒监督EXIT0，最大单子进程RSS315,364KiB。全部7项封存、18实际输出、52观察文件和当前/执行source snapshot逐hash核验；每窗4个前缀门及22个已观察Norm/RoPE官方producer通过，后者所有FP32/BF16字均精确一致。原5个Q Norm/RoPE BF16差异在实际owner数据链中消除，原失败证据未改。summary SHA72d5c380f3c2a3d498d66191b5e67de27238e75456ba8e5a88014715cc337e71。

每窗真实记录Scalar2,599,424（Add1,055,104、Mul1,148,160、op6 393,344、Div/Sqrt各1,408），与源计数预测一致；ACK3,407,872B、Matrix FMA671,088,640、Vector16 Add40,960。软件tick仍1,210,434，因其不计Scalar服务延迟，不能从tick不变推导硬件加速。QK当前配方的matching-input超限仍是独立阻断，KV/完整Attention/O/FFN及生产Chisel C2均未完成。

### 23:04 UTC：显式矩形 Matrix 与实际 GQA 子链

478a542 的 L3 CI38317512609 与 payload CI38317512699 已成功。15,819B紧凑工件的GitHub digest、80个精确提交源码、13suite/137tests无skip、Matrix三源/Vector单源构建receipt均复核完成。没有在CI重跑实际M128或RTL。

匹配输入的ascending QK原FAIL保留。固定官方实际JIT使用oneDNN3.7.1 brg_matmul:avx512_core_bf16、VDPBF16PS；通用成对高半先行d1,0,3,2,…,255,254在完整cold128/carried128独立QK单算子逐bit吻合官方。原有数组和FP32 FMA保持，只改变已有Q/K缓冲的读序；当前证据域为实际正常数/零，不能扩称FTZ/DAZ或整个ISA等价。纯Chisel源码overlay以enableQkPairHighFirst显式开启，默认false，原ABI、步计数、clear/last/finish/emit和PV顺序不变；9项源码/符号检查通过，frontend/RTL未执行。

共享Matrix的软件服务新增profile1，QK为256步/slice0、PV为1..256步/all8，均只在最后发result，随后真正retire result、MatrixDone、owner terminal才能释放。profile0旧Qwen2仍默认且维持逐步reply。两模式共用唯一81,920B累加资源，没有新阵列。新增10门及原32门通过；同实例无reset的混合序列实际计数1,193,984 normal FMA、65,536 Dense FMA、533 normal steps、23 results、7 done，20个legacy replies只来自profile0。扩展源码曾触发编译器交换fmaf的a/b寄存器，造成20个双NaN payload位差；反汇编与原ELF对照后，以volatile函数指针固定host C ABI参数次序，有限数算术、阈值及硬件资源不变，原失败保留。

新GQA owner按既有Chisel形状保留Q16×256、K32×256、scores16×256、QK16×32、context16×256和V256，所有操作数来自实际64B读取，复用同一Matrix和已有Scalar ExpNegative/Div。18项小门通过，覆盖旧模式→Dense→GQA复用、真实末ACK、错误排空/reset/旧epoch和M17/cache33两种tile边界。独立review发现并修复held-success遇Matrix poison后driver卡住错误终态的P1；只允许同一未接受事务的成功撤回，成功握手后不可追溯撤销。MatrixDone类型与背压稳定性也严格检查。边界小门不是M128执行证明。

随后从已封存C2双M16前缀的真实Q/K/V写回，重放到同一TypedMemory、同一Matrix/Scalar与同一GQA owner，两次GQA完成。cold16、carried16分别4.23/10.03秒、各65,536B真实context写ACK；每次8个QK组和8个PV组、16个result/done及1个accepted owner terminal。QK、scale、BF16概率、context四项逐bit相同；FP32 softmax分别888/2757个bit差，最大绝对误差3.27825546e-7/3.87430191e-7，五项均通过原0.03125最大/0.005均差门。修复前后所有实际观察和输出逐SHA相同。这里是GQA子算子复验：cache由封存actual cold/current K/V做宿主布局装载，尚未执行KV owner/fullblock fence；位置0..15及128..143、实际cache16→32，不能称128历史或完整现场前缀→GQA链。

执行原summary SHA为82f08363bbbd44da9f2d9a389b148a2eea16c99a12854867460e8d93c5a198b4。15项执行源码和原始输出已封存；七项比较源码另行绑定不可变478a并对全部已封存actual重新比较，明确属于事后比较复核，不伪称执行前已抓全比较源。masked-logits原producer尚未完整物化，不从未执行的future arithmetic补造观察；五项通过不能替代57项完整验收。

干净新checkout按workflow顺序使用新构建Matrix/Vector库，209tests/18suites、94源、22工件全部核验，141.80秒；不读取历史work，无模型下载或RTL。对应证据为GQA_PAIR_ACTUAL_M16.json、GQA_PAIR_SMALL_GATE.json、MATRIX_RECTANGULAR_PROFILE_GATE.json与GQA_COLD_WORKFLOW.json。本批远端CI须按新精确SHA继续核验。

下一门：先将真实KV staging→GQA→sigmoid gate→O/residual/postnorm/FFN接回完整公开数据链，并对同身份M128做有依据的宿主预算。当前GQA逐tick覆盖集合检查在M128放大明显，任何宿主加速须保持逻辑请求、依赖、原算术和发布栅栏，不能记为硬件提速。完整L3、公共Command128、生产Chisel C2/pair策略、RTL、35B两个block及五block总目标仍open；完整周期和MAC利用率继续为空，不能套用这些软件tick。


### 23:28 UTC：原 CI 身份回归收口与实际 Sigmoid gate

97446dabb936675932e1928ee31c4040d1d35315 的原五项 CI 均已终态：L3 38320597518（209 测试/18 suite/94 源）、GDN 38320597548（316/22/49）及 payload 成功；两份成功 ZIP 的 GitHub digest、精确提交源、全部日志/计数及 Matrix/Vector 构建回执已核验。Qwen2 contract 38320597453 和 frontend 38320597455 失败，原日志/ZIP保留，后者尚未运行 Scala frontend。失败分别来自当前 observer 仍绑定旧 MatrixService SHA，以及历史 75 源 receipt 被拿来与新工作树比较，并非这两份日志证明数值错误。

修复保留原 receipt 字节 SHA 3d0f449d…e5570e 和原结论，历史源逐路径读取固定 37b7de74431ed79b7e9f3d52d308ed7f46727b7a；当前 observer 显式升为 v2，仅允许 Matrix Python/C++ 两个已审源身份更新，其他 73 源、import/loaded-code/数值/发布栅栏仍严格。新增缺件、额外替换、第三源漂移、旧 hash 来源与浅克隆 fetch 集合负测。48 项受影响小门通过且独立审查无阻断；当前版本的 legacy 默认路径仍实际运行独立整数算术和公开 QK→Softmax→PV 对照，没有将旧整链 PASS 重绑到新源码。

现有生产 GdnElementwiseOwner 的 SigmoidMul=2 已映射到同一个软件 Elementwise owner，显式开关默认 false、attentionWidth=2048。复用同一 Scalar，依次 ExpNegative4→Add0→Div2→MulIeeeRne6→BF16 sigmoid→MulIeeeRne6 context→BF16；没有把 sigmoid 错写为 SiLU。原 Add/SiLU、有限下溢策略及负 gate≤−80 Unsupported 范围保持。46 项合成门包含参数锁定、真实 M1×2048、同实例模式切换、末 ACK、observer 异常后的同 pending abort/drain/reset。

真实子算子以封存的 actual raw-gate 和 actual GQA context 回放到同一 TypedMemory 的真实 producer 写/ACK/terminal；cold16/carried16 共 65,536 个 gated-context 输出及 65,536 个 sigmoid BF16 观察全部与固定官方逐 bit 一致，四项原 max=0.03125/mean=0.005 门通过。最终封存运行 5.249 秒、132 个已加载项目源/固定源码身份；每窗 131,072B 读、65,536B 写 ACK，32,768 exp/add/div 与 65,536 mul6，6,145 软件 tick。仍是 replay 子门，prefix/GQA 未在这一进程重执行，也不是完整 L3、M128 或硬件周期。

GQA driver 的重复 coverage 扫描改为宿主不可变集合封存：只在 admission 和真实 write/ACK 后验证实际整数集合，每 tick 检查同一 frozenset 身份，原逐字节 source 检查与末 SHA 保留。accepted terminal 后才归还 output 普通集合，支持未写 early-abort 输出被其他真实 producer 重用；部分写入仍拒绝 fresh 重用。28 项小门及八组旧/新实际输出、全事件/observer trace、tick、ACK、发布结果完全一致。此项仅减少宿主验真开销，不减少任何逻辑请求、物理流量或硬件资源，不能算硬件 MAC 提升。注入 memory 方法异常仍 fail-closed，不伪造进度或保证原 invocation 可续跑。

冷源受影响软件门313.0秒完成：完整frontend control步骤821次、observer/public observer22次、GDN330次/23suite、L3 219次/19suite，合计1392次测试执行（不是去重用例数），无skip。全部测试源/日志/工件身份复核；Scala/CHIRRTL仍交后继CI，未宣称本地展开。初期冷clone缺历史对象的失败保留，在该clone精确fetch八个固定commit后恢复，没有读取历史work或重跑大模型。后继精确提交 CI 待验。完整 L3 活链的 KV/final fence、O/residual/postnorm/FFN、M128 GQA、生产 C2/pair Chisel 选择和五 block 总门继续 open。


### c554：补齐 observer 的传递身份闭包

c554e502 的 L3（219测试／19suite／95源）与 GDN（330／23／50）原 CI 成功；两份紧凑工件的 ZIP digest、精确提交逐源码、suite日志/计数及编译receipt已核对。原 Qwen2 contract 38323301022 失败：新基础 observer 已显式 v2，但 official observer 仍固定旧 helper SHA，随后 profiled adapter 也固定旧 official observer。71项套件在真正比较前出现11 failures/32 errors，原日志与FAIL保留；不能将这个身份拒绝写为模型数值失败。原 frontend 38323301183 已于23:55成功，821测试、13份frontend receipt和159份CHIRRTL逐hash复核；61,428,945B ZIP与23项精确源码工具绑定已核。c554五门为四成功、一项上述身份失败，原FAIL保留。

本轮统一枚举 helper→official→monitoring→profiled 的全部传递引用。执行库存仍恰好75路径：73身份不变，只承认前一批已审的两个Matrix替换。官方快照必须含helper、owner、service、observer四项；其余caller自带源也逐项核验，缺项/漂移/非法replacement及loaded bytecode变更均拒绝。官方最小闭包79项、monitoring80项、profiled83项，实际runner按其完整闭包采集。25份历史receipt/report字节未改，新v2报告显式不继承旧数值验收。

完整尾段的小测试又发现原 frontend 全文hash门未包含c554新增的37b7de精确fetch/probe。保留首次117/118失败，修复只允许这两条精确行各一次、顺序相邻且处于已审位置；剥离后仍必须等于原898e1ced…整body身份。35条原Python命令、20分钟预算和其余workflow内容继续受原hash保护；未改workflow正文或预算，负测覆盖缺失、重复、漂移、移位和原命令改变。

独立只读审查六文件无阻断。随后在全新源码目录和按原CI版本新建的Python3.12环境，原contract步骤全文按原顺序执行，含全部后段suite与artifact收集：566项测试、156.913秒、最大子进程RSS376,552KiB，44份metadata/log工件3,509,351B，所有源前后不变，无历史work依赖。包含必要的小型宿主测试库构建，没有M16/M128模型或RTL重放。证据摘要见[传递身份修复](../reports/execution/QWEN35_L3_PREFILL_MODEL_20261012/OBSERVER_TRANSITIVE_REPAIR.json)。此修复不改变算术、阈值或实际L3覆盖；完整L3、公共Command128/生产Chisel/RTL和五block总门继续open。

下一实际闭包固定为19阶段：原8阶段前缀→真实KV append→GQA→SigmoidMul→O→残差→postNorm→Gate→Up→SiLUMul→Down→最终残差。先把最终真实Add的tag、完整ACK和held终态验证移到接受之前，并把KV prepare/retire与该driver绑定；held success遇abort/reset不得发布。carried只能消费同一fence上一成功提交的实际root，RoPE绝对位置与cache内query start分开。双M16完成后按完整阶段实测预算双M128，不再单独长跑GQA子门。

计数更正：c554文字与紧凑摘要原写1395次，复核原日志应为653＋168＋17＋5＋330＋219＝1392次。原因是人工合计将isolated public的168误写171；CI和原冷日志实际一致，无测试或结论改变。旧摘要原件及SHA保留，更正明细记录在新传递身份摘要。
