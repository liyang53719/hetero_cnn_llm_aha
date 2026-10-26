# 真实 Matrix 路线：两 Scala 源 compile-only 里程碑

- **实际PASS仅编译/静态身份**：2源→3 classes /63834 B，554 stage保持，1325 pins/5 inventories，exit0与cleanup闭环。
- 原Core＋service＋legacy的8×512真实drain源码接线，不用脚本tile替身；但未elaboration/运行，**不能声称真实FMA数值PASS**。
- 13 provider恢复及22 endpoint/4 ICG/四FMA源ABI只作声明/来源资格，不是生成闭包。旧4096资源FAIL、无全tileprobe、非零参考未冻、issued≠effectiveMAC均保留。
- 不纳后继ChiselMain/emitter候选；旧脚本端点PASS/FAIL及canonical状态不改，整体任务不置done。

[复现源码、精确hash与验收边界](../candidates/qwen2_core_real_matrix_compile/README_ZH.md)
