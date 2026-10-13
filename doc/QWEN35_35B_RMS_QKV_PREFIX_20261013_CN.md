# 35B L0：真实 H2048 RMS 写回 → 全形状 QKV 软件前缀

基线 [a5f49a1](https://github.com/liyang53719/hetero_cnn_llm_aha/commit/a5f49a1d04eefbe4b9387fdc0417d4b50e23633f) 的四项轻 CI 与三份紧凑工件已核闭环。新增代码复用其 H2048 RMS、K2048 双 partial、原 Matrix/Vector/TypedMemory；没有复制算术阵列，也没有把旧 RMS PASS 自动继承给新接线。

## 已执行范围

原始 BF16 embedding 行从 0 开始，经实际 RMS 读/算/写 ACK 与终态发布后，投影 A 直接指向这份实际发布的物理 Region。QKV 权重采用原 BF16 NK[8192,2048]，仅逐位转置为原驱动的 KN 布局。所有中间/最终输出先填哨兵；计算前只初始化原输入和权重。相同 owner、bank、Matrix、Vector 在所有窗口间保持身份，完成后检查以前发布的输出仍共存。

先执行 M16 的 Q/K/V 各 N160 小窗口，随后执行完整 M16/N8192：52 个窗口，51×160 加末窗 32；每窗两段 K1024，合计 104 个真实 partial 终态。所有结果经过原 Matrix 返回队列、共享 Vector16 Add、破坏性原位 lease/RMW、BF16 RNE 和真实输出 ACK。完整输出 262144 B 全部 ACK 并接受 terminal 后才发布。新软件前缀的公开 Command128/生产 Chisel 接线尚未完成。

小窗口6.99秒、完整M16 87.19秒、完整M128 145.36秒均是宿主验证耗时，不能用作硬件周期。完整M128也已按同源实际完成52窗/104partial，2,097,152 B投影全部写ACK，末32列和128行均实际执行。两形状是分别从原始embedding启动的RMS+QKV前缀，尚未执行本模型Conv/chunk/state、gated norm、O/residual或MoE，不能称完整35B block或carried状态。

## 官方来源与数值合同

模型固定 62704185bd97ad488cfc404e7caea797396b74dc；原 Transformers 源 42ca97014c85d71a88ad60d55f08cb9fb4d26e2c。仅获取 embedding 原行0..255、L0 input norm 和完整 QKV 三个 payload，共34607104 B；完整 QKV 33554432 B，SHA b6195bf0347afcbee3eab1e1f7c34b372cc917b19ddf4feaed8f70d699544db6。完整 checkpoint/LFS 哈希未验证，首次 tensor 哈希是本次观测。数据只在 ignored work，Git 只含源码、固定版本、哈希与紧凑结果。

独立参考执行原类中完整 BF16 nn.Linear(2048,8192) 调用及后续 transpose，保留 [1,M,2048] 输入和完整 N8192 后端形状；小窗口对照只在原全形状输出中切片，从不调用小 N160 官方算子冒充原后端。输入为已验证的真实 RMS 输出；Torch2.10.0+cpu、NumPy2.3.5、DEFAULT、单线程/单CPU、无 autocast。实际 oneDNN3.7.1 日志与 JIT 反汇编见 BF16 点积与归并指令，并非仅按 primitive 名字推断 ISA。

独立 C 按每个 K1024 内 pair-high-first 顺序 FP32 fmaf 累加，两个 FP32 partial 再做一次 FP32 Add，末尾 BF16 RNE；顺序 K2048 对照也保留。两种配方与原官方全形状 M16/M128 都执行了原 max_abs≤0.03125、mean_abs≤0.005 门，Q/K/V 各自及整体均须通过，不能用 V 的大量零误差稀释 Q/K 均值。

实际完整 M16 前缀输出对独立 C 配方逐 bit 一致；官方 Q/K 分别有518/501个位差、最大1.410593220986745e-37，V全bit一致。保留合法渐进下溢，未为了模拟 CPU 指令内部 denormal 行为而无证 FTZ。实际完整M128 owner输出同样与独立全形状配方逐bit一致，官方Q/K分别3923/3981个tiny位差、最大1.88079096131566e-37，V仍bitexact，各段均过原门。参考算术和实际owner执行分别保留身份，没有注入预计算RMS/投影结果。

## 固定资源与逐 case 性能记录

固定 Matrix4096 MAC、5 context、Vector16、Scalar1。A SRAM仍16×1376×256bit=704512B，A占1024words，lhs/rhs各160words，剩32words；没有第三sum槽。H2048 RMS仍三块1024 BF16存储，总6144B，output前128B临时保存32FP32 residue。控制、复用网络与物理时序仍待实现/综合。

| 已过case | 有用 Matrix MAC | 实际执行 FMA | 共享 Vector Add 请求 | Scalar 请求 | 输出 ACK B |
|---|---:|---:|---:|---:|---:|
| M16 RMS+Q/K/V各N160 | 15728640 | 125829120 | 480 | 166592 | 80896 |
| M16 RMS+全N8192 | 268435456 | 2147483648 | 8192 | 166592 | 327680 |
| M128 RMS+全N8192 | 2147483648 | 2147483648 | 65536 | 1332736 | 2621440 |

MAC 数来自实际退休 partial 与 C++ FMA 计数，两者区别明确；末32列有效/填充计数已包括。M16两case的useful/executed=12.5%，M128为100%；这些只是Matrix执行算术中的有效比例，不是全前缀/完整block利用率。M16与M128的实际执行FMA都为2,147,483,648，后者同时增加归并及写回行数，因此本次耗时不是简单128/16倍。全前缀实际物理读分别33,816,576/35,651,584 B，总写ACK分别327,680/2,621,440 B；共享DDR带宽竞争仍要进入完整周期模型。全硬件周期、busy/active-lane占空比、供数/依赖/写回/调度stall及跨窗重叠仍 unknown；后续须把同一完整调用 accept→terminal 的周期和所有共享资源时间线绑定后填写，固定分母4096不得扣除闲置阶段。

当前执行顺序是 RMS 先完整发布、随后每窗 partial0→partial1→Add→写回，再进入后继窗。可合法重叠的候选需证明原 bank 1R1W、5 context与共享 Vector 端口足够，不能用宿主批处理或推测 busy 替代真实流水实现。

## 控制、失败保全与验证

小合成门覆盖实际 H2048/K2048/N160、三窗口共存、末 ACK 背压、held-success、RMS末ACK错阻止所有投影、投影末ACK错/held-success abort阻止后继。tick/watchdog中断保存实际在飞读写/ACK状态和partial输出，明确未自动drain、未发布、不是可恢复checkpoint；已接受成功不能追溯撤销。普通前置准入或事后比较异常另有 runner 失败记录与此前已完成输出，不能称为数值失败或自动恢复。

独立review修正了参考汇总的逐段门执行、FAIL退出码和实际输出重hash；7个轻门包含稀释反例、同长度篡改与优化模式非零退出。旧数字输出不变，仅从保全字节重新比较，原执行源码与当前比较器身份分开保存。

首轮入口漏 include_qkv、workspace split_k 参数及共享 Add 的延迟导入身份检查失败全部保留。正确实现使用显式 split_k=2048，预先冻结实际 Request 类型的源码闭包，不扩大容量或放宽身份门。完整M16/M128的53份Python源和9份原生源码/库/receipt均前后复核；先前小窗口旧runner的原字节按原SHA另存，不重绑历史PASS。

本轮完整M128前缀已到数值终态，下一依赖是本模型Conv/Prep/chunk与真正状态生命周期，再接O/residual及MoE。Q35C/Q35D、U00.2/U01、五block联合M128以及80%/90%目标继续开放。

紧凑结果与逐case性能字段：[QWEN35_35B_RMS_QKV_PREFIX_20261013.json](../reports/execution/QWEN35_35B_RMS_QKV_PREFIX_20261013.json)。本批实际M16/M128已独立复核；新源码独立checkout按完整workflow顺序重新构建Matrix/Vector，GDN465项33套、原Attention247项23套全部通过；执行源码未变。新精确SHA的CI另行核验，不能拿基线CI替代。

## 云端目录恢复后的独立重验（2026-10-13）

原19文件候选仅存在Git对象树96a065ce7a3fb2e573ab8656f2996fe60e945d29，
未挂到main；原工作目录及raw输出丢失。新独立checkout从已验证a5f49a1重建，
19文件逐blob SHA/长度核验且git write-tree精确相同。以上原记录保留为历史，
不把恢复源码当成恢复数值PASS。

新增显式恢复runtime身份与参考入口路径/独立digest参数，官方checkpoint、
完整N8192/K2048、权重/输入SHA、原逐段门与算术配方均不变。重新下载34,607,104B
原始三个张量，内容SHA与历史一致；获取manifest因新时间戳具有新SHA。
官方Torch/NumPy三个二进制与历史逐SHA相同，wrapper/真实receipt另行锁定。
未上传权重、activation、原生库或JIT转储。

首次冷小门缺pytest导致36项未执行，其余429项通过；首次RMS准入使用两tensor
默认选择遇到三tensor manifest而拒绝，发生在算术前。新增显式--include-qkv，
完整manifest和range/header/content验证仍保留。原失败记录不覆盖。

新RMS M16/M128已实际完成且官方对应输出bitexact；完整QKV M16/M128的恢复重验
及最终冷小门记录以新增恢复报告为准。硬件全周期、MAC利用率、占空比仍未知，
保留固定4096资源与完整周期分母，不能把宿主秒数/软件tick换算为RTL实测。

恢复后新实际结果：M16 85.038秒、M128 141.099秒，均完成真实RMS→52列窗口/
104 partial→共享Vector Add→全QKV ACK。M16逻辑16行而Matrix物理pad到128行，
有用MAC268,435,456/实际FMA2,147,483,648；M128真实128行，有用MAC与实际FMA
均2,147,483,648。尾窗N32仍计入。12.5%/100%只是执行算术有效比例，不是全周期
利用率或占空比，也没有新的carried状态验收。

重建入口`scripts/rebuild_qwen35_official_runtime.sh`与实际重放入口
`scripts/replay_qwen35_35b_prefix.sh`分开：前者生成新的真实runtime receipt供审查pin；
后者接受已验证runtime/payload路径和独立manifest SHA，先真实RMS，后全形状官方参考，
最后真实完整QKV M16/M128，全部raw留ignored work。两个脚本仅做语法验证；本轮实际
组件命令已逐步运行，不声称脚本整体曾重复执行。恢复结果：
[QWEN35_35B_PREFIX_RECOVERY_20261013.json](../reports/execution/QWEN35_35B_PREFIX_RECOVERY_20261013.json)。
