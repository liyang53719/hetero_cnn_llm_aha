# 原构建字节与云端执行适配：SOURCE-ONLY，数值仍 0/5

- 构建者保持 e01529eb9681fc08a2790d2cc8c17735c986610f、run 41257805047、artifact 13064009898；实际 ELF/SV/driver/四份清单原字节不重写，不重新构建。原 GCC dependency collector 的 80186b8c… 身份保留。
- 执行者使用独立真实 Git commit / SOURCE_PINS。外部可信 invocation 绑定 executor_adaptation、独立审核 receipt、实际构建 handoff、预算审批及 workspace_loader。完整 catalog 差异必须与精确 host-only 白名单一致；发布审核另核真实 Git 全差异。不同全源码绝不称同一 commit。
- 修复消费端 Make recipe 对两个 ASCII 空格的误拒：只接受原唯一 target、原 token 序列，不允许额外 flags、shell 或第二 recipe。实际构建元数据已验证旧拒／新完整依赖门通过，非重新编译或数值通过。
- 当前云主机系统 loader/库与 builder 字节不同，不能仅凭 x86_64/SONAME 放行。官方 Ubuntu 精确版本恢复的六库逐 SHA 与实际 builder inventory 一致，留在独立 workspace；不改系统 loader、安全设置或 LD_LIBRARY_PATH。
- 显式原 loader `--inhibit-cache --library-path <private-root>`；私有目录仅六个原文件与一个已知内部 SONAME alias，无 hwcaps 子目录。静态 DT_NEEDED 与真实受监督 `--list` 均须精确六库，所有实际 resolved path/hash 必须在该 closure；缺失/系统回退/漂移先拒。后续 dlopen 仍 NOT_QUALIFIED，不能由启动检查推断完整运行。
- 原 provider、70 权重、五份独立参考、M128 chunk、4096 MAC、固定硬件/driver/刺激/算术/验收完全不变。实际硬件含共享 32-lane bank；本 host-only 工作不新增或认证全链 II=1 或性能。
- trusted launcher 的 budget/review 是既有云测试授权下的工程证据门，不是要求用户重复授权清单。缺真实静态内存账单/当前资源/审批输入不得启动；保留旧 owner 5 GiB、非 DUT 1 GiB，以及已审诊断 DUT 2.5 GiB hard-AS / sampled group-RSS 和 consumer 512 MiB。无 cgroup 不称硬进程组内存隔离。
- 当前完整数值、五块 M128、最终 RTL 仍 0/5。300 秒窗口仅有界校准，FULL 预算尚无真实速率依据，不填猜测时限。资源不足/超时是 INCOMPLETE，不冒数值 FAIL 或 PASS。
- 七件包传递已获用户批准，不重复询问。不得上传权重、NPZ、参考数据或原始日志；官方恢复库不夹带扩大这七件上传范围。

磁盘首次准入复用原有界 census：已存在完整 watched roots 的去重逻辑字节 L 必须不超过原 TREE；仅预约最大未来新增 `TREE - L`，并保留额外 free 8 GiB。实际 loader 根亦计入 watch。原每阶段 free 8 GiB、aggregate TREE、文件/entry/增量门均不变；抽样不是未来峰值保证。


### 2026-11-01 导入故障恢复
原 5214a22 云端任务已完整生成五份 M128 软件参考后，因 numeric sibling 导入缺失终止；原硬件尚未执行。新 `retained_materials` 是经独立批准输入 pin 约束的纯字节/来源核验，不执行数学、不复用旧 owner lease。只允许原固定 70 权重和五参考，各原 supervisor / argv / 源码配置 / tensor hash 重新核验；新 runtime 当前身份验证仍必须完成。恢复记录原输入 provenance，不制造跳过阶段的新 native receipt。实际受控 import 用非 mock subprocess 回归，原冻结硬件/driver/ELF 不变。
