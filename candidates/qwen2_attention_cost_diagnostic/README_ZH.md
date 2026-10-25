# M2 Attention 四臂成本诊断：有限实际结果，默认不接完整 DUT

本包只新增独立诊断源码及脱敏证据，不启用生产路径、不修改既有 pins。唯一实际 M2 四臂运行 exit 0；实际独审通过的范围是组件运行闭环和已留存证据一致性，非完整 block、M128、RTL、硬件周期或性能验收。既有完整 M128 CPU 超限 FAIL 原样保留。

## 实际结果与局限

固定顺序为 clean off、clean on、count off、count on。clean 仍有必需的完整服务事件观测，不是无监测基准。两 clean owner-through-ACK 的 process CPU 为 0.179653944 秒与 0.619314592 秒，单次固定顺序受缓存、热身和顺序影响，不可当可靠 benchmark、主瓶颈时间占比或 M128 预测。精确阶段计时以 ACTUAL_RESULT_PROJECTION.json 为准。count 臂方法计时包含监测开销，且 inclusive 嵌套重叠，不可相加；计时分辨率可能产生零，不代表操作免费。

两个 count 臂各有 140862 callbacks；每臂 Scalar BF 19968 次、PV matrix_step 288 次、strict lane Add 576、Mul 36、BF 72。后者不是 ScalarService 请求。这里只是 M2 调用计数，不可推广为 M128 实测。

每臂 1515 条实际服务事件通过独立生命周期检查，原 ticket 只在跨臂比较时双射规范化。四臂 output/score/write 摘要一致，运行内原 comparator 比较通过。原独立 AST Python recipe 在全部 terminal ACK、资源释放、四臂控制比较之后运行，十字段及 output/score 对照通过；共享原精确 RNE primitives 如实披露，不等同官方完整 Transformers forward。只捕获因果有效区域，未来 padding/sentinel 不是实测值。

独审未重放 target 或解码 tensor。off/count 的原始 outputs 未分别留存，不能事后独立重算四臂数值。旧 launcher 只提供 RESULT/PARENT，没有独立最终 receipt/seal 或完整 pre/post hash ledger；固定 worker 前后检查以及本次独审当前 1019 pins 重验构成有限依据。包外 57 artifacts、4599104 B 的 hash 清单是后补外置绑定，不伪称运行原生 seal。末映射为 17 ELF 加 2 locale/cache，仅快照而非完整 OS 事件历史。1 GiB 是 AS 硬限，无 peak RSS 实测产物。

## 源码与测试身份

13 个 Python 文件均逐字复制原 r2，没有 path adapter、没有新执行资格。完整 316-file assembled source、已有 Matrix/SiLU ELF、Python/NumPy、qr/kr/v 和 witness 由外部精确配置供给；本包没有私有 config、授权账本、tensor、events、maps 或安装路径，不自称自包含。

cost_probe 直接正常加载原 service_trace.py 的 monitoring_enter / monitoring_stop / capture_error，不复制简化 lease。原两套 28+14 测试加 13 probe+22 adapter 为每模式 77 个逻辑身份，normal/-O 共 154 test executions；独审重复相同身份，不是新增 154 unique。历史 v1 的 13 mocks 不足以证明 lease 安全，原 BLOCKED 与 unsupported local PY_UNWIND 失败保留。R2 使用新配置，未覆写历史失败。

公共源码与原执行源 hash 见 pins/SOURCE_PROVENANCE.json；运行 1019 条逻辑 pins 保留原顺序/重复/bytes/hash，不含物理定位。原 receipt/review/hash 与新 projection 文件 SHA 是不同身份。本次打包只复制、hash 和 git roundtrip，没有重新 import、mock、native 或数值运行。有限准备审查和实际独审身份见 evidence；独立发布复核由包外发布收据绑定。

## 可复现接口（不是自动运行或再次授权）

在干净 checkout 中，原监测 lease 与测试闭包位于 candidates/qwen2_ordered_event_stream。原 helper 必须匹配 SHA e7c078e6235adc02b762243e407d8830a9401b2c9638e01608ea0923622bd172。Python 3.12 的测试接口：

```sh
python3.12 -I -S -B candidates/qwen2_attention_cost_diagnostic/test_cost_probe_mock.py --lease-source candidates/qwen2_ordered_event_stream/service_trace.py --lease-sha e7c078e6235adc02b762243e407d8830a9401b2c9638e01608ea0923622bd172 --reviewed-tests-root candidates/qwen2_ordered_event_stream
python3.12 -I -S -B candidates/qwen2_attention_cost_diagnostic/test_cost_probe_lease.py --lease-source candidates/qwen2_ordered_event_stream/service_trace.py --lease-sha e7c078e6235adc02b762243e407d8830a9401b2c9638e01608ea0923622bd172 --reviewed-tests-root candidates/qwen2_ordered_event_stream
```

必须同时保留原 28/14 suites；上述两个命令单独不等于 154 次完整回归，本次未重跑这些公共命令。实际入口仍为 launch.py --config LOCAL_CONFIG --review LOCAL_REVIEW --review-sha EXACT_REVIEW_SHA --approval LOCAL_APPROVAL --approval-sha EXACT_APPROVAL_SHA --m 2 --output FRESH_OUTPUT。私有输入/完整源/依赖必须另供并逐 hash 绑定，新执行须新准入；不可复用旧一次账本或把逻辑 pins 当可执行 config。

原限额：1 CPU，30 CPU 秒，45 wall 秒，1 GiB AS，每输出文件 4 MiB。实际 worker CPU 8.210441282 秒、parent wall 8.297031357 秒。没有新长跑授权。固定 4096 MAC 与 legacy PV 63.57% 上界仍挡住 80/90% 目标，本包不改变此结论。
