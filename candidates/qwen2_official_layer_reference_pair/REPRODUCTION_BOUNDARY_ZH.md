# 复现边界

## 公开包可以复现

Python3.12标准库下的portable mock子集及独立公开身份检查，不需要Torch/NumPy/transformers、官方模型、网络或真实tensor。入口在加载原测试前后检查ML模块；原测试还安装拒绝数值import的finder。

原测试68项全部源码原样保存。portable选择66项，明确不运行：

1. SourceContractTests.test_frozen_capture_is_unchanged_and_public_disabled：依赖未随包提供的历史single-arm capture.py。paired公共入口仍拒绝的测试位于已选原测试中。
2. SourceContractTests.test_network_helper_is_exact_frozen_source_region：依赖历史import_gate_r2/worker.py及含私有路径的原provenance映射，未随包提供。

另外2项PublicIdentityTests验证公开源码完整字节及network helper区域SHA。这是新增发布身份检查，不是上述2项原测试复现。所有执行与日志SHA见evidence/MOCK_EVIDENCE.json。

full_layer_capture/pins.json只是原测试fixture兼容所需的原pins副本，和paired pins内容一致；不是另一个实现。

## 公开包不能自包含复现

没有权重/raw13、29输出payload、baseline输出payload、完整maps/modules、原4MB CONFIG、approval/capability/claim或私有路径。公开summary中原receipt/seal/review SHA只标识未公开原件，公开投影另由发布清单核hash。

实际数值复现需要：
- 合法提供与逻辑pins完全一致的13原始BF16输入和原官方config。
- 固定11包runtime、完整官方transformers dependency target与对应Python/native工具闭包，实际CPU/build/git/thread/deterministic profile一致。
- 新环境内重新形成路径与代码位置绑定的source/runtime/input全manifest、模块/映射候选闭包、独立exact review及新的明确执行授权。不能复用本次已消耗的一次性claim、approval或把原CONFIG SHA套到新路径。
- 完整执行资源限制、PID/start身份控制、窄网络策略、前后全hash与失败无completion seal原则；不因公开了源码就获准运行。

prepare_gate.py/worker.py/run_gate.py保持实际运行字节，所引用的外部审计目录和原始闭包不在fresh checkout中。因此本包只提供源码、逻辑身份及审查摘要，不是自包含模型runner。
