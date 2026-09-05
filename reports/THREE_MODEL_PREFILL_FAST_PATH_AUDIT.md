# 整网 prefill 加速推进：当前可执行边界

用户要求：自动连续推进，不再每个小检查点停下来交接。

## 已执行调整

- `run_q1024_projection_continuous.py --projection 0` 已自动完成全部17段并运行收集器；1572864个BF16输出逐位通过，25656608周期。
- 检查点仅用于恢复；每个重任务仍限制600秒、CPU8–23、30GiB，单重任务运行。
- 协调器通过真实文件锁阻塞等待，不轮询、不重复启动、不自动忽略失败。
- 交接仅保留不超过40行；详细证据留在阶段报告。

## 不能误称为“三模型整网已可运行”

| 当前入口 | 已有证据 | 尚缺什么 |
|---|---|---|
| Qwen2 q1024 Q/K/V RTL | Q/K/V完整1024行投影通过；Q利用率18.39%、K/V18.41% | decoder其余算子、28层与最终输出的真实整网执行链 |
| `run_qwen2_q1024_full28_backend.sh` | 调用C++ generic_layer_backend，可作参考来源 | 不能作为完整28层RTL性能证据 |
| Qwen3.5/Qwen3.8 root-owner canary | 算子/小型控制与数值用例 | checkpoint参考、跨算子数据连续性、整网RTL/controller回放 |

依据：`OPERATOR_MODEL_CANARIES_V3.json`明确排除完整checkpoint推理和跨算子tensor-memory连续性。
本机项目`work/models`目前只有Qwen2权重；Qwen3.8权重/参考路径已向用户询问。

## 后续优先级

1. Q自动连续完成后已通过锁自动启动真实Matrix attention控制器数值验证，不再手动逐段调度。
2. 优先补齐整网可执行入口、参考轨迹和实际数据连接，不把更多微型canary当作模型完成。
3. 按既定计划区分数值RTL和整网cycle-accurate控制回放；后者必须证明真实握手/DDR/队列计时，不能用估算或直接累加算子周期冒充。
4. 若需要更快的仿真执行方式，先验证周期和数值等价；不能因赶进度改变完成口径。
5. 三个完整模型的q1024统计仍为OPEN，当前没有可诚信承诺的三模型完成时间。

## 已落实的连接整改

- `hetero_npu_integrated_v0.sv`仍实例化固定LATENCY的contract adapter，不可作为整网性能入口。
- attention的真实QK/PV迭代原先在testbench task中；现已新增可综合风格的`attention_matrix_tile_sequencer.sv`，支持128/256 head维度及既定hi/lo概率路径。
- 顺序/反压/尾部掩码/错误协议、真实Matrix7168项FP32数值、完整q128 attention1536行头/240tasks均通过；后者3317900周期、hash cc0eaf553c59b9f6。
- q128使用已有确定性算子向量，TB还提供tensor memory及SFU/merge服务；不是checkpoint整层或DDR整网性能。
- 详见`reports/execution/ATTENTION_ENDPOINT_PROGRESS.json`。不得把这项控制器单测计为模型通过。
