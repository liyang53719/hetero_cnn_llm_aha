# MoE V2 事务接线 r2：编译通过；原15case整体CPU120 FAIL

本包只有9份共享Scala源码与小证据投影，不是完整35B block/4096硬件或数值通过。
原source审发现两真实协议漏洞：未知raw响应被下一请求重标，以及晚到release撤销
已held请求。r2增加稳定单entry offer和reset-only响应隔离，独立检查buffer/pending/
heldresponse/counters，普通poison仍允许当前真实排空。原BLOCKED不被覆盖。

9源产生24类，依赖175旧类，无shadow，源/JAR/类前后匹配。实际15项Chisel/Treadle
控制测试仅13项完成（7arbiter+3producer+2bridge+1接线）；CPU120.02触帽，native-9，
outer1，strictcleanup完整。两原漏洞的各自case确已成功。第二接线case进入但原日志
不含杀时phase/cycle/完成ops；其fixture拟576次mock返回，不代表已观察576。第三
边界case未观察。不能把两项未完成写成功能失败，也不能称整体15通过。

实际producer复用固定共享order controller：真实done、九贡献和exact1shared来源
绑定，不由host Bool生成drain。consumer/owner通过registered releaseAck收口；
未知raw响应隔离不伪退信用，缺真实drain需外部watchdog+隔离reset。当前owner身份
字典序仅临时资格限制，不是最终OOO/高利用率调度。所有原语数值响应均为测试mock，
13case不构成BF16数值资格。没有复制/缩小MAC阵列、模型专用ALU或新完整top。

14个低FIR只保留哈希/大小索引身份，审者未审其全部body；不是Verilog RTL仿真。
CPU/RSS为采样，wall为inner/postflight，不冒精确外层时长或child环境快照。环境依据
实际闭环境命令和拒绝式源绑定。原日志、类、IR、PID/机器路径均不上传。

REPRODUCTION是角色化命令/监督合同，不是新运行授权或已执行模板。依赖source
provenance与历史类hash分开；新重建须重新资格化，不混168+7之外全625类。
单scalar仅事务/故障资格壳，后继共享16lane吞吐路线完全不混本包。
