# U00.2：两组冻结真实输入的四路 RoPE 舍入消融

## 结论和边界

在本地与 GitHub CPU 两套历史真实前缀输入上，只有“四个乘积全部 BF16 RNE，再做加法并末端 BF16 RNE”的软件候选逐位复现所有已保存的官方 native 乘积和输出。仅 sine 乘积 BF16 可以修复现有反例且通过这两套样例的原门限，但仍有 38,880 个输出元素的位模式不同，不能据此选择为 source-native 等价策略。

本轮未改生产 RTL、既有硬件 oracle、native reference 或容差；没有候选 RTL/PPA/完整 block/MAC90% 通过声明。既有 FP32 RTL 与自身 oracle 的一致性仍成立，远端 source fidelity 的 0.0625 > 0.03125 拒绝仍保留。下一硬件实验应单独命名 all-products-BF16 候选，先明确转换异常位与接口策略后再实现、生成和回放实际 RTL。本轮不切换默认算术。

## 固定数据而不是在新 CPU 重算夹具

每套输入是 cold/carried M128 的 Q8/K2、64 旋转维的 split-half i/i+32 配对：81,920 pairs、163,840 输出；两套合计 163,840 pairs、327,680 输出。

`tests/fixtures/rope_rounding/` 保存两套可独立复跑的紧凑 NPZ：

- 同一历史 native Q/K Norm、cos/sin 的输入原位
- 历史官方 cos/sin 两个产品 producer 原位及最终 native 输出，绝不从本轮候选重算 expected
- 历史两个实际 RTL wrapper 的输出和异常位
- 精确 group 映射、原始完整 NPZ/报告/vector/实际 RTL 文本的 SHA256 和运行环境

远端 native 原归档为 run37559899983/artifact11456093688，SHA256 9892a37713d63dfa2d3025d1f34b12a7f606e08b8faec919982bb2e612137b33。其完整 producer NPZ 与独立历史 RTL run37559899826 使用的 NPZ SHA 完全相同。两个报告因时间戳不同并非同一字节，不能混称同一报告。本地保留另一套原数组，不能用远端或新 CPU 结果覆盖。

提取器 `scripts/freeze_rope_rounding_corpora.py` 对原报告和原完整数组验 SHA，再核对输入、两个实际 RTL 文本/NPY/vector 一致，直接切片保存 native products/output。提取期间不执行模型算术。执行器另外固定紧凑 NPZ 的 SHA，拒绝篡改、错误 dtype/shape、未知 corpus 和非有限值。原始归档未来过期不会影响已提交的两套紧凑冻结输入。

## 四路逐节点软件合同

顺序均为 ec=e×c、os=o×s、es=e×s、oc=o×c。四个乘积先各自 FP32 RNE；按候选选择额外 BF16 RNE；然后 e′=FP32_RNE(ec−os)、o′=FP32_RNE(es+oc)，最后软件投影 BF16。无 FMA。

| 软件候选 | 额外 BF16 产品边界 | 本地不同输出 | 远端不同输出 | 本地最大绝对差 | 远端最大绝对差 | 原门限 |
|---|---|---:|---:|---:|---:|---|
| fp32_all | 无 | 26,091 | 26,348 | 0.03125 | 0.0625 | 远端拒绝 |
| cos_bf16_only | ec、oc | 17,448 | 17,524 | 0.03125 | 0.0625 | 远端拒绝 |
| sin_bf16_only | os、es | 19,438 | 19,442 | 0.03125 | 0.03125 | 两套条件样例通过 |
| both_bf16 | ec、os、es、oc | 0 | 0 | 0 | 0 | 两套逐位一致 |

门限仍为 operator max_abs≤0.03125、mean_abs≤0.005，并对每套的四个 Q/K 分组分别检查。各候选本地/远端平均绝对差分别为：FP32 0.000790893/0.000801761；cos-only 0.000462629/0.000470623；sin-only 0.000573379/0.000577873；both 0/0。FP32 与 cos-only 的远端超限项均只有原反例一个。

完整报告同时比较：末端 BF16 对冻结 native、末端 BF16 对原硬件软件投影、候选 FP32 sum 对实际旧 RTL、选择后的产品对冻结 native products。每组保留绝对误差均值/分位/最大值、正负方向、位差数、超过原门限数和有序 representable-bin ULP 距离。每个不同位置的 pair/lane 索引完整保存在 NPZ，可用完整 trace 定位，不只保存最坏样例。

ULP 定义为跨过多少个 BF16/FP32 可表示编码，±0 合并为同一个数值。它不是用单一局部间距作除法。接近抵消时原 native 输出可能恰好为零，所以最大 BF16-bin 距离可达 15,316，而绝对差只有 0.0064697265625；不能把这个数当作大幅相对误差或替代原绝对门限。报告另外保留 signed-zero-only 差异与 native零/candidate非零计数。

## 永久反例的因果定位

远端 carried Q token110/head4/channel50（absolute position238），pair index69266，even通道18/odd通道50；输入 bf920000、c1100000、3f800000、3ce10000。

- ec=bf920000、os=be7d2000、es=bd005200、oc=c1100000。
- FP32 与 cos-only：es 未舍入，odd sum=c1108052，末端 BF16=c1110000（−9.0625），仍拒绝。
- sin-only 与 both：es 舍入 bd000000（−0.03125），odd sum=c1108000（−9.03125，恰为 BF16 中点），ties-to-even 得 c1100000（−9），逐位匹配保存的 native。
- 不能因为 sine-only 修复该 witness 就外推为 native 等价；两套全量样例仍有 38,880 个不同输出。

## 独立检查与特殊值范围

主算法复用已验证的 integer-dyadic FP32 每步 RNE，并保留每 pair/每候选全部18个 word：四个原产品、四个 FP32 flag、四个候选产品、两个 FP32 和、两个 FP32 flag、两个 BF16 输出。

独立 C 参考 `scripts/rope_rounding_fenv_reference.c` 不调用 Python oracle：volatile binary32 运算、显式 FE_TONEAREST、禁 FMA/fast-math，BF16 用 discarded-bit 与 parity 比较。它逐一验证每个中间值和 FP32 flags；开跑先拒绝 FTZ/DAZ/不支持的宿主。所有真实输入的产品与加法都通过，不能用对终值的比较掩盖中间误差。

补充 7,207 个算术 pair：原 2,055 directed/random FP32、额外4,096有限 BF16随机位、32个 signed-zero组合、1,024个raw-FP32 subnormal组合；与真实模型流量分开报告。ties-even、cancellation、non-FMA、BF16 subnormal conversion 单测/C self-test 保留。NaN/Inf、FP32中间overflow、BF16 overflow明确拒绝，不能称为全 IEEE 特殊值支持。BF16 conversion 的异常位尚未定义为候选 RTL 合同；报告内 flags 仅表示实际执行的 FP32 操作。

HardFloat 的precision-p/unbounded-exponent tininess 和宿主 fenv 在min-normal编码边界可能有差异。执行器只允许并完整列出该确切类型的underflow-bit差异，其他位/数值差异均拒绝；本机此次没有这种差异。native的 unary−odd 与 RTL 的产品 sign-bit inversion 在有限RNE域含±0等价，不能替换为算术0−product，也不推广到NaN payload。

## 可支持的硬件代价判断

实际 `rtl/sfu/fp32_rope_pair.sv` 与 `fp32_rope_pair_pipe.sv` 均为四次FP32乘法、两次FP32加法，输出FP32。保留这些算术单元的最小候选：cos/sin-only 各增加2处产品转换，both增加4处；若末端也实际输出BF16，则另有2处转换。以上是每pair的转换操作/边界数，仅在不共享设计中才对应并行转换实例数，绝不是综合cell数。

有限FP32→BF16 RNE可用guard/sticky/tie条件加高16位增量，仓库 `fp32_rmsnorm1536_chunked.sv:48–55` 有类似逻辑。舍入后可零扩展回FP32加法输入，无需新增乘法/加法算术操作。不能由此宣称FP32乘加器面积减少。

结构上可在组合wrapper结果寄存器前或pipeline的MWAIT/AWAIT现有capture前插入组合转换，因此“可能无需额外架构级流水stage，前提是满足timing”。未跑候选综合/布局，不能承诺不降频、面积/功耗或吞吐不变；若需增加stage，要重新验证valid/data/flags与背压。原回放cycles含人工输入间隔与输出阻塞，不是性能证据。

末端转换不等于BF16 store。现有endpoint仍写32位结果到512位buffer；packing、mask、owner、memory接入要单独验收。没有带宽收益或MAC利用率推论。

## 执行与后续

- `python scripts/run_rope_rounding_ablation.py --output <fresh-dir>`
- `python -m pytest tests/test_rope_rounding_ablation.py tests/test_rope_hardware_oracle.py`
- `python -O -m pytest tests/test_rope_rounding_ablation.py tests/test_rope_hardware_oracle.py`

新增CI名称明确为software-ablation-not-RTL，上传完整原始trace/独立C trace/全部mismatch索引和报告；绿色CI只接受这次冻结输入的软件消融。旧硬件gate与source-fidelity反例保持不变。

下一有界实现：单独命名both-BF16候选，冻结FP32输入域/BF16输出域、overflow/nonfinite/转换flag合同与背压；实际Chisel/HardFloat生成和两个wrapper回放后，才评审接入Qwen3.5 owner。Q/K256 Norm的1+weight、packed Q/gate、partial64布局、表/位置/cache与FP32/BF16存储仍要集成。三模型完整block数值与固定资源整block useful-wall MAC≥90%继续OPEN。

## 独立硬件候选后续

四产品BF16策略已另建有实际16位输出与明确转换flags合同的实验RTL，详见 `doc/U00_2_ROPE_BF16_CANDIDATE_20261007_CN.md`。本软件消融记录及旧生产算术保持原样；硬件候选有自己的源哈希、独立参考、生成/回放和协议测试，不用软件表格代替实际RTL证据，也不自动升级为生产政策。
