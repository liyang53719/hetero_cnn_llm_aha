# Qwen2 L0 RMS1536 / FP32 RoPE cold→carried 软件候选 v2

状态始终为 `DIAGNOSTIC_NOT_ACCEPTED`；`policy_approval=false`、`hardware_v0_conformant=false`。各节点的数值 PASS/FAIL 与政策状态分开。此候选没有修改既有 v1、v0 numerical contract、硬件或 RTL，也不构成 ACK、时序、周期或完整模型质量验收。

## 变化与边界

新入口为 `scripts/qwen2_rms_rope_prefill_candidate.py`。基于 source-hash guard 的既有 carried v1 生成源，只替换 RMS 函数并添加独立表生成/单算子观察模式。Dense、bias、RoPE pair rotation、QK/PV、softmax 与 MLP 算术函数逐字保留；测试直接比较这些 source sections。

- RMS 使用已独立审计的普通 C 十节点函数：1536 宽、V8、四个 residue、三个16项 block、lane0..7，FP32 除1536、epsilon、sqrt、reciprocal，BF16 normalized 后乘 direct gamma，再 BF16。
- RoPE 表由同一候选 ELF 生成：FP32 exponent、powf、reciprocal、position multiply、sinf/cosf。全部位置0..255、64频率对应的 BF16 表固定为已核验 digest。FP32 与官方 MKL 表不逐位等价，也不声称跨机器等价。
- 源码构建和小单测不需要 ignored work 中的历史张量。production 读取 `reports/execution/QWEN2_RMS_ROPE_POLICY_20261011/` 中保持原 SHA 的审计摘要，运行数据仍只保留在 ignored work。

## 两阶段执行与证据

每个 M16 或 M128 pair 都重新编译候选，并实际执行 cold 和 carried，各一次。两个阶段使用同一 ELF，运行在两个独立软件进程。carried 直接读取 cold 进程写出的 `raw_stages/cache_k.f32le` 与 `cache_v.f32le`；没有从旧 candidate 导入新的 cold 结果，也没有将官方 cache 注入 candidate。

每阶段启动前冻结新源、依赖源、编译命令、ELF、header、Python/libtorch/动态库、输入 arena、表和 cache 的 hash。执行后重新核验输入不可变、旧 cache prefix、未使用 sentinel、15阶段顺序和进程完成。这里的 ACK 仅指软件文件/进程完成契约；没有验证硬件 ready/valid、总线 ACK 或 stall。

carried 保留四种 reference：官方和独立方程各自沿用其已核验 cold cache；官方和独立方程分别条件化在本次候选实际 cold cache。纯 cold 官方/独立 reference 可在 runtime、源、payload、原始文件 hash 重验后各复用一次，并明确计数。

所有29节点均比较。operator max_abs≤0.03125、mean_abs≤0.005；最终 y max_abs≤0.05、mean_abs≤0.01。FP32 softmax 没有获批 elementwise 门限，只保留诊断差异和 row-sum≤2e-5 语义检查。数值失败保留，不等于实现/身份错误；只有语义或证据错误阻止放大。M128 要求同源的新 M16 完整证据，并由人工代码审阅后启动。

## 本地控制

新小测包含：十个 compiled RMS 节点与已审计 Python 模块逐位比较、全位置 FP32/BF16 trig 与独立 C、旧 v1 未修改与各算术 source section 不变、宽1536的缩小 FFN cold→carried、真实 raw cache 依赖、cache tamper/错位/截断、absolute position 绑定、软件完成 ACK 丢失/重复/乱序拒绝，以及政策状态不可被数值 PASS 覆盖。

重现 focused tests：

```sh
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  work/recovery_20261011/python/bin/python -m pytest -q \
  tests/test_qwen2_rms_rope_prefill_candidate.py \
  tests/test_qwen2_rms_rope_policy_diagnostic.py
```

实际完整 pair 命令返回 exit1，刻意不向 hardware acceptance 发出成功状态。输出必须为新的 ignored work 目录；已有目录拒绝覆盖。M128 使用已审阅 M16 pair 的路径和 RESULT SHA，单个 C++ 阶段 timeout60秒，线程上限4（实际 C++ 单线程），每次先检查内存和磁盘。

## M16 已执行结果与报告修复

18 个 focused tests 通过（新候选7个，既有 RMS/RoPE 单算子11个）。实际 fixed M16 pair 目录为 `work/qwen2_rms_rope_prefill_v2_m16_fixed_20261011/`：cold4.11秒、carried4.62秒；两个阶段均校验全部29节点，语义全部通过。

- cold：官方和独立 reference 的全部已定义 BF16 gates 通过；官方 scores/logits 逐位相同，最终 y max_abs0.00390625、mean_abs0.0000198893。
- carried：官方 self-cache 与 actual-cache-conditioned 的全部已定义 gates 通过；两者 scores/logits 逐位相同，y max_abs0.001953125、mean_abs0.00000908754。
- carried 独立 self-cache 与 actual-cache-conditioned 仍各有 scores/logits 两节点失败：各1个元素差异，max_abs0.25、mean_abs0.0000406901。这一真实数值失败保留。
- cold/carried 的 n0、n1，共4组新实际输入，与官方相同输入的8个观察节点及最终 RMS 输出均逐位相同。该核验不把上游差异造成的端到端 n1 差异隐藏掉。
- softmax FP32 row sum 最大误差 cold1.78814e-7、carried3.57628e-7；elementwise 差异仍无政策门限。

首次 M16 在 `work/qwen2_rms_rope_prefill_v2_m16_20261011/` 保留。它暴露了新 reference loader 的布局错误：官方文件 q/k 使用 token-major export shape，却被按 head-major logical shape 读取，导致错误的 q/k 比较失败。原始实际计算不受影响。先对已有 raw outputs 只读重比对确认根因，再修 loader、增加非均匀 token/head 回归，随后在新的目录进行一次有实际修复理由的 M16 pair。两个 pair 的 ELF 与所有 cold/carried raw outputs 都逐字节相同。没有重写原失败 receipt。

首次运行的 Python 和测试源码按原 SHA 保存在 `work/qwen2_rms_rope_prefill_v2_m16_launch_source_20261011/`。布局诊断说明及逐文件 hash 比对在 `work/qwen2_rms_rope_prefill_v2_m16_layout_diagnostic_20261011/RESULT.json`。

## 一次 M128 cold→carried 的完整诊断结果

在 fixed M16 证据经过独立审阅后，只执行了一次 cold128→carried128。cold30.5507秒、carried33.1129秒；单阶段均低于60秒。两个阶段和 M16 使用相同 ELF SHA `4715ebf2180c6ccb08ce69f2434ca02cdd0447845164ce486b4bf069cbbd460e`。query128、总 key256、真实 raw token IDs0..255 与原配置/权重保持一致。

**仍是 `DIAGNOSTIC_NOT_ACCEPTED`。** 原 cold M128 的官方 scores max16、logits max8 失败没有消失；独立 cold reference 的 scores/logits max2、prob max0.031494140625、gate max0.041015625 也仍超原门限。cold 最终 y 在两个 reference 下都通过，max0.03125。

carried M128 四种 reference 的失败数均从旧 v1 的15节点降为4节点，原15节点失败 receipt 保留：

| carried reference | 本批失败节点及 max_abs | y max_abs | y mean_abs |
|---|---|---:|---:|
| official self-cache | scores1、logits1、n1 0.0625、gate0.0390625 | 0.0078125 | 0.0000537381 |
| official actual-cache | scores1、logits1、n1 0.0625、gate0.0390625 | 0.0078125 | 0.0000510651 |
| independent self-cache | q0.125、scores8、logits8、gate0.0390625 | 0.0078125 | 0.0000333940 |
| independent actual-cache | q0.125、scores8、logits8、gate0.0390625 | 0.0078125 | 0.0000307412 |

原 v1 official self-cache carried y max0.0390625、mean0.000243412；本批更接近 reference，但两个版本的最终 y 都已在原 block 门限内，不能把这一改善称为原失败变成完整 PASS。当前仍有中间 operator 失败，也没有精度或硬件政策批准。

按实际生产者/消费者拓扑检查，各新方法的第一个不同节点均为 Dense `qr`，而非 RMS `n0`。carried official 两种 cache 条件的第一个越界节点是 `scores`；independent 两种条件是旋转后 `q`。旧 v1 carried 四种方法都是先在 `n0` 发生差异，先在 `qr` 越界。该结论基于完整29节点的原始比较统计，不按节点字母排序。

本批4组 M128 actual n0/n1 同输入官方核验均为8个节点和最终输出逐位相同。端到端 n1 的 official max0.0625 和 independent max0.03125 是各自上游 residual 输入已不同的整链比较，单独保留。并未以同输入 RMS 精确覆盖它们。

cold/carried 全部语义检查通过；FP32 softmax row-sum 最大误差分别7.15256e-7、2.92063e-6，均低于2e-5。carried 官方 FP32 softmax elementwise max0.0171000361 继续仅作诊断，没有添加门限。

全部29节点、四 carried 方法、旧 v1 对照、逐节点 delta 与拓扑首差异/首越界在 `work/qwen2_rms_rope_prefill_summary_20261011/RESULT.json`，SHA `072e3e21dfa4c1103b9a4125ae83c58d7dae5c1136a6369609c83da12d0ca812`。

| 已冻结产物 | SHA256 |
|---|---|
| 新 driver | `41aea07ba09fc5c11f6aafbe14e83ebdba6e843a3cf47080a954a1032b6461e9` |
| 新 tests | `02c2c8cedc98b317ece7593fbd968d89424f65d7352deacb5e42a28ee5fed2ce` |
| generated C++ | `0cdfd2c6927eec8dfb72e315e9a1107d6966d47b6326de077bf77a9e3a73ded6` |
| fixed M16 pair RESULT | `989c3758008c6ec65db55ad51907f690da98762498a5ce3b3b11d4f375024299` |
| M128 pair RESULT | `99d551a40ca38af3d196015cf2dbb6e4ea80bdfec1f33f7c0d5cbb58a9131ac0` |
| M128 cold RESULT | `ae99b4ce2aceebcbbd9c83b1cbf2ab64605314ae60dfbf5423258db6469d2ab9` |
| M128 cold FROZEN | `489714248a931c18c623327eb8c6a20f7aeb81042b618737d50dcf9e06d400d4` |
| M128 carried RESULT | `07a63cbe29e26d398c60b0de980cbdf76caeea48cefb39cfe6f559a9592fdd39` |
| M128 carried FROZEN | `4a95ab44d0711f69cfb1c46315c07cefcdd12112df6535a29b58e1d62733d9a4` |

M128 实际命令：

```sh
OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 \
  work/recovery_20261011/python/bin/python \
  scripts/qwen2_rms_rope_prefill_candidate.py --tokens 128 \
  --small work/qwen2_rms_rope_prefill_v2_m16_fixed_20261011 \
  --small-sha256 989c3758008c6ec65db55ad51907f690da98762498a5ce3b3b11d4f375024299 \
  --out work/qwen2_rms_rope_prefill_v2_m128_20261011
```
