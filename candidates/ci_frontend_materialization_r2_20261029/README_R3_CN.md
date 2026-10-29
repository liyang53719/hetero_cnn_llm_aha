# TEMP / INCOMPLETE：R3 精确采用已观测的公共 JDK 外链

R2 run40816952149已明确记录 JDK_UNKNOWN_EXTERNAL_ALIAS：lib/security/cacerts实际解析到/etc/ssl/certs/adoptium/cacerts，134280B；当时只准/java/cacerts，因此在未读取未知目标内容前失败关闭。原首run40814080857的childstderr缺失，历史根因仍UNKNOWN，不能追认。

本R3只把inventory、binder、safe summary三处精确公共路径从/etc/ssl/certs/java/cacerts替换为/etc/ssl/certs/adoptium/cacerts；不允许两者集合，不扩大任意外链。不改变regular 0..4MiB上限、目标hash冻结、全alias pre/post复核或未知alias结构化失败规则。仅只读/hash系统预装公共信任库，不修改证书、信任、安全设置或网络权限。实际内容SHA须由新job观测，134280B样例测试不等于真实文件内容验证。

R2目录仅这三个生产文件做普通Git更新，旧cb237e6源码和失败证据可由历史恢复；README_CN.md保留的是R2设计历史，本README_R3_CN.md为新路径纠正。其余原硬件、fixed4096/Vector32、source R2 manifest、canonical/SV检查、资源限制与frontend-only范围均不变。No weights、C++ build、DUT数值回归；完整五块Chisel/最终RTL仍0/5。

新增workflow hetero-fresh-fixed-frontend-r3.yml只对ci_launch/fixed_frontend_r3_20261029_once.json触发。先经审发布源码，不含launch；后另批准一个直接父指向源码SHA的新增launch文件，schema=FRONTEND_R3_ONE_SHOT_V1、profile=FIXED4096_VECTOR32_FRONTEND_ONLY、nonce=fixed_frontend_r3_20261029_once。仍核实际git单A/parent/event/attempt1并checkout精确source。标准ubuntu24单350min上限，exclusive组，无自动重试，不重跑旧job。
