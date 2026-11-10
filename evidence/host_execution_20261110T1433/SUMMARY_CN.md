# hetero 14:33 检查点：启动链推进，完整数值 INCOMPLETE

- 原 session 36793：350.03 秒 exit 1，非超时。原 Host 构造、17 个真实 native 绑定及 reset 两周期成功；驱动输出目录被 runner 提前创建，真实驱动在刺激前拒绝。
- 修复输出所有权：驱动独占创建数据目录，runner 日志转独立 sibling metadata。真实 driver 轻测确认新目录进入完整193字节首帧，旧目录拒绝；不当 Host 数值通过。
- 针对性后继 session 12680：330.05 秒 exit 1，非超时。真实驱动 reset5周期、一次launch，active_cycles=1、pc=0、完成数0、AXI读写0，立即收到非 clean result；未进入 block 数值执行。
- 原源码审计定位：HostBlockCommandsV4 的 profile0 入口要求 officialBf16，而此次原默认 LegacyV0 构造不满足。不得擅自切数值策略、改变硬件开关或仅放松检查；继续审查原 FP32 Qwen2 完整路径与项目限制引入层。
- 新增独立 preflight：真实配置/readonly输入加载至首帧；旧输出/旧metadata、非法预算、坏driver hash、缺view全部拒绝。补只读结果字段失败诊断，不额外poke/eval/step，不替换原异常。
- 独立协议审计及实际Treadle UInt 1/8/32/64/512高位/最大值/零批量读回通过，只是接口资格。final帧不是数值成功，仍需子进程exit0及独立参考比较。
- 五块 M128 完整数值仍0/5，固定4096 MAC；没有完整block利用率实测，没有最终统一RTL数值PASS。原head4 underflow FAIL保留。35B官方权重访问阻塞未绕行。
- main 0c1eecaf4044b690b26c19c04a6737201418f592；CI 42834517712 success，仅payload guard。
- 原失败及新失败证据、临时文件全部保留，本检查未清理。当前无Host运行。此前拒绝的源码/原始日志不通过其他渠道上传；本文件仅最小事实摘要。
