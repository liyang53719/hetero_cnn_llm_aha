# M16 官方单层参考：源码准备片

**TEMP / EXECUTION_DISABLED。没有生成新 M16 数值参考。** 本片仅新增独立候选包，不改生产入口、旧 pins、旧参考或 canonical。基线为 `74fa592972eb47d9fadcb14ff0ac22374bd8329a`。

- `capture.py` / `pins.json` 与已独审冻结源逐字相同，分别 SHA256 `4fe8428c8ae2a1d96a900b0fc26e9a34cb98663f037c029595a5e51d4fc9bfc4` / `0a129018f3c82d959014a0d7a205d736ea0d589d958e970cc96f7ecf2899fa13`。
- 正式实现准备真实 Transformers 4.40.1 `Qwen2Config` 与完整 `Qwen2DecoderLayer.forward`，不是旧38语句AST算术回放；仍不是整个 `Qwen2Model` / `ForCausalLM.forward`。配置保留32768 RoPE、eager显式选择，原始 raw13 BF16 参数直接绑定。
- 29项由原运算 hooks/trace 捕获，mask为原入参，cache K/V为冷语义别名，未物化/未观察范围详见 [冻结设计说明](README_ZH.md)。不拿参考填DUT缺失字段。
- 公共 `run_capture` 无条件拒绝。私有 `_capture_impl` 不是安全沙箱，也不是当前获准的执行入口；完整一次性launcher、实际import/maps、资源和终态清理、实际29观测/无干扰尚待另片闭合。

## 可复现的纯软件测试

从仓库根目录执行：

```sh
python -I -S -B candidates/qwen2_m16_official_layer_capture/test_capture.py
python -I -S -B candidates/qwen2_m16_official_layer_capture/test_review.py
python -I -S -O -B candidates/qwen2_m16_official_layer_capture/test_capture.py
python -I -S -O -B candidates/qwen2_m16_official_layer_capture/test_review.py
```

也可显式设置 `QWEN2_OFFICIAL_MODEL_SOURCE` 指向同 SHA 官方 `modeling_qwen2.py`。这仅供完整源码 compile-only 检查，绝不 import/exec 官方类。实际源仍须 hash 匹配，缺源不 skip。两测试入口均阻止导入 torch/numpy/transformers。

本交付 normal/-O/-I-S/-I-S-O 各21项原测试和32项独审扩展通过，共212次测试执行（21项套件是32项扩展套件的子集，四模式重复执行，不是212个独立用例；逻辑用例共32个，即原21项+独审新增11项）；只是stdlib/mock与源码身份检查，不是Chisel、真实模型、native数值或RTL通过。`PUBLICATION_ADAPTATION.json`明确唯一发布适配为测试路径可移植化。历史21/32日志和原receipt SHA保留，未冒充新数值证据。

## 输入、原门槛与待办

`pins.json`给出raw13的文件名/shape/bytes/SHA与官方源/config身份；不包含权重或输出payload。`INPUT_METADATA_PROJECTION.json`为先前独立输入审计的脱敏子集，不是重新读取真实tensor的证明。`GEOMETRY_PROJECTION.json`为静态29几何。原M16 C++辅助oracle并非官方目标；M128旧参考为AST subset且使用rotary256，不能截取其输出或继承PASS。

原节点BF16 max_abs≤0.03125且mean_abs≤0.005；最终y max_abs≤0.05且mean_abs≤0.01；nonfinite拒绝。softmax_fp32没有获准误差门，仅保留原row-sum 2e-5语义检查。本片不运行比较，亦不新造阈值。

独立官方依赖获取/normal-import冷门正在另片处理，不纳入本包PASS。第一次cold总体FAIL已保留：网络bind事件被拒；IPv6 loopback探测是最强静态候选，原事件未记录地址/调用栈，动态归属未证实；不得用它升级此处运行资格。这里不含该冷门代码、账本或原始maps。

完整block固定4096 MAC分母不变，legacy PV路径63.57%理论上界仍保留。本片不证明80/90%利用率、周期、II、频率或完整M16/M128资格。

发布审计说明：内嵌 `evidence/PACKAGE_REVIEW.json` 是首版包的历史独审，保留其当时 README/VALIDATION 的真实hash。本次仅澄清旧bind归因不确定性、重叠套件的执行计数及此历史审计标签；执行源码、pins、测试断言和日志未改。当前发布独审以本次 DELIVERY 指定的新外部r2收据为准，不把旧收据冒充修订后文档的字节验证。
