# 原模型完整 M128 扩时验证：实际观测域与完整协议 PASS

详见 [源码、独审摘要与边界](../candidates/qwen2_full128_extended_observed_validation/README.md)。新独立9000CPU/10800wall窗口下，原模型完整public21软件DUT完成21个completion、17个job、1个result；最终y与原批准实际观测数值域通过官方reference比较，经独立逐值、完整事件流和终态工件复核。

只改变时间预算/版本，原硬件/输入/数学/阈值不变，未采用normalization helper。旧3600CPU失败及所有原失败不改。24批准域、softmax FP32诊断及mask/repeat_k/repeat_v/logits四非物化节点分列；full29、observer noninterference、RTL和90%硬件利用率仍未建立。useful/nativeFMA的90.8343%不是周期利用率；accepted-slot算术比69.9801%也不是。全部任务状态、五block总目标不变，不上传raw输入/权重/张量/事件或可重构权重编码。
