# Qwen2 Core：M3 source + single-TU build

- **PASS：** 固定 M3 源码/独立标量 RNE/小合成门；一次单 TU 实际编译链接与静态 16 产物闭包。
- **本批不覆盖：** M3 run。1728/576/1260 只是编入的静态表，不是实际事件；不证明跨 16-key、通用数据 alias 排除、完整 FMA/128 RTL/full29/90% MAC。
- 新 46 cache/source 端点门不回填旧 Python 覆盖缺口；M1/M2 限定 PASS、所有历史 FAIL/STOP 和 canonical 状态保持，整体任务不置 done。

[最小差异、复现源码与范围](../candidates/qwen2_core_client_m3_build/README_ZH.md)
