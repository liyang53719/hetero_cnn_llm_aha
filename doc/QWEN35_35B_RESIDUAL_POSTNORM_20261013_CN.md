# Qwen3.5-35B L0：实际O后残差与postnorm

基线3bf80c19已闭环：原GDN38457859238、goal38457859263、payload38457859258全success；643项/67套/195源零skip及原ZIP逐SHA复核。上一批两档O同输入官方bitexact，不继承为本批postnorm验收。

## 本批最小范围

- 原层输入与同次实际O做BF16 Add，再按原943/947 AST的BF16边界进入H2048 post_attention_layernorm。不能用input RMS输出替代原层输入，不能融合省掉BF16残差写回。
- 显式35B H2048 Add-only profile；旧0.8B默认几何和数值策略保持。三块32元素beat缓冲复用，原Chisel参数能表达H2048不等于已绑定/已跑RTL。
- 同一RMS owner、同一Scalar及原三块2048B bank再次用于postnorm；Matrix/Vector不新建、不计新增MAC，owner两次事务分开统计。
- 新StrictPostNormDriver继承实际旧RMS transport/算术；原请求/Region/资源/三bank持续绑定；真实write事件SHA、完整ACK及原held terminal检查后才发布。篡改pending保留义务fail-closed，不宣称新增坏tag wire注入或自动恢复。
- 残差前复核真实O终态、输入hash、资源epoch/bank/profile；postnorm必须消费真实残差Region，所有成功/失败仍保持chunk state/history/scratch private，generation不变。

## 参数与参考

- 只下载L0 post_attention_layernorm.weight BF16[2048]共4096B。模型62704185bd97ad488cfc404e7caea797396b74dc，shard14 header189080B，header SHA d6d6f3155bd210da84591c715306d39d0ba4c1a7878db8bdcc65dc52054e85d2，inclusive range7884248–7888343。
- manifest SHA9fe42b27599c7e83524b899638f595b8bac9e5c6c4eaf2750a18c9a521712ba0；只有metadata、脚本及摘要入Git，不提交4KiB权重或raw。
- 固定官方源码943 BF16 Add、947调用原RMS878–895，实际11次dispatch捕获。旧O两档与4个synthetic官方smoke已完成，只是参考验证，不是本批producer执行。
- postnorm FP32平方/mean/eps/rsqrt/(1+weight)/两乘法/最终BF16逐节点记录；候选sqrt→div与官方rsqrt的差异保留。auxiliary sum不能冒充官方mean；不新设standalone容差。
- 候选真实RMS的不可变观察快照用于诊断，host存储不是新增硬件缓存；不把参考数据回灌producer。

## 资源与计数预测

每token残差读8192B、写4096B、2048次Scalar Add；postnorm读12288B、写4096B，新增两块外部DDR H staging及4KiB readonly权重。两阶段合计读20480M、写8192M。预测需由实际transport/ACK计数核对。完整硬件周期、MAC利用率、busy/active-lane占空比仍未知。

## todo / ongoing / done

- done：4KiB payload元数据和HTTP/hash验证；H2048 Add及原默认门；严格RMS围栏13项；官方参考11项冷门和6个固定runtime smoke。
- done：最新局部preflight57项通过，含旧elementwise22项；不累计重复集合。
- done：同次真实M16和fresh M128 attempt3源冻结执行，残差及postnorm BF16与七类可比FP32节点均bitexact。
- ongoing：小批发布与原CI闭环。
- todo：router按官方full256 softmax/top8/BF16归一及ascending-expert累加另批；MoE和最终残差完整block、warm联合提交、生产Chisel/RTL仍open。

## M16同次实际链结果

- 100执行源/13native前后不变，13终态成功，原O批14份输出含state/scratch逐SHA一致。残差32768 BF16词和postnorm32768 BF16词均与原943/947执行逐bit一致；postnorm另与独立FP32配方逐bit一致。
- 实际RMS观察节点squares、mean、mean_eps、inverse、scaled、gamma、weighted均与官方FP32节点逐bit一致。root只属于候选sqrt节点；sum与官方辅助sum分别保存，不混称原forward节点。
- 残差实际读131072B、写/ACK65536B、6145软件transport ticks、32768 Scalar Add。
- postnorm实际读196608B、写/ACK65536B、8193软件transport ticks；Scalar add68240、mul_ieee_rne98320、sqrt16、div16。与逐token资源/流量预测吻合。
- 原RMS三bank identity复用、Scalar同实例；Matrix/Vector计数没有增加。全链Matrix仍执行4311744512，有效538968064，12.5%仅工作量比，不是硬件利用率。
- state/history/scratch未发布、generation不变。M128沿同冻结源码从头重跑完成；本批仍不构成完整block或RTL验收。
- 运行前全冷门678项/72套/205源零skip且前后不变；独审已逐source/log核对。实际两档原raw、七类FP32节点、各82路径记录及计数已独审无阻断，本批发布和CI尚未进行。

## M128中断与新attempt

- 首个M128在20:45:09 UTC最后保存gatednorm阶段（1280.9秒）；随后工具session不可用，summary停在RUNNING。没有O/残差/postnorm终态、输出或pending恢复快照，退出码和终止原因无法确认；不得写成timeout或PASS。
- 21:02复核100源、13native及13份已持久raw哈希，均完整且旧阶段字节保持。原summary/raw保留，另附中断审计，不能从已保存gatednorm重新灌数据冒充同次继续。
- 一次独立后台launcher未留下运行summary，两日志0B，保留启动痕迹。当前工具的进程视图不能跨session确认活进程，因此改用受管理session及阶段/退出码证据跟进。
- 21:04:08 UTC fresh attempt3从头执行M128全链，数值源码不改，原1800秒内部wall watchdog不变；外层1830秒只作终止清理和退出码落盘。没有放宽数值门或原位恢复声明。

## M128 fresh attempt3完成

- 21:29:02 UTC记录exit0；实际1489.756秒，内部1800秒预算未改变。100执行源、13native前后不变，13终态成功，原O批14份输出SHA全部保持。旧中断和启动失败记录另存，未覆盖或假恢复。
- 新残差262144 BF16词SHA70704553d4b42c32a6fa2ad4f0deaf4a0cf44594f832d5cfdb8a654400ca4280；postnorm262144词SHAb524371f72e29cd0f98411effd0d1fbe73d29b9bcc0af4010170478b1bb1f174，两者均官方逐bit相同。七类实际FP32观察节点也逐bit相同。
- 残差读1048576B、写/ACK524288B、49153软件ticks、262144 Scalar Add。postnorm读1572864B、写/ACK524288B、65537软件ticks；Scalar add545920、mul_ieee_rne786560、sqrt128、div128，均与闭式预测一致。
- Matrix总执行和有效均4311744512，Vector计数保持旧O批；100%仍只是工作量比。postnorm数学平方归约有效2048×128个独立Mul/Add对，不能算新增Matrix FMA或硬件利用率。残差MAC为0。
- 同RMS三bank及Scalar复用；state/history/scratch保持private/gen0。完整block仍缺router/MoE/最终残差与联合状态提交，生产Chisel/RTL/完整周期及duty继续open。
