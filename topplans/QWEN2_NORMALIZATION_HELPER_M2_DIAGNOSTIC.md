# normalization helper：模型 + observer 单对 M2 诊断

[原字节源码、安全投影与完整限制](../candidates/qwen2_normalization_helper_m2_diagnostic/README.md)

- **改变 Python 模型结构，不是纯 observer 优化。** 原七角色 selective identity 基线与新 `_normalization_helper` 八角色组合，在两个顺序 fresh worker 中各跑一个 M2 owner job。
- 实际退出0；独审27,487 checks，3,072输出words、36因果scores、十字段7,272 cells与保留独立recipe逐位一致；每臂1,515完整事件、控制、192写与六个固定后置Scalar probes一致。
- 参考是历史已完成recipe，本次未重跑；当前参考数值只在两个当前终态后加载。DUT normalizer频次1，参考8/16，各自契约通过，不声称频次相同。
- B 在 helper PY_RETURN、`_op` 尚未return时观测；op为仅身份角色mask0，其余七角色与显式schema受检。不是已完成 `_op` return 或直接Scalar执行帧证据。
- owner CPU仅单对 **0.561403066 → 0.472320008 秒**。无重复/随机化/因果分离，不作稳定加速、纯observer收益、性能采纳或full128预算适配结论。
- 总计5.451501314 CPU /5.767274779 wall秒；45 CPU/60 wall原诊断预算不变。RSS63,787,008bytes仅采样high-water，不是连续总树峰值。
- 101个实际artifact/2,972,605B完整保留；仅公开源码/hash/角色化摘要，不上传rawtensor/字段/事件/私有路径。原审计脚本registry附加三元数据的过严比较及纠正历史保留。
- **所有原 full128/历史数值FAIL、canonical状态不变。** 仅这一个M2组合诊断有实际数值资格；无Scala对应、fullblock/full128/full29、RTL/硬件周期/MAC利用率/90%或性能采纳验收。
