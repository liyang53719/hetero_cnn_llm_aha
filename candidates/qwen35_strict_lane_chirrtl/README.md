# 隔离 strict FP32 单 lane：CHIRRTL 前端增量

本包保留 9 份原字节源/差分/结构描述，仅记录已完成的一个 emitter 编译及一次单 lane 构造展开。生产 lane、HardFloat、旧 BF16 配置和原工具链不在本包重复复制。

实际前端输出包含 9 个模块、8 条父子边：一个 full32 Pre、原 Mul/Post/Round 各一个及必要 HardFloat 子层。真实 CHIRRTL 独立核得唯一变量 24×24 mul、27 个顶层端口叶、130/124-bit 请求/响应 payload、12 个顶层 reset 寄存器共 553 bit。它是硬件中间表示，不是 SystemVerilog、仿真或数值测试，也不证明综合后面积、频率或映射乘法器数。

45 组纯 parser 控制与两个自然退出的 JVM 终态分开记录于 SUMMARY.json。真实输入 390 项前后同身份/同哈希；55 个原 class 只读复用，新增 3 个 emitter class；所有 class/IR 二进制与原日志均不发布。

原监督为总 180 秒、共享绝对 work 150 秒、compile 最多 120 秒、elaboration 最多 30 秒、cleanup 5 秒及 post 25 秒；单 CPU、每进程 AS 4 GiB、后代 RSS 2 GiB 和 owned 16 MiB 均按原定义，其中 aggregate 是采样门，不是瞬时物理上界。

## 复现边界

原入口是 CPython 3.12.14 的 `python -I -S -B launch_chirrtl.py`。这是源码摘录，不是可直接运行闭包：入口仍严格要求精确 FROZEN_PLAN.json，该机器相关计划不在公开包中；REPRODUCTION_PINS.json 仅提供相对角色和内容指纹，不重写路径或绕过校验。不得仅根据此包启动新 JVM 或扩大为阵列执行。parser_controls.py 的人工 IR fixture 也不是生成硬件。

## 保留的集成阻断

0x00800000 × 0x3f7fffff 的交付结果均为 0x00800000，但原 HardFloat 的源规范 flags 为 UF|NX=3，旧 CPP 按交付值修正会给 NX=1。这里没有执行硬件 flags，该差异仍阻断未来模型/硬件的数值契约整合；软件参考和本次前端 PASS 都不能解除。BF16 raw 模式不等于 strict 有限域，旧 BF16 源未修改。没有真实握手、16 lane、阵列、完整模型或 80% 利用率资格。
