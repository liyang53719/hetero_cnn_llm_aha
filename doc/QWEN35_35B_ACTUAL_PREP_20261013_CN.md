# 35B 同生产者完整 Prep 前缀接线（2026-10-13）

## 本批范围

同一个 TypedMemory、PrepScalar（继承 ConvScalar/SharedScalar）、Matrix4096/5contexts、
Vector16 依次执行真实 RMS→完整N8192 QKV→Conv4/SiLU、同 RMS→分别N32 A/B、
有读写/ACK/终态的 AB 重排，再将实际 ConvOut 与 AB Region 交给32头 Prep。
输入和权重按原 pin 获取；不把旧独立运行 raw 导入成为伪造的中间生产者。
Conv history 一直是未发布 staging，不代表完整 block state commit。

新增 AB 重排每 token 从 A/B 各读取64B，按 [A32,B32] 写128B，单 outstanding，
保留一个64B buffer；全部 ACK 完成后还须接收成功终态才发布。读错、ACK错、
末 ACK 背压、held-success 遇 abort 分别测试；已接受写义务实际 drain。
错 ACK tag/bytecount 测试直接检查 TypedMemory 协议断言；pack 未实现可注入 read-response tag/size 端口，不扩大覆盖声明。
超时保留 pending/部分输出，不伪造 ACK 或声称可恢复。

## 原始 g 域阻塞与显式 policy

低成本原输入预检先发现：真实 M16 的16个、M128的128个越界全部在 value head22。
原模型 Prep 在 g 算完后要求 -80<g<=0。官方 token0 g=-91.57681274414062，
FP32 c2b72754；现 Scalar 同节点 g=-91.57679748535156，c2b72752，差2ULP。
输入 a=-7.927417755126953e-6、A_log=4.21875、dt_bias=1.046875。
预检只是定位，不是新实际前缀 PASS。

保留默认 legacy_open80 不变；新增显式 35b_finite_nonpositive_fp32，仅对35B布局
开放，由 job/owner 同身份选择。它保留有限非正 FP32 g 原字节、不夹断、不降低精度。
实际 owner 测试覆盖 -79.5、-80、-80.5、-92；旧默认仍拒绝边界及更负值，
非有限输入仍拒绝。此为新软件候选输出域，不宣称旧 Chisel 源已支持。

下一 chunk 的 ExpNegative 目前 abs>=80 饱和为0，官方 exp(-91.58)仍可能产生
非零 FP32 subnormal；此差异继续开放，需要显式 IEEE 策略和独立数值测试。
本批没有以 Prep 允许输出 g 来宣称32头 chunk 或完整状态链已通过。

## 参考与门

上游 RMS/QKV/A/B 保持此前固定参考、算术顺序和原阈值，Conv/SiLU 同输入原1BF16ULP
门不变、history同输入bitexact。QKV旧参考快照唯一packer.py已随后改变，故本批用当前
固定脚本重新生成独立官方/C参考；M16/M128分别约1.2/8.53秒，原始数值结果不变。
没有重复下载、没有重复启动昂贵EDA。

独立 Prep 参考抽取固定官方 forward AST、l2norm 与 chunk 到 Qscale 的原节点：
QK16重复为32，V32不重复；beta先BF16 sigmoid再扩FP32；g为FP32；Q/K归一化和Qscale
为FP32。逐Q/K/V/beta/g和padding输出绝对、相对、ULP、bit差以及全部raw SHA。
不增加未经批准的 Prep 误差门，报告 passed=null、thresholds=null。

## 计数与未完成项

Matrix/Vector/Scalar 与原Prep128FP32 head缓存、64参数元素保持固定；AB打包新增64B
单包缓冲显式计入。32头重复Q/K归一化仍计executed工作，不能按16头独特源少算。
每case记录完整上游各阶段MAC/Scalar/DDR/ACK以及软件ticks；硬件全周期、busy duty、
active-lane duty和流水重叠尚未测，软件时间不当作RTL性能。

- done：源码接线、AB打包6项、前缀域/错误2项、新policy4项、原Prep/chain等30项回归；
  官方参考10项常规测试与独立 pinned_smoke 5项实际运行。
- ongoing：独立审查和小批CI；M16/M128真实接线与逐角色诊断已完成。
- todo：官方精度差异收敛、32头chunk布局/exp subnormal、状态fence、O/residual/MoE、
  完整L0/L3和RTL回放、固定资源全周期MAC利用率及占空比。

## 实际结果

M16/M128 各7个真实成功终态、71份执行源码及10个native工件前后不变；原上游strict门全部通过。
M16到Prep117.44秒、含诊断119.71秒；M128到Prep466.20秒，期间与冷回归共用CPU，
不作性能前后比较。V/beta两档逐bit一致；Q max_abs 2.235e-8/2.980e-8、maxULP6/7；
K max_abs1.788e-7/2.980e-7、maxULP6/8；g max_abs4.959e-5/5.341e-5、maxULP33/35。
这些保留为诊断，不称Prep数值验收通过。padding全正零，history仍未发布。

Matrix每档实际2164260864 FMA，M16 useful270532608，M128 useful2164260864；
算术padding比12.5%/100%不是完整周期利用率。Conv独立Scalar乘积524288/4194304。
AB重排实际读/写/ACK各2048/16384B，32/256个64B包。Prep写819200/6553600B。

首遍冷门因5个显式skip被现有零skip门拒绝，已将固定Torch smoke移到独立pinned_smoke入口，
默认CI不跳过、不放宽门。拆分初版遗漏json导入已由小测发现修复；未继承失败PASS。
首次旧chain回归漏Matrix环境配置失败，补齐已安装库环境后30项通过；完整失败记录保留。

[机器摘要与全部身份](../reports/execution/QWEN35_35B_ACTUAL_PREP_20261013.json)

最终零skip冷门513项/44套/141源，源前后不变；指定计划清单91项通过。独立小smoke5项另行实际执行，未计入513项。
