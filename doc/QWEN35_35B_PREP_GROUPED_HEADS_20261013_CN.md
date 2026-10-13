# 35B Prep：显式 key16 → value32 布局与真实事务小门

## 官方审计与本批边界

固定 Qwen3.5-35B-A3B revision 62704185bd97ad488cfc404e7caea797396b74dc，
Transformers 42ca97014c85d71a88ad60d55f08cb9fb4d26e2c。官方 forward 558–577
先将 ConvOut 拆 Q2048、K2048、V4096，重排为16/16/32头、每头128维；beta在BF16
执行sigmoid，g由FP32 A_log.exp及FP32(a)+BF16 dt_bias的softplus得到。随后Q/K按
repeat_interleave(2,dim=2)映射，value头h读取key头floor(h/2)，不是h%16。
chunk入口295–306才将各张量转连续FP32、Q/K L2norm、Q再乘128^-0.5。

现生产Chisel GdnInputPrepOwner只接受M1、最多16等头；原软件扩展支持M1..128，
但也写死16等头和旧行跨度。此次只扩展对应软件owner的显式布局与地址事务，不改
生产Chisel或chunk的头数上限，不声称完整35B Prep/GDN/RTL通过。

## 实现与物理资源约束

- 保留0.8B默认布局 Conv6144、AB[A16,B16]、FP32 Core6400。
- 新35B显式布局 Conv8192、AB[A32,B32]（128B/token）、A_log128B、dt_bias64B；
  FP32输出 Q4096/K4096/V4096/gates512，共12800元素、51200B/token。
- Q/K通过真实读取地址映射h//2，不物化整个重复张量；V读取h，每头不复制。
- 每token以16头为一组，读取A_log对应64B、完整dt_bias64B取相应半区、A/B各64B取
  相应半区。第二组重新填充同一组参数bank。保留64个参数元素容量（按FP32预算256B）、
  单128-FP32 head缓存、单64B事务包，没有新增全token、全head或递归状态片上数组。
- 完整组边界先消费前16头的V和gate ACK，才填充后16头参数。第二组读错排空已接受
  事务并锁定；末写ACK错误不发布。完整输出只有全部51200B/token ACK后才发布。
- 同一外部PrepScalar（Scalar1）；Matrix/Vector不参与本组件运算。整个prefix或后续
  chunk仍使用既有固定资源，不能把本组件未使用Matrix当成完整设计资源分母变小。

官方config/source完整SHA与repeat分支AST均在grouped_source_identity中检查；layout
只准入(16,16,128)及(16,32,128)，拒绝任意未验证几何和owner/job混用。0.8B减少头数
合成测试仍保留原完整stride并真实补零写ACK；35B入口必须完整32个value头。

## 验证层级

合成M1与M128通过实际 TypedMemory producer写/ACK/发布，再由Prep owner实际读取、
共享Scalar运算、逐64B写/ACK。独立参考用NumPy repeat_interleave构造两组16头，
调用既有独立固定算术配方后拼回完整输出；它不调用candidate地址helper，也不提供
owner的输入或输出。逐bit比较全部FP32向量、gate及padding，并单独检查h1/h2/h31、
Q/K成对重复、V不重复、两组参数地址及完整读写字节数。

新门包括第二参数组读错、最终ACK背压和错误、错误布局拒绝。硬件history/state
commit和generation均未改变。共享scalar在终态释放，无未排空的memory pending。
这属于合成软件功能/控制回归，没有使用真实35B A/B投影输出；不继承前一Conv权重
前缀的PASS，也不授予原本未分配容差的独立Prep native验收。后续必须逐Q/K/V/beta/g
报告与官方运算的精确差异；完整chunk/整block原门继续开放。

## 计数与性能

每token真实读取32×3×256+2×4×64=25088B，写ACK51200B；M128分别3211264B和6553600B。
Q/K重复头目前重复做归一化，避免未经验证改变算术/缓存生命周期；这是执行计数，
不能当成有用工作量提升。没有硬件cycle、busy/lane duty、stall或overlap测量，保持
unknown；未达到或证明80%/90%利用率。此批不新开微优化。

## todo / ongoing / done

- done：官方头映射/精度顺序及最小payload审计；显式地址执行；固定缓存组复用；
  合成M1/M128完整字节对照及故障事务测试。
- ongoing：完整0.8B/35B冷回归、独立审查、小批发布和精确CI工件核验。
- todo（紧接本批）：实际RMS→A/B投影接线与参数获取、35B Prep逐角色官方诊断；
  再完成32头chunk布局及完整状态生命周期，不长期停留在纯shape合同。

下项只需shard14新获取262336B：A/B各BF16[32,2048]共262144B，A_log FP32[32]128B、
dt_bias BF16[32]64B。原header SHA d6d6f3155bd210da84591c715306d39d0ba4c1a7878db8bdcc65dc52054e85d2。
绝对inclusive ranges：A 277976–409047；B 409048–540119；A_log189080–189207；
dt_bias277912–277975。Z为额外16MiB、非Prep依赖，本批未获取；专家权重亦未获取。

完整冷GDN481项/37套、124份源前后不变，覆盖旧0.8B及35B门；计划/清单91项通过。
逐case计数及源码身份见 [机器可读报告](../reports/execution/QWEN35_35B_PREP_GROUPED_LAYOUT_20261013.json)。
M128实际Scalar操作含mul_ieee_rne2629632、add1064960、sqrt8192、div14336、
exp_negative8192、softplus4096；QK平方实际1048576项，独特源元素平方524288项。
软件ticks305153仅是软件事务步，不是硬件周期。
