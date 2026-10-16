# 原 Public 共享父级 packed Attention（M1/M2 transport 实测通过）

- 已完成：冻结的原类 M1/M2 packed owner 和全启用单元 native profile2。
- 已完成：同一 PublicKvTransport、同一 Dense A banks 的 KV/scratch 仲裁和单父级边沿；实际物理地址/匹配 ACK。
- 已完成：独立代码审查、26项 normal/-O 冷测试（各1项 native 跳过），一次明确启用的 M1/M2 native 测试和4个故障用例，墙时1.393秒。实际输出/score与原始 AST/Fraction oracle 位精确；详见相邻 evidence 目录。
- 待完成：完整 Public 数值入口、真实 Q 输入片上寄存器/银行放置、硬件 mux/时序、M16/M128 及 RTL。

显式 PackedPublicProfile 默认关闭，只接受 M1/M2。原 OfficialAttentionOwner 类型、默认算法和 Public 精确类型/角色策略保留。原全链数值 source guard 不在此修改，也不继承历史 PASS。

ScratchMux 在已存在 ParentLoan 的单次 tick 前合并控制、后观察。KV 使用 0..4095，score/prob 使用独立 generation-valid 的4096..4191；共用原 Banks 和一个 raw response。scratch release 仅结束内部借用，物理 lease 直到原 supplier 终态清空后释放。owner 的 Matrix held result 与匹配 bank/DDR ACK 仍共同约束完成。

原 Q 地址走既有 DDR 请求；K/V miss 按原物理地址装入实际 A banks，hit 读相同 banks。96-word panel 是显式额外384 B模型资源。输入 packet/寄存器在硬件中的放置和端口调度尚未建立。没有新 SRAM 硬件或性能 PASS。
