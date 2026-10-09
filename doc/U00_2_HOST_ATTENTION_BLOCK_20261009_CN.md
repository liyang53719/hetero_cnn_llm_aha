# Qwen3.5 第3层完整 Attention block 的 M1 生产接线

本轮把默认关闭的生产 Host 从 Attention core 延伸到整个第3层 block 的计算图：原始 hidden 输入、input RMSNorm、Q/K/V、QK Norm、partial RoPE、真实 prefix KV、矩形 QK/softmax/PV、sigmoid gate、O、残差、post RMSNorm、FFN gate/up、SiLU乘法、down 和末残差。源接线与小门禁不能代替完整生产数值；当前整链数值为 **PENDING CI**，模型 cold128/carried128、恢复和原 native 精度门禁仍未完成。

## 命令、资源与状态边界

一次 launch 为22条 Command128、296条 descriptor record、19次实际 owner 请求。296条记录占4736字节；两次 launch 的元数据表使用独立16KiB槽，实际DDR布局逐span检查。所有 typed 中间张量的行数为1、tokenBase为0、tokenCount为1，按真实字节数分配及64字节对齐，不把M128容量或首tile称为M128执行。

既有 QKV v2、Norm/RoPE v1、core v2 的命令相对顺序和算术保持。新增公开 ATTENTION_POLICY v3 表示 RMS、Dense、elementwise 和最终 block fence，并显式绑定角色。input/post RMS和残差/SiLU复用既有 owner，新增 sigmoid 模式仍经相同共享 Scalar。全部 Dense、QK、PV复用同一个 MatrixPipelineService、八个 Matrix512 切片及单一 pinned iDMA。

sigmoid 命令的标准源根固定为 A=前面实际写回的 Q gate，B=前面实际写回的 PV context，D=乘积。先把 sigmoid 结果舍入到BF16，再乘BF16 context并在末端BF16 RNE。不能交换两个源根，也不能用SiLU代替sigmoid。集成审查曾发现候选前端把A/B倒置；旧控制PASS只说明当时的控制行为，错误源/日志保留，修正后的绑定需独立回归，不将旧PASS绑定新源码。

前端仅允许 QKV 消费本次 input RMSNorm 的实际ACK结果，第一残差继续读取原始hidden。缓存、最终输出以及11份权重加一份完整trig表的身份持续绑定。KV追加和PV结束只形成待提交状态；最终残差全部写ACK后，仍须末block fence被接受才公开cache length、generation和最终输出。下游末残差ACK错误允许已发送的W字节保留在staging，上一已提交prefix、最终输出和参数身份保持。无reset/restore完成声明。

## 输入与独立参考

固定模型 revision 为 `2fc06364715b967f1860aea9cf38778875588b17`，Transformers 为 `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。生产CI计划每次fresh生成baseline和AVX2各一次，实际M1两launch选择同一baseline官方cold_m128中的原始hidden token0与1；上游来源是embedding到GDN0/1/2的真实官方prefix。第二次launch的carried指DUT真实KV续写，不称上游GDN decode。

只预装两条raw hidden、11个原始参数、完整256×64 BF16 trig表和四张命令/描述符表，共18次preload。所有中间输出、cache和guard均由哨兵初始化，实际前驱数据必须经同一DUT和物理DDR写回再读取。每次成功launch应ACK68608字节，Dense共18350080 MAC；QK/PV工作量另计。驱动按真实物理地址索引并在completion后复核整个DDR。

完整参考从raw hidden重新计算input RMS，不能把native producer07作为QKV输入。独立固定算术覆盖57个producer、所有K1024/2048/3584 Dense的连续FP32 FMA及末BF16、原C1 Norm和B1 RoPE、sigmoid与SiLU各自的BF16边界。expected cache仅从上一次参考图的append结果续算；与DUT输入分开保存。live capture、原projection/Norm reference与完整图authority必须在同一进程中存活；离线摘要不能授权数值PASS。

原operator的max_abs=0.03125、mean_abs=0.005以及block的max_abs=0.05、mean_abs=0.01继续保留；完整native FAIL和prefix报告不被固定算术吻合覆盖。新GQA stage的官方验收门限仍未授予，其比较明确是diagnostic。有限负gate不大于−80属于共享指数recipe未支持的输入域，必须拒绝，不能把饱和或截断当作官方语义。

## 验证与执行方式

发布前保留独立整数参考小测、真实共享Scalar的sigmoid owner逐bit门禁、公开descriptor解析/alias检查、前端小控制RTL和源码独立审查。前端控制门禁的owner completion来自测试替身，不能算完整block数值通过。通用旧CI会自动发现新增Spec：控制helper放在稀疏检出已包含的项目tests目录；sigmoid测试无外部环境时从同一整数参考在内存生成并核对70个合成向量哈希。测试入口迁移另行typecheck和CLI复核，旧控制RTL与真实Scalar证据保留原Spec哈希，不声称新Spec已重跑RTL。正式生产门禁在GitHub执行两种同DUT两launch用例：成功，以及第二launch末残差最终ACK故障。输入和所有中间值只来自真实内存流，失败不能提前发布最终fence。

整体runner预算18000秒，保留180秒写失败摘要；构建上限7200秒、每个两launch用例上限3600秒，均受剩余总预算限制。复用已验证的进程组清理，严格FP编译选项保持，driver显式O2；没有实测数据前不作提速声明。只上传紧凑summary及source/input/output hashes，Git与CI摘要中不存权重、NPZ、模型tensor或生成binary。

C03.2/C04.2/C05、S01/Q35A只增加本局部接线证据，不关闭关联大项。U00.2保持ongoing，U01保持to do，C02.2保持OPEN。下一验收是当前精确提交的M1完整物理链终态及诊断，然后扩展真正cold128/carried128、完整失败恢复和后继层；不重开MAC优化。
