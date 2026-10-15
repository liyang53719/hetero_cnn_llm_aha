# Bounded ATen Q projection arithmetic diagnostic

This is a new Python/C++ **software** candidate, not Chisel/RTL, and not an
update to the current DUT, public21 runner, prior expectations, or error gates.
The existing DUT may satisfy its original numerical error gate despite using a
different floating-point graph. Bit equality is a diagnostic, not a new gate.

Fixed source: Torch 2.10.0+cpu, commit
`449b1768410104d3ed79d3bcfe4ba1d65c7f22c0`, ATen AVX2, mkldnn disabled.
`BlasKernel.cpp:409-438`, `ReducedPrecisionFloatGemvFastPathKernel.cpp:23-26,
138-148,289-303,350-388`, and `functional_base.h:59-75` define the graph.

For each output initialize S[8][8] to +0. For t=0..23, r=0..7, lane=0..7:
`S[r][lane] = FMA_F32(x[64*t+8*r+lane],w[64*t+8*r+lane],S[r][lane])`.
Reduce register indices at offsets 4,2,1; then lane indices at offsets 4,2,1.
Retain the source's zero-tail add. Add BF16-expanded bias in F32 and round once
to BF16 RNE. There is no 1024+512 split or adjacent-pair reversal.

One logical output uses 64 persistent F32 accumulator values, plus operands and
temporary values. The C++ loop serializes them. It does not establish a mapping
to 4096 physical MACs, SRAM ports, clock cycles, or utilization. The separate
resource-screen task must account for those. Per output:1536 FMA,56 register-tree
adds,7 lane-tree adds,1 zero-tail add,1 bias add,1 BF16 conversion.

RMS reproduces the existing pc0 explicit V8/ILP4/three-block graph from raw x and
gamma, never loading an official intermediate as a candidate operand.

All execution requires an explicit call/`--execute`. `probe.py` uses fixed local
input hashes, six original native identities (including the local 30MB Python,
not CI's 17KB executable), fresh output, 4/1 Torch threads, and a full
`nn.Linear(1536,1536)` on shape `[1,128,1536]`. It compares existing completed
attempt01 `qr` bytes with this newly executed reference under the original
max_abs<=0.03125 and mean_abs<=0.005 gate. `qr` means projection+bias before
RoPE; the old public `q` name denotes post-RoPE data.

Only eight selected columns across all128 rows execute in the new candidate.
The official operator is never sliced to a smaller shape. The probe is bounded
by90CPU seconds/4GiB address space and must be launched with150s external wall
timeout. No complete Transformer forward, checkpoint download, or CI trigger.
Reports remain local. An old failed whole-block attempt's completed prefix
artifact does not become a fresh DUT execution or full-block acceptance.

## 中文状态与允许公开的聚合结果

- Done：local01 的旧QR产物对新官方子链通过原门；26个元素逐bit不同，
  max_abs=0.0078125，mean_abs=9.913492249324918e-08。
  独立8×8算术候选检查1024个元素，差异数0；RMS差异数0。
- Done：local02 六个前缀节点均有限且通过原门。各节点的
  max_abs / mean_abs / 不同元素数如下，未放宽0.03125 / 0.005门限：
  - n0：0 / 0 / 0
  - qr：0.0078125 / 9.913492249324918e-08 / 26
  - kr：0.0078125 / 2.6824272936210036e-07 / 5
  - v：0.0009765625 / 5.002220859751105e-08 / 17
  - q：0.0078125 / 9.357851619521777e-08 / 14
  - k：0.015625 / 7.152557373046875e-07 / 2
- Ongoing：独立审核这些源、测试及诊断证据。CPU归约图不同并不意味着
  需要改变原硬件资源结构或强制复现CPU逐bit；旧前缀已通过原误差门。
- Todo：fresh DUT完整链路、attention/FFN/整块与硬件证据尚未由本目录
  建立；五block128的既有状态保持不变，不能据本次前缀结果改判。

上述结果是历史已完成前缀产物的新比较，不是fresh DUT。原始数据、
详细收据、实际张量hash、路径和布局元数据只留本地，不发布work结果。

仓库根目录的正确小测试入口（使用固定本地NumPy环境）：

`python3 -m unittest candidates.qwen2_aten_q_projection_candidate.test_model candidates.qwen2_aten_q_projection_candidate.test_prefix_probe -v`

共9项通过；使用显式module入口，不能用直接目录discover替代包内相对导入。
