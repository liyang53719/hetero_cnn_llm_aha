# Qwen2 public21 当前生产 parser 控制基线

基线 main：`8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689`。
本门用当前 `HostBlockCommands` 真正读取 Command128/descriptor，经 Chisel → RTL → Verilator 检查完整21命令。owner 返回由测试台控制，因此证明的是公开入口、字段与事件生命周期，不是算术执行或完整block RTL。

## 新执行结果

- 同一 DUT 不重置依次执行 M16、M128、高地址重定位 M16（epoch 7/8/9）。
- 每次21 completion、19 owner、236 metadata read；逐字段验证 kind、M/N/K、A/B/C/D、tag、writeBytes、三类 dtype flag，所有其余内部字段为零。
- 对照由现有公开字节软件 parser 新运行生成，现有 `official_bf16/execution.py::validate_job` 只提取身份固定的角色检查，不执行其数值程序。
- 原 Attention QK/Softmax/PV 三命令预检与融合保留；score/probability没有实际DDR读取。
- 请求、owner返回、completion、Host result均加人工保持。无owner返回前不得发布；拒绝 short、wrong-tag、owner error、metadata error、unknown opcode、跨launch stale producer，共六类。
- 新门是1项实际RTL测试，0失败/0取消/0忽略；portable入口26.107s，157源和10份metadata文件前后SHA不变。12项冷门 normal / Python -O各过。
- 2769拍只是本控制夹具每个成功launch的观测，包括人为stall和mock owner延迟；没有算术资源分母、MAC利用率或完整block性能含义。

## 与已过数值模型的差距

当前默认 parser为19 owner；历史 resident FFN三命令融合后的软件路径为17 owner。生成物将二者分开，不继承历史数值PASS。当前 Chisel `QwenOwnerJob` 尚无 candidate 的 materializeDenseOutput，生产kernel也未接入 public Dense reduction coordinator。本门不改变任何生产源码或默认选择。

后续在严格固定 current-main 字节的候选组合中保留 official/resident 规则，接实际 parser → route latch → DenseBlockReductionCoordinator，再验证真实共享owner/算术。不能仅凭PC或N1536区分Q与O，需角色/typed字段/materialization一致；不能把控制返回冒充真实ACK算术链。

## 复现

冷门：`python -m unittest discover -s candidates/qwen2_resident_matrix/public_dispatch -p 'test_*.py' -v`，另加 `-O`。

1. `python candidates/qwen2_resident_matrix/public_dispatch/generate_contract.py --out <fresh-fixtures>`。
2. 启用已有固定 Chisel/HardFloat/firtool/Verilator工具链，使 `sbt-chiseltest` 和 `HARDFLOAT_SOURCE` 可用。
3. 对生成的 gate.json 计算SHA256；运行 `python candidates/qwen2_resident_matrix/public_dispatch/run_control.py --fixture-root <fresh-fixtures> --gate-sha256 <sha256> --out <fresh-results>`。

缺少manifest pin、源码漂移、metadata篡改或旧输出目录均硬失败。fixture只有公开metadata，没有权重、激活或参考结果。CI本批只新增12+12冷门，外部RTL复现没有自动折算为CI执行。实测元数据见 `reports/execution/QWEN2_PUBLIC21_CURRENT_DISPATCH_20261014.json`。
