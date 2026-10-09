# Qwen3.5-0.8B：生产 Host Q/K/V 投影 M1 局部门禁

状态：2026-10-09 本地实际 RTL 的两个 M1 投影 case 和一个真实 alias 拒绝 case 通过；默认关闭，严格为 PROJECTION_ONLY。不是完整代表性故障/reset 套件、全 M128、Norm/RoPE 或新提交 CI 的 PASS。

紧凑结果、身份 pins 和旧 CI 收尾见 `reports/execution/U00_2_HOST_QKV_PROJECTION_20261009/`。本地构建基于 `78e60a5ea661b295d1e1e04669a9d0c7cc52cb0b` 上的 dirty 工作区，由 403 个冻结源内容 hash 绑定；该 SHA 只是基线，不是本次数值执行的精确源码提交。后续 helper 修改不能追溯改写这三份回执。

## 实际通路与输入

使用原 `HostBlockTop → HostBlockCommands → QwenOwnerKernel → StreamingDenseOwner → MatrixPipelineService`。三个标准 Command128 顺序完成 Q/gate、K、V 投影；同一个逻辑 Matrix、8 个既有 Matrix512 slice 和单一 pinned iDMA，不新增 Matrix。独立拓扑回执与生成 RTL hash 一致，无时序签核。

三个命令均读取相同的 layer3 producer07 归一化激活。Q 输出为八头各 [query256, gate256] 交错的 4096 列；K、V 各 512 列。Q 并非 K 的输入，K 并非 V 的输入。Norm、RoPE、attention 和 FFN 不在本门禁中。

固定模型 revision `2fc06364715b967f1860aea9cf38778875588b17`、Transformers revision `14e738b5d0cc69aa27a95dde272aea41fde44f2f`。本地复用已封存的官方 baseline/cold 和 baseline/carried 输入，fresh=0/reused=2，不称为新官方执行。每例 12 个头的独立整数/C terminal 按原始 A/W hash 严格复用；未重新生成或加载全 accumulator trace。顺序 K=0..1023 的 FP32 std::fma、末端 BF16-RNE 是另一路比较参考。

## 三个已完成 case

| case | 实际窗口 | 数值/拒绝结果 | ACK及发布 |
|---|---|---|---|
| cold0_pass | baseline/cold/base0/count1 | Q/gate/K/V 5,120 BF16，canonical 位差0，762,218周期 | 3命令，10,240B |
| carried127_pass | baseline/carried/base127/count1 | Q/gate/K/V 5,120 BF16，canonical 位差0，762,218周期 | 3命令，10,240B |
| cold0_output_alias | K目标覆盖Q已发布窗口 | K在owner前返回status9，issued_jobs=1 | 保留Q的8,192B，K/V无发布 |

每例均检查完整 12,156,928 字节物理 DDR，含只读 A/W、guard、inactive 窗口和逐命令写后快照；已完成输出并存，只有成功写 ACK 改变模拟内存。两个 pass 的最终 ACK 延迟与 completion backpressure 均有实际覆盖。三次 supervisor exit=0。

native producer 比较仍用 max_abs≤0.03125、mean_abs≤0.005 原门限。cold 的 Q content、Q gate、K 零位差；V 有 2 个 BF16 值不同，max_abs=0.0001220703125、mean_abs=2.3847678676247597e-7，原门限通过。carried 所有 Q/gate/K/V 与 native 逐位一致。完整 native BF16 audit 仍 FAIL（本地 baseline 5、AVX2 9 项），不能由局部结果关闭 C02.2。

独立复核对三例重查原始输出、物理内存、日志和已存回执一致性，并在后续 helper 修改前核验 403 源文件、20 HardFloat 文件、RTL及程序身份。引用的是已保存复核，不使用之后修改的 helper 重算历史。

## 必须保留的构建恢复边界

初始 Verilation exit255/SIG9 和同目录生成重叠历史保留。后续串行生成的 538 个 C++/header 文件中，523 个原字节相同；15 个仅在受约束路径注释及配对 protectlib compatibility guards 上通过窄比较。原始全字节比较 FAIL 仍保留，不能写成 clean build 或所有生成文件 bit-exact。

窄证明、SV wrapper、已编译库/程序和 bounded-build 输入清单已由独立复核校验；日志/时间证明两轮生成先于编译，但没有每个 C++ 文件在编译前独立封存的 hash manifest。实际 Verilator ELF hash 为 `619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703`，与 675-byte wrapper 分开记录。

生成 RTL SHA256：`1a3e604b01a5b945e6cab11319bc6afd326c54b1e8524817b84144b123796229`。
程序 SHA256：`fbfa36d98a4ab5b0fd2fa3ef200a7ab1f12de289938ac0b77122d4529a8f38a2`。

## 旧 CI 与当前工作互不替代

`prior_ci_summary.json` 保留三条独立终态：7945a708 的 official Host V 四组 M128（fresh=2/reuse=0、262144 BF16）；同提交 synthetic legacy 两层（42命令、430 descriptors、1,409,024 FP32零位差、17,096,970周期）；78e60a5e 的 synthetic legacy 16-lane real/tiny block CI（2792项复核、原15阶段）。78e60a5e只改三个CI文件，Host源相同不等于Host在新SHA重跑。

fresh Host V artifact 的工具身份只直接捕获675-byte wrapper，原限制保留；legacy独立紧凑复核没有取得1.4M原始输出与全CSV，不能称独立重新逐值比较。本地两次旧回归中断和7945a708的Qwen2入口失败均保留为非PASS。详细终态和链接见 `doc/U00_2_HOST_BF16_V_20261008_CN.md`。

## 接续范围与优先级

先发布新精确提交后做 clean fresh CI、余下实际故障和reset门禁；Host QKV count16/full128 尚未运行。生产 Host Norm256/partial64 RoPE、带前缀attention和FFN仍单独推进。

GDN作为并行主线，直接推进真实生产Host的有界owner、显式状态读写及cold/carried续算，不把完整Attention收尾当作GDN启动前置。另行GDN owner单元实验不属于此QKV交付，也不能称当前main已有GDN实际RTL闭包。后续仍需35B-A3B的真实路由与expert链。

C03.2/C04.2/C05只增加本地M1集成子证据；S01/Q35A等大项不关闭。U00.2 ongoing、U01 to do、C02.2 native gate OPEN；三模型完整数值、固定资源整block useful-wall MAC≥90%、DC/PPA/800MHz时序均未验收。

交付只含源码、pins、hash及小摘要；张量、权重、NPZ、生成RTL/程序和全部DDR快照留在ignored work，不提交任何编码payload。
