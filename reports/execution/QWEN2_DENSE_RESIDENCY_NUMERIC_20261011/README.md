# Qwen2 L0：真实 M16/M128 驻留映射的软件数值等价

`SUMMARY.json` 只保存身份、计数和验证摘要。固定官方权重/embedding 的 cold
M16、cold M128 分别完成原15个数学阶段，663552和5308416个FP32值全部逐字节
等于封存v0。两次使用同一ELF和188043264B只读arena；中间结果由前级实际写入。
独立复核重算了30个输出文件的SHA并重新逐字节比较，没有重复forward。

本次仅把原C++数学模型的Dense函数替换为实际bank数组、FP32前缀保存/恢复、
5个accumulator和2个结果槽/1个finalValue的数据移动。其余算术源码保持不变，
每个输出lane仍按递增K执行FP32 FMA。测试还覆盖3个C槽、两个N组、5+3上下文、
RNE边界、消减、末K偏置、非法权重和不完整M16前置证据。

这不是Chisel执行、Host命令/iDMA回放或时序仿真。FP32 arena中的BF16权重值
按逻辑BF16字节计流量，不是硬件DDR图像。原15阶段在Dense最终写入时合入偏置，
实际21命令的独立bias owner未执行。768KiB重新分区和FP32 seed硬件接口尚未实现。
CPU耗时3.70/24.94秒不能用作MAC利用率。原BF16阶段门和最终FP32门的FAIL保留，
政策状态始终为`DIAGNOSTIC_NOT_ACCEPTED`。

## 复现

安装轻量CI中固定的CPU依赖，从仓库根目录设置`PYTHONPATH=src:scripts`。
使用原`collect_qwen2_layer0_payload.py`和`qwen2_block_recipe_model.py`生成对应
官方payload及M16/M128基线，遵守后者的M16前置门；数值失败的M128仅可通过
显式`--diagnostic-m128`入口生成，非零退出码是保留的精度失败。完整原入口见
[模型优先计划](../../../doc/QWEN2_PREFILL_MODEL_FIRST_20261011_CN.md)。
没有这些原始基线文件时，不能只凭此摘要复验旧结果。

准备一次普通C++模型，随后用原M128基线的`readonly_arena.f32le`依次运行：

```sh
python scripts/qwen2_dense_residency_numeric.py prepare --output work/resident-replay/generated
python scripts/qwen2_dense_residency_numeric.py execute --generated work/resident-replay/generated --arena work/qwen2_block_recipe_m128_release_20261011/readonly_arena.f32le --arena-sha256 c34bcef98ca05d3c05087559741152082492b40fa6b74e072a1dec589c964a69 --tokens 16 --output work/resident-replay/m16 --timeout-seconds 90
```

先验证原基线收据、全部输入/输出hash，然后逐项比较M16的15个输出；必须全部
相等才继续M128。下面是只读比较示例，`tokens`为16或128；失败应停止，禁止以
宽容差代替字节相等。

```python
from pathlib import Path
import json
import qwen2_block_recipe_model as base
tokens = 16
root = Path.cwd()
old = root / f"work/qwen2_block_recipe_m{tokens}_release_20261011"
new = root / f"work/resident-replay/m{tokens}"
a = base.validate_recipe_receipt(root, old)
b = json.loads((new / "RESULT.json").read_text())
assert b["shape"]["tokens"] == tokens
assert [x["name"] for x in a["stages"]] == list(base.STAGE_NAMES)
assert [x["name"] for x in b["stages"]] == list(base.STAGE_NAMES)
for x, y in zip(a["stages"], b["stages"]):
    assert base.file_sha(old / x["path"]) == x["sha256"]
    assert base.file_sha(new / y["path"]) == y["sha256"] == x["sha256"]
    assert (old / x["path"]).read_bytes() == (new / y["path"]).read_bytes()
```

```sh
python scripts/qwen2_dense_residency_numeric.py execute --generated work/resident-replay/generated --arena work/qwen2_block_recipe_m128_release_20261011/readonly_arena.f32le --arena-sha256 c34bcef98ca05d3c05087559741152082492b40fa6b74e072a1dec589c964a69 --tokens 128 --output work/resident-replay/m128 --m16-prerequisite work/resident-replay/m16 --timeout-seconds 90
```

对M128重复上述比较。若fresh环境的合法输入identity不同，应记录新SHA并生成
同输入的新基线；不能假称重现这两份旧收据。不得绕过generator/ELF/arena哈希门。
小CI只执行合成数据的8项数值/控制测试，既有248项模型回归及21份报告；它不
下载真实权重，也不重新执行本摘要中的真实M128。
