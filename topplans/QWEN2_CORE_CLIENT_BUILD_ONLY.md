# Qwen2 Core：build-only 限定里程碑

- **PASS（实际）：** 原冻结模型/harness完成39对象+2PCH+1link，129 active产物204,109,468 B，最终ELF及静态5-file依赖/版本闭包通过；只发布hash/源码检查器。
- **尚未：** 模型执行、M1行为/数值、完整128 RTL/full29、真实Matrix FMA、硬件MAC周期利用率。编译CPU不充当硬件周期。原FAIL/STOP及canonical状态不变。
- **保留边界：** stock9Wno不是warning-free；PCH格式不是使用证明，MMD不是系统头全闭包。root预启动hash误比与reviewer分类纠错不误报为目标编译FAIL。
- 下一步须单独审查并准入原模型normal_m1运行，当前无该运行结果。

[最小build源码与证据](../candidates/qwen2_core_client_build/README_ZH.md)
