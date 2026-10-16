# 原 PublicKvTransport 的 packed M1/M2 实测

一次已审查、20秒子进程上限的实际 native 测试成功：1个测试，包含真实 M1、带背压 M2 和4个故障用例，总测试墙时1.393秒。使用既有合格 profile2 库，没有重新编译。这里只包含安全的哈希、计数和日志，不含张量。

M1/M2 使用准确原类 OfficialAttentionOwner、原 ProfiledMatrixService、PublicKvTransport、同一个实际 Dense ParentLoan/A Banks。整个分配期间 owner/parent 边沿分别为1768/1768和4857/4857。K/V 核心请求112/336，外部 miss32/64，hit80/272；Q仍为96/192次原物理地址读取。scratch请求48/96全部匹配 ACK。Matrix步骤98/198，最终 result/done14/28，全启用单元 FMA397312/798720。输出96/192个64B写包仅在匹配成功 DDR ACK 后提交；相关 Matrix 写债务108/216全部退休。

所有输出和全部 score 与字节固定的原始 owner AST/Fraction oracle 位精确。哈希也与前一原 owner 小测试相同。selected overflow、foreign DDR、output error、scratch abort 四例均清空已接受债务并以失败结束。故障收据保留失败/排空标志和父边沿数；未归档各故障的累计分类事件数，不能从成功用例推算。

执行 pins 是317595ead1d94c3c5cda0996ab7076f0f22c713aba3a216238084e18b0accac1，收据903053926f79f88c7adecae2b6e583903a64aba6ec893ead4dff963124a36042。166项执行源哈希通过事后检查。发布前仅更新 candidate README 完成状态和相应 pins；代码/测试与实际执行一致。

- 已完成：26项冷测试 normal/-O（各1个 native 跳过）、一次明确启用的实际 native 测试、源闭包/事后检查、独立代码与原始收据检查。
- 已完成：独立检查本安全证据文件，原始4文件逐字节核对和2+2证据测试通过（无跳过）。
- 待完成：真实 M16 原21操作 Public程序、完整独立门限和输入资产绑定；更大规模/RTL/物理输入寄存器调度。

原 Public 元数据整程序只支持 M16/M128，所以本次是其实际 transport/owner 的 M1/M2 测试，没有宣称执行完整21操作或获得完整模型 PASS。96-word panel仍显式计额外384 B；Q输入硬件放置待定。软件边沿和FMA计数不代表硬件周期或利用率。
