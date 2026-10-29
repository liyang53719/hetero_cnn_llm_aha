# 五 profile 完整 128-token provider-only 实际摘要

来源为唯一已完成采样的 ACTUAL_SUMMARY.json，SHA-256 `17646e6a6b6ec2f50fe550830c3f2184a4261df662ecaa35b92c68d521c541a6`。导出器只接受该原始字节身份，再按字段白名单导出，不读取或发布 weights、NPZ、provider payload、路径、PID、argv。

7 个 stage 均 native0 / cleanup 完整；整体编排 363.974443389 秒，stage 耗时之和 249.513020236 秒，二者不同且都不是 DUT 性能。五个 profile 均为完整 128 token 的输入 provider 映射；原参考身份已核验，本轮没有新参考计算、DUT 执行或完整 block 数值通过。

每 stage 仅 1 次进程采样，最大只读树 census 21.524005078 秒。零或小 RSS 样本不代表实际零占用、最小占用或峰值上界；资源资格明确 INCOMPLETE。观测到的树最大字节数也是采样结果，不是瞬时峰值上界。摘要不导出已过时的剩余磁盘空间。

复现提取（需自行持有上述原始摘要，不从本包恢复 payload）：

    python -B export_provider_measurement.py --input RAW_SUMMARY.json --output NEW_SUMMARY.json
    python -B test_export_provider_measurement.py
    python -B -O test_export_provider_measurement.py

本包 4 个轻量测试普通 / -O 均实际通过；另实际使用锁定原摘要执行了导出。未重跑任何采样、安装、参考或 DUT。
