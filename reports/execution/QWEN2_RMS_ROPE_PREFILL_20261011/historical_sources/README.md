# 首次 M16 比较布局错误的源码快照

这两份源码从未发布为独立 Git commit，故保留当时原始字节供失败回执复核。它们不是当前生产脚本或测试入口，不授予当前文件旧 PASS。实际 C++ 算术与修正后相同；差异在 cold 参考 Q/K 的 token-major 逆变换。

- candidate SHA256: 818325c08e80e4b1167334ebe24a774238606614ca87eb3d5c83b8216e90bca4
- test SHA256: ad6221f564df8591fd60952898e6d53be2638acb148941281ebb1ca403f33893
- base commit: a17ebcc91cd3ffdd38e42743aa3264ea25d75f0c

原失败与修正后数值比较分别保全；不包含权重、张量或ELF。
