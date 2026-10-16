# Dense A 跨 N context 复用及 W 供数审计

可以先做一个默认关闭、保持算术次序的 A-cache 切片：现有 context-inner 循环
在同一 K 上复用一次 128×BF16 gather。真实 Qwen2 M128 七个投影的 A gather
由 1,462,272 降至 298,496，平均 2856/583≈4.8988 倍。Gate/Up 恰好5倍，
其他投影有3-context尾组，K/V的整体因子只有4。本文是源级方案和必要计数，
没有实现新RTL、测量时序，或证明完整block达到80/90%。冻结运行文件未修改。

## 已有容量和正确的循环

以下路径前缀为 `candidates/qwen2_resident_matrix/`：

- `transposed_owner/TransposedDenseOwner.scala:103–129,290–311`：四项
  operand FIFO；每个K遍历context0…C−1，之后才K++；C=min(5,剩余N32组)。
  N组只在所有结果、write ACK、DMA和operand债务排空后推进。
- `transposed_down/owner_down.patch:295–321,504–545`：实际Down/window路径
  同样是context-inner；K坐标在chunk内，顺序为chunk→N组→K→context。
  `transposed_down/model.py:514–526,728–759`给出相同索引及chunk/prefix fence。
- `transposed_owner/TransposedDenseBanks.scala:37–38,58–78,81–111`：A gather
  每次实际读8个bank；16-bank FFN列事务会与其冲突。B恰有16×160×32B=80KiB，
  两个40KiB half各放128 K×5 context×32 BF16。linear=half×1280+depth×10+2c+nh，
  bank=linear%16、word=linear//16。两half的2560个bank/word位置无重叠且填满容量。
  不增加context数、不借另一个half做第六个context，也不改W布局。

| 投影 | K | N | 原A gather/Matrix step | 复用A gather |
|---|---:|---:|---:|---:|
| Q |1536|1536|73728|15360|
| K、V 各 |1536|256|12288|3072|
| O |1536|1536|73728|15360|
| Gate、Up 各 |1536|8960|430080|86016|
| Down |8960|1536|430080|89600|

Down分chunk不会降低这个复用因子；每chunk各N组仍需读一次自己的local K。
这些数不含A ingress的RMW、clear、Norm、KV或其它client。

## 最小寄存器方案与执行顺序

`chisel/continuous_prefill/src/main/scala/heteronpu/continuous/BurstProtocol.scala:24–27`
声明每个step有544B名义payload；transposed owner把其中112个B lane恒置零，
实际非恒定payload为128 BF16 A+32 BF16 W=320B。不能把恒零lane当保留寄存器。

可选资源账本：

1. 保持Queue4，显式新增256B A hold及metadata。它是新增storage配置。
2. 首选：Queue4→Queue3，另设256B hold；活跃payload预算由1280B降为1216B，
   名义bundle预算也下降。新增valid/K/generation及mux须单列。源码容量守恒
   不等于综合后的面积/寄存器类型等价，仍须检查实际FIFO实现和保留网表。

每个FIFO entry继续带私有A副本；不要让已排队step指向会被覆盖的唯一cache。
因此hold只需活到本K最后一个B响应被安全enq，不必等全部Matrix step消费。
不能借用`aHigh`作为256B hold：它只有256 **bits**。
也不借`finalValue`或两个Matrix result slot，它们承担terminal返回及writeback。

建议实现顺序：

1. context0发一个A+B同步读；下一返回边沿捕获A到hold，并以当前A响应组装step0。
2. context1…C−1只读B；返回时使用匹配K/generation的hold，保持原W位置和step flags。
   原始每个输出仍严格K递增，BF16 ingress及FP32 FMA/舍入点不变。
3. B请求每次预留Queue3中的响应credit。最后B请求不是hold释放点；最后B响应
   成功enq后才可让下一K的A响应覆盖hold。旧FIFO entry在反压时稳定。
4. 下一K的A+B读可接在上一K最后B请求后的边沿；同步返回时使用old/new有效标签，
   不通过未初始化hold旁路。第一版允许必要bubble，不把本计数当无气泡证明。
5. 用独立`aGather`和`bRead`使能、pending/response标签拆开现有联合read接口；
   仅禁用A读而继续使用原response.activation会读到无效或上一个同步值，不能这样改。

五context理想片段是A+B0、B1、B2、B3、B4：仅第一个请求占A read口。
其余四个边沿允许一个明确仲裁的FFN A-bank请求；B banks独立，仍可供每拍32BF16。
现有`ffn_tiles/tile_ports.patch:295–300,368–384`把整个read/busy互斥，
`ffn_window/window.patch:180–191,209`屏蔽外部tile且writeback时停Dense读。
所以A-cache单独上线首先只减少读次数/切换；释放给SFU必须另做控制修改。

后续arbiter要按物理read/write边沿判冲突：A gather占8个bank读；tile列读/RMW
占16个读，RMW拥有下一边沿16个write。lower A和upper tile word不重叠时，
不同地址的一读一写可共边沿，但不得忽略原同步返回或重复RMW同word依赖。
现有tile写最少accept→commit两边沿，读最少accept→capture→ACK三边沿，
一个held response继续占它已有responseValue；不能把每个FFN事件自动当单周期。
需要新的A响应路由和仲裁metadata，无需添加A SRAM端口。

## Result、窗口及失败边界

`MatrixPipeline.scala:7–22,68–84,129–135`只有两个16KiB joined结果slot。
`TransposedDenseOwner.scala:137–147`/Down patch329–339用唯一16KiB finalValue
边运行边排结果；五个terminal context不能等done才处理。
FIFO缩深不能改变result.ready/write-ACK fences，不能为了保A缓存暂停全部结果直到done。

cache identity至少含当前A lease/generation、chunkBase/localK和当前组有效性。
window `reuseA`只说明SRAM里的输入仍有效，不许可沿用上次结束时的最后K缓存。
在setup、N组/窗口切换、chunk切换、A clear/load、新job、invalidateLease和poison
清cache valid；next group重新gather。`ffn_window/window.patch:308–346`
对A lease核对base/format/rows/K/stride/identity，cache必须服从同一域。
abort禁止新请求；已接受同步响应、FIFO、Matrix、DMA和tile RMW继续按原债务排空。
晚到响应不可重新置valid；仅协调reset可重用被poison的状态。只给metadata加tag不能
解决独立reset的旧响应问题。

## 实际 W 配置、burst及硬约束

选中transposed Down的Host约束明确是weightReadBeats==16：
`transposed_host/host_workspace.patch:120–123`、`official_bf16/chisel_policy.patch:93`。
因此基线是1KiB adapter mailbox和1KiB descriptor边界。虽然通用源码支持maxBeats64，
不能把4KiB mailbox/边界当当前配置；64版本增加3072B mailbox并有不同segment控制。

`transposed_down/owner_down.patch:245–257,446–496`仍逐64B发descriptor，
burstOutstanding阻止下一请求，response.ready只有接受后才有效。即使理想后端，
1,462,272 BF16 W beat也需至少2,924,544个request/response服务边沿。
W总量93,585,408B不因A-cache减少。下列源文件位于主工程：

- `chisel/continuous_prefill/src/main/scala/heteronpu/continuous/IdmaWeightBurst.scala:31–40,88,136–157`：
  maxBeats参数、mailbox、idle-only请求以及commit-LAST。
- 同文件330–378：64B对齐、maxBeats×64B边界及尾响应后才回idle。
  103的四项segments queue只跟踪一个descriptor内部AXI sub-burst。
- `rtl/integration/idma_backend_rw_axi_flat_wrap.sv:32–53,66–74`：flat ABI无交易tag，
  active_q把上游锁为单个transfer；NumAxInFlight4只属后端AXI，不是四个owner请求。

最小W后续切片可将同K的C≤5个相邻N32 BF16 beat合为1至2个descriptor，
遇1KiB边界分开，仍写当前既有half；K下一行有stride，不能把间隔当连续有效W。
每个descriptor的已接受长度、tag、row、起context和返回index须显式保持；只有全部
预期beat及干净LAST完成后才增加half的committed row数。error/LAST错位排到已接受
长度，poison半区，禁止Matrix消费其provisional内容。

全block合法coalesced descriptor数依各W基址的64B对齐偏移为365,568…379,136；
全部基址1KiB对齐时365,568。即使每descriptor只收费一个launch空边沿，服务也需
1,827,840边沿（尾端的边沿编号可差1），已逼近80%总预算。五beat burst本身不够90%。
64配置的descriptor范围315,264…318,656，也不消除串行launch/commit间隙。
实际adapter与后端有更多状态，以上不是可达到的延迟预测。

若要两row descriptor同时在途，需**同时**改变adapter和flat wrapper默认关闭模式，
核验上游响应有序契约，并单列两个metadata/commit credit。可评审的payload方案
是把已有1KiB mailbox分为两个512B row slot，每slot容纳≤5beat；当前统一dst=0、
local AW校验和全局streamIndex均须修改。不能只加owner queue就称后端已并发。
若无法证明untagged完成严格有序，应保持一项或显式扩展tag ABI，不能猜测配对。
同边沿LAST+新请求必须先按旧head核对并commit/poison，再按独立credit记录新请求；
count'=count+accept-retire，错误不得抹掉同边沿已接受的新债务。

下一W模型应覆盖：held请求与LAST、跨1KiB的4+1/1+4、同边沿retire/accept、
tail error与新credit、缺失/多余LAST、第二descriptor反压、half复用/窗口invalidate、
abort双债务排空；这批测试属于未来实现，当前仅测试边界和计数。

512bit数据口每拍最多64B。1GHz时单方向理论64GB/s；100GB/s不是这条通路已实现的
带宽。完整block达到90%所需仅W平均约57.36B/cycle，仍未包含A、output、prefix等流量。

## 两个具体 W 后续选择

**A. 先保持现有物理格式，做row burst。** 上面的1KiB边界及descriptor账本适用。
它适合小步验证，但短burst的首拍/commit延迟需要真实多descriptor credit才能隐藏；
仅同边沿退旧入新不能消除LPDDR首拍等待。现有NumAxInFlight4与flat single-active是
两层不同限制：解除后一层仍须验证前一层和真实memory latency的约束。

**B. 离线转换为N组优先的K128×N≤160连续权重tile。** 可复用已有转换/验证基础设施，
不是算术重写，但当前尚未有该生产格式：

- `src/heteronpu/weight_packing.py:1–6,129–139`明确声明IO tiles不改变物理row-major；
  `160–199`已有完整源hash、manifest、独立逐word readback，可扩展为独立新format。
- `chisel/continuous_prefill/scripts/pack_owner_bf16_weights.py:31–40,64–91`
  只变dtype/descriptor dtype，保持原tensor次序，没有K128×N160地址packer。
- `ffn_window/check_numeric.py:136–168`当前DDR map把官方[N,K]按请求地址解成[K,N]；
  该边界可新增明确的packed-layout版本，仍只依据地址、源文件和格式，不看expected结果。

当前七投影K均为128倍数。取ng=floor(n/160)×160，C=min(160,N−ng)，
packed_word_offset=ng×K+k×C+(n−ng)。组内K128窗口因此连续；每个beat按
depth→context→32列顺序解包到原B-bank位置。既有40KiB half放full5-context窗口；
3-context尾窗口是24KiB。K128尾、N32尾及其它模型形状必须单独定义/拒绝，
本审计不泛化未验证tail。假设payload起点1KiB对齐，所有窗口长度/起点均为1KiB倍数，
可使用真实maxBeats16的完整16beat descriptor，**91,392**个，总W字节仍93,585,408。
无需扩大B SRAM或1KiB adapter mailbox；只改变runtime私有文件的物理排列和地址生成。

实现需新增format版本、source/payload/packer哈希、逻辑形状与tile索引契约，并用独立
逆索引逐word核验原BF16位值。BF16源仅排列，不再舍入；FP32源沿用原RNE且只转换一次。
Host/owner必须显式选择格式，默认保持旧格式，不能用已有weightBf16位暗含layout。
不把raw/packed权重写入git；运行时转换与收据可复现。原每输出K递增的FMA次序不变。
最小修改面是packer新format/readback、owner W地址/descriptor计数、地址解码memory
fixture与格式准入；A-cache可先独立落地。

长burst也不等于无延迟：令一个descriptor从接受到释放credit的实测驻留时间为T，
L为有效beat数，D为合法在途数，则平均beat/cycle≤min(1,D×L/T)。5beat、D=2只有在
T≤10时才可能满64B/cycle；16beat、D=2的必要条件为T≤32。不能凭NumAxInFlight4
或理想0/1拍后端宣称现实满足；refresh、行命中、仲裁、返回反压及LAST commit都计入T。
若每个packed descriptor另有g个不可隐藏边沿，单W账本至少1,462,272+91,392g；
90%整块预算只容纳g≈1.85，且还没计其它流量/不可重叠工作。需要实测而非填常数。

既有`reports/execution/Q1024_DDR_BANDWIDTH_ENVELOPE_RESULT.json`明确是bandwidth
envelope/testbench而非DDR固定延迟标定，并写明800MHz AXI512只达理论51.2GB/s、
100GB/s只是上限。下一模型应接收显式latency/credit/带宽参数并标注来源，直到真实
目标LPDDR trace/参数被核对前，不把它包装成硬件预测。

## 80/90% 必要预算和下一步

固定4096MAC，useful=6,014,828,544；80%预算1,835,580、90%预算1,631,626又2/3。
复用后Dense A gather298,496+FFN六类列读430,080=728,576个A read admission，
取代原1,892,352。panel的27,648事务、82,944服务边沿包含读写，不能再称82,944读。
保守单列这些已知bank工作为811,520服务边沿，尚未加ingress/其它client；它和
Matrix/DMA/SFU可部分重叠，不能把所有下界机械相加或假定全部免费重叠。

Matrix1,534,080+panel82,944=1,617,024，80%仅余218,556，90%仅余14,602又2/3
给没有隐藏的其它工作。原16 divider仍至少1,792,000 cycles，90%已被独立排除。
合法FFN重叠还受三tile槽、完整seal规则和Down大A覆盖upper tile区约束；A-cache
并未证明双窗口容量或Gate/Up、SiLU、Down可同时驻留。要继续做生存区间和实测调度。

建议先实现默认关闭的A-cache+Queue3，仅验证读数、原步序/输出及所有stall/abort，
再做真实maxBeats16的W row coalescing。带宽、微序列、FFN仲裁随后合并测量；
这些切片都有独立价值，但当前无80/90%验收。

复现：完整仓库直接pytest本目录。拆分审计工作区须显式设置
`HETERO_AUDIT_BASE_SOURCE`为包含所列主工程文件的已核对checkout；只有本地缺失
的文件才取该root，仍逐一SHA256核对。15项普通及-O测试验证计数/容量/源约束，
`M128_COUNTS.json`须与report完全相等，不执行算术或RTL。
