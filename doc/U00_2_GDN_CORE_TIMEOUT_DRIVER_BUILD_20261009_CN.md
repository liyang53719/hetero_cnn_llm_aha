# GDN core 超时与驱动构建修正

精确提交 `d7ce9bd74a929037e459b3300134bd9f1722916e` 的原 core 作业
`37900097873 / 113737768573` 于 2026-10-09 10:33:42 UTC 达到原 7200 秒
DUT 预算。GitHub 作业失败，数值验收状态为 `PENDING_INCOMPLETE`，不是已观测到
数值不匹配。完整 block 原作业 `37900097687 / 113731529569` 在本记录写入时
仍执行原 18000 秒预算，没有取消或重启。

已独立校验 compact ZIP、481 个源码哈希、62 项输入身份与原构建包/ELF/RTL
绑定。可得的 DUT 日志仅为 4096 字符尾段：第二个 carried token 的 pc5
recurrent 仍有成功写 ACK，末条完整 ACK 为 cycle 13,708,458、head10/row32/
column96（均零起）、64 字节全 mask、error0。原驱动只有在第一个 cold token
八命令、fence 和全部物理 DDR 比较完成后才进入 run1；这是支持 cold 已走完
驱动检查的控制流推断。完整 Python 审计、最终 DUT 身份验证仍未完成，不能
升级为完整 core PASS。参考阶段的 RSS 589744 KiB 不是 DUT 资源峰值。

实际编译 argv 显示，生成模型已有效使用 `-O2`；用户 C++ 驱动末尾的
`OPT_FAST=-O0` 则覆盖了前面的 `-O2`。因此本次只将 GDN 构建入口的
`OPT_FAST` 改为 `-O2`，保留 `OPT_SLOW=-O0`、`-ffp-contract=off` 和
`-fno-fast-math`。这项修正不修改 RTL 算术、资源数量、输入、数值门限或预算。
下一次构建产生的新 ELF 必须使用新的源码/构建身份重新验证，不能重绑旧证据。

参数回归用 GNU make 检查 user-driver 与 generated-model 两种实际参数顺序，
包括继承旧优化选项的情况；普通与 `python -O` 各 3 tests、9 subtests 通过。
尚未测量新驱动的耗时或增量编译资源，也未声称此修改足以解决超时。下一实际
CI 继续用原预算执行完整 cold＋carried 数值门，结果决定后续处理。

证据摘要位于 `reports/execution/U00_2_GDN_SIM_DRIVER_O2_20261009/`。
U00.2 继续进行，U01、完整 block、M128 和原 native 精度门禁未因本次超时或
构建参数回归而关闭。
