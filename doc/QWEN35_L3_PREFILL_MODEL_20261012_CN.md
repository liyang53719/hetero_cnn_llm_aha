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
- ongoing：本批远端CI工件闭环；C03.2/C04.2/C05中的L3模型子链继续，不能关闭父项。
- to do：同实例Q/K Norm256→partial64 RoPE→KV双span fence→矩形QK/Softmax/PV→sigmoid gate→O/residual/postnorm/FFN/residual。Norm256原PWL/NR算术及原native失败/门限必须保留，新增数值差异要明确阻断。
- to do：公共Command128和Chisel接入，包括新RMS归约、投影分块、共享Scalar IEEE选择；当前软件通过不冒充这些硬件接口已经执行。

2b21d738的参考源码CI38304400698与payload CI38304400709成功，11测试、3源码/contract身份及1116B紧凑工件逐hash核验。本批新增CI只构建小共享软件库，运行全部source/synthetic测试；不采集模型、不下载权重、不生成RTL。实际大张量仅在本地保留，Git只提交源码、固定版本/hash、紧凑验证摘要和必要历史纯源码。

Qwen2完整cold M128、0.8B L0完整cold→carried M128维持各自已完成软件模型范围；0.8B L3完整block、35B-A3B L0/L3、Chisel/RTL及五block联合验收均未完成，S01/Q35A/U00.2/U01继续open。
