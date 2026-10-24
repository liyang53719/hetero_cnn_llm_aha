# Qwen2 selected 冷测工作流：截止边界加固

- [x] 仅给已有轻量 workflow 添加两处拒绝：每个子进程返回后，以及最终输出 PASS 前，elapsed >= 120 秒即失败。
- [x] 保留原五组测试、normal 76 / -O 76、单子进程20秒CPU / 256MiB / 单CPU / 最多30秒wall、总120秒和job5分钟预算。
- [x] 保留原无skip、无empty、精确计数检查；不改任何模型代码、数值容差、原始运行证据或其他workflow。
- [x] 新增4项纯mock回归：最后子进程120.01秒、恰好120秒、最后日志处理后120.01秒均拒绝；正常完成保留76+76。
- [x] 回归脚本在普通和优化的隔离Python中各4项PASS；它不启动子进程、不导入候选、不改CPU affinity或资源限制。

复核命令（仓库根目录）：

```sh
python -I -B tests/test_qwen2_selected_cold_deadline.py
python -I -B -O tests/test_qwen2_selected_cold_deadline.py
```

原提交1bdf70e的自动CI 40124039643已正常完成76+76，远早于120秒边界；本补丁不会回写或否定该历史结果。修复的是极端边界下最后子进程或日志处理越界后仍可能打印PASS的遗漏。新提交自动CI须单独观察，不提前宣称通过。

范围仅限工作流截止判定和mock回归。完整M128、native、Scala/RTL、真实硬件计时/利用率没有在本批执行，原TEMP/INCOMPLETE边界不变。
