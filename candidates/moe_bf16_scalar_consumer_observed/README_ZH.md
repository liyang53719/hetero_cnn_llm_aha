# MoE BF16 scalar consumer — 独立观测后继 5/5

同一 consumer/顺序控制/原 BlockScalarFloat 与 HardFloat 电路在 Treadle 中通过原五个小 case。只新增观测 Spec；没有改变 DUT、Golden、ready/valid 刺激、MAC 数或资源结构。首次 CPU120 失败包保留在 SOURCE_REFS 的固定 commit，本后继使用独立 CPU300 窗，不能反改旧 FAIL。

一份 numeric DUT 无 reset 顺序执行 9 贡献（专家升序、shared 最后）与 8 贡献：576 + 512 次实际 scalar 操作，全部实际 op/a/b、response flags/error 和最终 32 个 BF16 lane 与已固定官方 eager 合成数据一致。循环分别 2020/1796 cycles，不含任务装载/回包/完成 hold，不能作4096-MAC性能。结果初见核 identity/status，保持4周期后只再次核 data；不扩大为逐周期全字段稳定断言。

其余四 case 检查非规范 BF16 weight、原子 count admission、旧身份/重复/越界不耗合法 credit、真实 producer drained 失败收敛。64-cycle 无握手门只用于全部输入已缓冲的 Add/Mul 合成循环，不覆盖任意长延迟共享服务。

**范围仍未完成：35B L0/L3 fullblock、M128、专家矩阵/attention/GDN、同一完整4096硬件五profile接线；NaN/Inf/overflow 全合法BF16语义也未关闭。** consumer 自身不实例化ALU，最终共享 scalar 租约、父级取消隔离和 drain 仍须集成。

参考官方四个原方法体、绕可选 backend decorator 的范围和纯合成 fixture 来源均沿用固定旧包，不重复下载/重生或复制 Golden。SUMMARY 分清真实 native 收据与缺失的工具 session/raw outer terminal；不补造历史。源码与监督角色模板可复核，模板字节不是原执行字节。REPRODUCTION 不授予重新 native 运行或预算提升，须新空目录、外置固定 metadata 和另行运行批准。
