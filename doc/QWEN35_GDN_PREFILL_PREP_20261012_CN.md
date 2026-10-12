# 0.8B L0：真实 Conv/AB 写回到 M128 输入准备

本轮在同一前缀模型中接通了实际 RMS→共享 Matrix QKV/Z/AB→Conv4/SiLU→InputPrep。完整 GDN、真正 chunk64×2、状态 fence、公共 Command128 和 Chisel/RTL 尚未完成。两个窗口各自 cold；第二窗口 token128..255 不是 carried GDN 验收。

## 数据与算术

InputPrep 只读取同一物理 TypedMemory 中已经写入、ACK 并接受成功完成的 Conv 和 AB 张量。A_log 保留原 FP32，dt_bias 为原 BF16[16] 加32B物理padding。AB单个64B记录为 A16/B16。目标从哨兵开始，FP32[M,6400] 按 Q2048、K2048、V2048、16个64B gate记录写回；gate为 g、BF16舍入后无损升FP32的beta、14个正零。

同一 Scalar 对象服务 RMS、Conv 和准备阶段。Q/K按原 M1 owner 的 ascending FP32平方/加法归约、eps1e-6、sqrt/reciprocal，再对Q做chunk缩放。g和beta复用原ExpNegative/Div与显式启用的Softplus7；不新增SFU，不调用数学exp充当实际实现。原异常、未支持域及每个舍入节点保持。每个owner仅复用128项FP32 head缓存、参数缓存与64B包；这次是独立token准备的软件M128扩展，原Chisel InputPrep仍只支持M1。

所有输出ACK完成并接受成功terminal后才发布准备张量。abort、reset、读错、tag错和末ACK错禁止发布，先排空已经接受的请求。尚未被消费者接受的成功结果遇abort会转错误；已有错误不被覆盖，已接受的成功不能被迟到abort撤销。Conv history仍为staging，两个状态域和generation都没有提交。

## 数值结果和范围

[结果与实际字节身份](../reports/execution/QWEN35_GDN_PREFILL_PREP_20261012/RESULT.json)绑定模型、checkpoint、32项源、原C++ Matrix ELF、输入和全部实际结果。先执行并封存两窗口actual，随后运行参考，没有向实际链注入reference中间结果。

M16用时78.93秒，M128用时279.80秒，各完成12个owner。M128最高RSS487,684KiB；新增两个准备张量合计6,553,600B、1,638,400个FP32字，全部对独立数组参考逐bit一致。每个M128准备阶段有51,200次完整64B写ACK，V为实际Conv的无损升宽，beta低16位为零，gate padding全正零。此前RMS/投影/Conv的原门继续通过。

InputPrep没有已分配的独立native门限，所以固定算术符合性和官方诊断分开记录，不将诊断自动标PASS。相同实际Conv/AB输入下，官方完整形状前缀的最大绝对差为：Q约4.47e-8、K约3.58e-7、g约1.91e-6；V、beta与padding逐bit一致。纯官方前缀输入也保留对照，传播后的K最大绝对差0.0018176548、Q0.0002462566、V0.00048828125，没有删除或放宽这些差异。完整GDN output/state原门留待真正chunk与末层完成后评估。

软件tick、Scalar请求和CPU时间不等于硬件cycle。固定4096 MAC/cycle分母不变；完整GDN硬件周期与有效MAC利用率为空，不沿用Qwen2旧映射统计。

## 可复现小门与后续

103项、10个独立进程小测试通过；新的冷源码checkout按workflow顺序执行构建、全部测试、工件收集也通过，约25.39秒。首次本地冷验证脚本漏读GitHub的GITHUB_ENV步骤间传递，造成库路径缺失；原失败已保存，修正本地验证脚本后完整重验，CI workflow与数值实现未为此改变。另保留最初合成夹具M1被Dense合法域拒绝的记录，正式小链使用M16，没有放宽准入。

源码与实际M16/M128产物分别经独立只读检查。本批 ada0a8a 两CI成功，已下载核对9257B工件、103测试、23测试源及3项编译源；CI只执行小合成门和小C++库构建，不下载权重、不重跑actual M128、不生成RTL。提交只有源码、脚本、hash和紧凑摘要。

下一步以真实准备结果做头0的完整128×128状态、true chunk64诊断，再按证据接全16头与两chunk；16-lane FP32映射首先是保精度验证路径，不默认满足80%吞吐。随后接gated norm、O/residual、postNorm、FFN与最终双状态fence。五block M128总门及S02/S04/Q35B/U00.2/U01继续开放。
