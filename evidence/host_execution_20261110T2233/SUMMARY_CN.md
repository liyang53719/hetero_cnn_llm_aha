# hetero 22:33：同硬件真实L3持续任务（INCOMPLETE，运行中）

## 持续性修复
先核main20872bc与上一轮CI success、原600秒任务已终态，未谎称恢复已丢失的Dense进程状态。旧首Norm精确PASS仍限L3 M128的128×1024 BF16首Norm，完整五块0/5。
实现一次从头的持续runner：60秒soft heartbeat及阶段真实actual文件hash不终止进程；固定6小时/20000000活动周期hard上限，fatal/协议错误/final保留终态。双独占锁与不可覆盖identity防重复；外层OS监督覆盖native exit/abort并清理遗留driver组。启动前全部依赖、输入和原终态pin验证；仅真实completed且文件完整时记录阶段actual，不注入参考。独立假runner控制测试通过soft后仍存活→final、native-like exit7无receipt、outer硬限三例；soft报告无step/clock/eval/kill/wait操作。不是可恢复checkpoint，未伪称只保存core即可恢复17native、driver DDR与AXI队列。

## 原身份运行
唯一实际L3 M128持续任务session48108，runner PID5/start7747398、driver PID6/start7747402，使用同compiled Host、17真实native及固定4096硬件。原Hostlib6609ada9、strict保护、输入/权重/精度/舍入不变，未重elaboration。尚无新完整数值结果，后续沿该身份观察，不重启前缀；每小时检查不会杀进程。

## 工作量与利用率层级
按原程序/真实调度核七Dense共2348810240 MAC，固定4096资源至少573440 issue cycles。实际M128窗口80+48导致权重读两遍，读写79822848B；当前串行64B供数driver至少1247232 bus cycles，因此仅这些Dense在该供数假设下理想有效MAC上界约46%。这是源码/driver供数下界与理想上界，不是RTL实测、完整block利用率或目标内存结论，绝非80%/90%达标。六小时是合理观测上限，不保证全块完成；后续仍需实测校准和真实依赖/缓存/供数改进。

## 其余块与保存
L0原完整输入桥已准备但未启动，原underflow FAIL不改；Qwen2首Norm串行链成本保留，未重复短跑；35B两块真实输入缺口和MoE同分契约不绕过。五块完整数值0/5，最终RTL未通过，32lane候选不能继承当前路径结果。
只发布允许摘要/hash；候选代码、权重、原始日志与运行文件本地保留。临时清单核验，无清理，运行引用与唯一证据未删除。

首60秒心跳已实证：79658帧、pc0/jobs1/completed0/DMA1725/resetRequired0，剩21540秒，soft报告后原任务继续运行。新任务尚未完成首Norm，未把旧PASS冒本次完成。
