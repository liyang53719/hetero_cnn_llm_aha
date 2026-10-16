# 共享 Matrix 的原 Qwen2 Attention 软件端口模型

本目录接续公开21命令的模型数据链，不生成或执行RTL。`matrix_numeric.cpp`
只包含原 `transposed_down/numeric_smoke.cpp` 一次，普通QK/PV与转置Dense共用
唯一 `accum[5][16][256]`。不把Python输出快照、host FMA调用或模型tick当作
硬件SRAM、硬件周期或MAC利用率实测。

`matrix_service.py` 在同一资源上串行切换Dense和normal模式；每个真实结果、
done、seed ACK、legacy reply及owner终态都有接受边沿。未退休或错误排空中
不能换owner。Dense回调只对应当前同步driver已经核验的队列/sequence/generation，
可选ticket/epoch断言不构成异步传输协议。完整16×256结果是不可变字节快照，
按访问惰性解码；所有512个normal FMA仍实际计算，未裁剪非选中单元。

`attention_owner.py` 复用原Qwen2Block的8拍QK diagonal、0..15顺序归约、
source-bound FP32 softmax与逐key PV row0。输入仅来自accepted64B响应，
输出仅通过真实写回/ACK。Q/K/V长度使用本次完整cold prefill M，causal key
为0..query；尚不提供carried/prefix矩形调度或Qwen3.5配置。

异常合同有明确边界：原Matrix endpoint丢弃算术flags，只对协议报告error；
核心检查被选中的16个结果是否finite。非选off-diagonal溢出不改变合法输出，
选中的Inf/NaN返回Numerical。不能将前者扩大为忽略有效输出异常。原Scalar
Add/Mul/Div的fatal underflow策略、ExpNegative内部flags策略和固定舍入不变。

测试含独立libm.fmaf/整数舍入参考、实际共享Dense窗口/seed退休、特殊位模式、
协议错、错误排空、背压、复位和未发布终态。设置MATRIX_SERVICE_LIBRARY可
复用一次组合库；组合TU为matrix_numeric.cpp与原ffn_tiles/silu_recipe.cpp，
不得再次链接会引入另一accumulator的ffn_window/numeric_recipe.cpp。

公开整链入口位于相邻ffn_public/check_fullgraph_numeric.py。原native-v0与
FP32-final FAIL、未批准数值政策和最终硬件验收保持独立，软件canonical逐位
一致不能改记官方模型精度通过。

## 已接受内存债务修复（2026-10-16）

- 已完成：Attention 收到异 tag 或非规范 tag（包括 bool/float）响应时进入 Protocol
  排空，保留原 request 与 memory_pending；只有匹配的响应才能退休该已接受债务。
  memory_response_fire 表示匹配响应的消费，与 exact64 owner 的语义一致。
- 已完成：6 项短合成回归覆盖 read/write、正常匹配、匹配错误/长度错误、reset
  并发、未接受 offer，以及实际 resident PV32 子类的 A 租约保持到终态消费。
  Matrix/Scalar 使用无算术的空闲服务替身；实际 owner tick/ports/fault/finish 均执行。
- 待办：本次没有完整数值、native Matrix、Chisel/RTL 或性能通过结论。
  算术生成器、容量和 bank 布局未改。旧 pins/FREEZE/收据保持不变；未来运行需对
  新源码单独冻结与核验，不能继承历史结果。

```sh
python -B -m unittest candidates.qwen2_resident_matrix.ffn_attention.test_memory_debt
python -B -O -m unittest candidates.qwen2_resident_matrix.ffn_attention.test_memory_debt
```

### 2026-10-16：冷检查的历史与当前源码分开验证

- 已完成：四个 cold workflow 将原有默认入口、全部冷测试和拒绝测试保留在独立的 `55199873c0d5378c53538cc4273b53a3a012915d` checkout；历史 pins、失败摘要、参考结果均不修改。
- 进行中：当前事件提交必须通过 `scripts/check_attention_cold_compatibility.py`。136/139/154/177 项依赖中仅允许已审阅的 AttentionOwner 控制修复和三个 observation v4 身份更新；所有其余依赖、冻结包的文件集合与内容必须一致。另单独固定 resident/scratch/PV32 实现及两个回归测试源码，并记录实际事件提交和工具源码身份。
- 当前协议回归：真实 owner 的 6 项债务测试和 scratch 的 7 项所有权测试，普通与 `-O` 各执行 13 项，禁止跳过、预期失败或缺项。NumPy 2.3.5 仅用于当前测试的模块导入；历史测试继续使用 `-S`。
- 辅助检查命令：`python -B -S -m unittest scripts.test_attention_cold_compatibility -v`；`python -B -S -O -m unittest scripts.test_attention_cold_compatibility -v`。
- 当前闭包命令：`python -B -S scripts/check_attention_cold_compatibility.py --historical ../historical --package attention128 --event-sha "$GITHUB_SHA"`（另支持 `qkv16`、`qkv128`、`attention16`）。要求两个实际 Git checkout；缺文件或身份错误必须失败。
- 待办：合并后检查关联 CI 全部终态。历史测试通过仅说明历史冻结契约仍可复验；当前源码兼容和短协议回归不继承旧数值 PASS，不证明完整模型、fullblock、RTL 或硬件性能。
