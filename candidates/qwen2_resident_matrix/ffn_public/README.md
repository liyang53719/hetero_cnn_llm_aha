# 公开 Command128 字节 → 完整 FFN 子图模型

此默认关闭候选将公开的 Dense20、Dense20、Activation35、Dense20 四条命令，接到既有 Host 控制、驻留协调器、同一 Matrix/共享 bank 模型和真实 act/prefix 写后读。它是独立 FFN4 子程序，从原 v0 完整软件图的 n1 开始；前置 Attention/Norm/residual 不在这四条命令内，不能声称完整 block。

## 输入 ABI 与来源

`fixture.py` 复用仓库 `Command128`、`DescriptorRecord`、tensor/shape/stride、MatrixAux 与 SfuProgram packer，生成4条命令和43条描述符。shape尾部填1；stride使用原公开 ABI 的元素单位。额外 metadata 位于独立只读区域，不复用 bias_index、workspace或私有opcode。fixture检查全部11个物理分配区间互斥，支持合法64-bit重定位，拒绝56-bit越界/溢出。

`model.py` 的 RecordReader 按真实64B地址读取公开128-bit字，检查表范围、tag、背压和错误锁定。typed reader按实际链逐次读取，检查dtype/rank/layout/stride、权限、完整padding跨度和policy。Host按需读取命令并保持原三命令预检、全program primary-root扫描、events/live/virtual状态；未知opcode仍先参与root扫描，在执行到达时由原正常入口拒绝。

launch仅快照config；表内容不被宣称全局immutable，也没有预解码命令表绕过真实读取。已捕获的三条组命令遵循现行生产源码锁存边界。workspace是第4个公开region，来自真实launch快照和epoch+1；身份标记不是跨reset checkpoint证明。

## 同一数值与控制链

`execute_numeric.py` 将实际 Host GroupRequest 对象交给原协调器，所有Gate/Up窗口、SiLU、act drain使用原helper。Down请求由公开第4条命令真实解码，经可选owner-edge回调推进同一个owner/bank；成功计数取自真实接受的终态和物理FMA观察，错误路径不伪造成功计数。

act只有真实写ACK后可由Down读取。三个原组completion在全部56窗口完成之后按顺序退休；Down末ACK和真实owner终态之后才允许第4个completion，最后返回整个FFN4程序result。backpressure期间event、live范围和结果保持。参考数组及phase10–13只在完整公开程序成功终态之后解码比较，不初始化中间结果。

普通Down的raw poison漏洞在实际 `ffn_group/group.patch` 的Host/Top默认关闭profile修复，runner原样传递consumer ready。成功线性化点是 `completion.fire`：未握手成功遇隔离不能发布；已接受成功不能被迟到poison追溯撤销。全局resetRequired没有epoch字段，后续launch隔离仍有效；普通明确error保持原status，已接受工作先排空。

## 证据层级

- 当前小门：公开字节31测试；实际小N160窗口、tiny Down与poison边界12测试；Host控制52、源码组合8测试。完整Host/kernel95个Scala源typecheck、6份有界CHIRRTL通过，default-off两IR与原版相同。
- 完整实值捕获以本目录独立source pins和receipt为准，不能继承812d858旧capture为新执行。
- Python控制模型与严格C++ FP32 FMA/原SiLU recipe是软件实现；不是直接执行Chisel，也没有生成RTL或运行硬件SFU。
- metadata按实际64B读次数计入流量；控制模型串行metadata调用不提供共享iDMA仲裁的硬件延迟。模型ticks/host运行秒数不用于硬件MAC利用率。
- 固定4096 MAC、32个1R1W bank、768 KiB SRAM和唯一16-lane SiLU不变。poison修复寄存器账不变；组合门控面积/时序未综合。
- 原完整M128 native/FP32-final FAIL、数值政策待定均保持。完整五block M128和冻结刺激硬件回放仍待完成。

CI只运行合成小门、来源校验及Chisel前端。权重、raw activations、NPZ、可执行文件、实际输出和生成IR不提交Git；需要的实际capture数据保留在任务工作目录，Git只保存脚本、来源pin及紧凑摘要。

## 两个新实际捕获终态

M16/M128分别304.597/437.927秒host wall，Gate/Up/act/Down全部逐bit等于独立固定算术与保存v0 producer。M128覆盖3,637,248个FP32元素、56窗口、112投影终态、56drain，act/Down分别4,587,520/786,432B全ACK后交付4个公开completion和1个最终result。两个case均实际读取87个64B metadata拍，共5,568B。

M128 payload流量98,041,856B，加入metadata为98,047,424B；仍是FFN子图的实际软件端口流量，不含整个block，不是测得DDR带宽。M128观察有用/物理主机FMA均5,284,823,040，M16有用660,602,880/物理5,284,823,040；硬件whole-wall利用率保持null。新公开Host逐边沿控制增加的是主机模型开销，不能用约305/438秒推断硬件时延。

来源与结果见 `numerical_receipt.json`。两次执行均绑定同48个严格源，原812d858旧capture没有重新绑定。源于prepare-only的venv分类失败及修复记录保留，未将其记为算术失败。

## 同一公开21命令程序的前缀接入

新增 `make_qwen2_21_fixture` 直接复用原 `pack_owner_block_fixture.py` 与 BF16 权重描述符转换器：21条 Command128、215条描述符、35个真实分配及同一 KV 分配中的两个 view。命令原始字节、地址、stride、生命周期保留；七个 Dense B 的存储 dtype 从 FP32 改为既有 BF16 合同，原 FP32 大小的保留区未被其它数据占用。原三类普通 region 与第4 workspace 分区仍隔离。

`legacy_prefix=True` 仅启用旧生产入口已有的 Norm、Bias、RoPE、KV 解码。`prefix_execution.py` 从 raw x 开始，按 pc0–9 连续执行 Norm、Q/Bias/RoPE、K/Bias/RoPE、V/Bias、KV。元数据实际读取端口和全部数值读写使用同一个物理地址索引；三次 Dense 使用同一个 Matrix owner、A/B bank、原 accepted-step C++ FMA。所有中间结果从真实模型写拍产生，只有全量 ACK、owner 终态和公开 completion 握手之后才可被下一命令读取。每次发布复核此前输出，pc9 后全量检查输出共存、canary 及未执行 suffix/virtual 区哨兵。

前缀 owner 的 NumPy FP32 原语保持原 v0 运算和舍入点。Norm 的 Scalar 路径保留原 underflow 错误策略；Vector 乘加保留原路径的有限数写回检查。这里模拟共享资源的串行所有权，不证明 row buffer 的实际 bank 分配、共享端口时延或 Chisel 执行。QKV 的 K1536 可放入现有 K2560 chunk，不读写外部 prefix workspace；完整 Down 还需将外部 workspace 实存接到此唯一地址模型，不能从本次前缀继承该结论。

`check_prefix_numeric.py` 冻结 raw 输入、公开 metadata 和执行源码，M16 为同一 frozen cold M128 的前16行。公开 RoPE 表容量1024、原数值参考容量128，活动 token 的双精度 libm→FP32 生成顺序相同，sin 半区地址按各自真实容量计算。十个写回区在 pc9 的真实 ACK/公开 completion 后，与提取的原 C++ Norm/Dense/RoPE 方法逐位比较，包含 bias 前的 qraw/kraw/vraw；旧保存参考只覆盖 n0、qr、kr、v、q、k 六项，另由保存 k/v 组成 KV 校验。独立 oracle 不计算 Attention/FFN。

该前缀 checkpoint 停在同一 launch 的 pc10，尚无整个21命令程序的 terminal。它不覆盖 Attention、O、residual、后置 Norm、FFN 或 carried cache，不是完整 block 验收。上文 FFN4 两个历史实值捕获对应不可变提交 `8212a32f43338163baee4126e522dcacede0fa23` 的源码，`numerical_receipt.json` 保持原哈希；新增普通 Dense/前缀实现不得继承其旧 PASS。新捕获必须用自己的源码与结果身份。

本轮 pc0–9 新捕获 M16/M128 分别22.985/48.492秒 host wall；十个输出区126,976/1,015,808个FP32值均对独立原方法逐bit一致。两组分别写入507,904/4,063,232B并全ACK，共10个公开completion，pc10仍待执行。M128读取14,425,088B含7,168B metadata，连同写回共18,488,320B实际软件端口流量。两个case原63源与冻结副本、执行前后SHA全部一致，独立复核直接重建raw输入并逐字节核对输出、参考、哨兵与ACK，未重跑算术。

结果见 `prefix_numerical_receipt.json`。M128观察有用/物理主机FMA均402,653,184；M16分别50,331,648/402,653,184。原生M128与FP32-final门仍 FAIL/待定，硬件whole-wall周期及利用率保持null。

## 原公开21命令的完整cold M16/M128软件链

`check_fullgraph_numeric.py` 将前述前缀接到 `ffn_attention` 的原QK/softmax/PV
方法，再执行O、两次residual、postNorm与完整FFN/Down。它复用原21命令/215
描述符和同一物理内存、Matrix accumulator、Dense owner/五bank；所有中间值
来自实际前驱写回或已经退休的驻留结果。`--prepare-only --rows 16/128
--compile-receipt ...` 先冻结75源/35 Python导入与原始输入身份，执行必须给出
`--snapshot`、其SHA以及M128所需同源M16先验。Gate/Up和Attention临时区保持
虚拟span语义，普通DDR写回与驻留tile completion分开计账。

本次数值结果见 `fullgraph_numerical_receipt.json`：M16原单次运行成功；M128
在1200秒预算内已接受全部21 completion、17 owner results及唯一整程序终态，
但最后新执行的独立参考仅剩29.024秒而超时，原运行仍记FAILED。
`verify_completed_fullgraph.py` 随后仅复用冻结前已存在、逐项证明同源码/ELF/
输入/shape的完整参考，19个实际输出共5,636,096个FP32值逐字节相同，没有
重跑实际链或参考。后处理PASS与原超时并列。17个输出可对照原终态摘要hash；
Gate/Up原驻留observer文件的bulk hash首次在后处理记录，未伪称提前封存。

M128实际软件端口读217,227,904 B、全ACK写15,728,640 B，共232,956,544 B；
Host有效MAC6,014,828,544，实际主机FMA6,801,063,936。Dense1,462,272步与
legacy Attention1,585,152步互斥使用同一资源。固定4096 MAC/拍分母，以每拍
最多接受一步得到极乐观48.187%上界；若再假设共享双向64 B/拍流量预算，则
流量上界40.343%。它们不是硬件利用率实测，也不证明iDMA实际带宽。当前旧
Attention映射没有兑现此前理想整图131.7 MB/71.35%的搬运上界。

仍未验carried/prefix矩形调度、实际Chisel/RTL/iDMA整链或官方native质量；
原native-v0/FP32-final FAIL与未批准的数值策略均保持。公共轻CI按test文件
独立解释器执行，完整发现且计数；不删除旧capture严格import闭包。
