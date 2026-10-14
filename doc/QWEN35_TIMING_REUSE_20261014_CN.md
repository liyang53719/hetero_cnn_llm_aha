# 固定资源时序与 4-row 数据复用候选（2026-10-14）

## 当前优先级与边界

用户要求在模型阶段定位低 MAC 利用率并落实流水、数据复用。固定 Matrix4096 / Vector16 / Scalar1 不变。当前实际 35B L0 链仅到 post-attention RMSNorm，MoE、最终残差及完整 state commit 尚未完成。完整 block 周期、MAC 利用率、busy 占空比仍不可给出；以下是局部实测和保持现映射的条件资源界，不是完整 block 性能通过。

## 已冻结 M128 的瓶颈计数

`candidates/shared_resource_timing/analyze_prefix.py` 重新读取指定 SHA 的原13阶段成功终态，绑定生产 Scalar、Matrix、iDMA 源码，拒绝缺阶段、错误终态、M16填充口径混用。

- Matrix 实际 useful/executed FMA 均 4,311,744,512；固定4096对应理想满阵列 issue 槽 1,052,672。
- 当前各阶段总 DDR 读1,577,861,632B、写71,925,760B；单512bit payload 服务即使没有任何控制或DDR延迟，也需至少25,777,928拍。
- Scalar 外部请求25,679,680次，其中 Add/Mul/op6基本请求22,350,336次。保持当前单请求 idle→normal→done wrapper，单个连续ready请求 E0接受、E1算术、E2结果接受、E3下次可接受；N个基本请求的首接受到末结果接受含边界最小span为3N−1=67,051,007拍。
- 因此保持现资源分派时，仅DDR payload和仅Scalar基本请求分别给当前prefix Matrix useful利用率条件上界4.0836%与1.5700%。不包含Div/Sqrt/Exp、新opcode、Vector、DRAM时序、descriptor等开销。改变资源分派或流量后必须重算。
- 原typed ticks合54,486,336，比仅基本Scalar服务界还低，不能换名为硬件clock。
- Chunk实际读1,483,079,680B，scratch重复读1,476,526,080B；Vector Add/Mul请求42,526,720次。不得把这些向量工作计作Matrix FMA。
- Matrix212个K1024组中200个用5contexts，6个用1、2个用3、4个用4。单靠context反馈的最少额外issue空槽32,736，约accepted steps的3.11%；不能解释上述主要非Matrix服务需求。

## 已实现并实际局部重放的数据复用

文件：`chunk/matmul_reuse.py`、`replay_matmul_reuse.py`、`test_matmul_reuse.py`。

原 `_matmul` 对每个输出row×16列重新读取整个B归约列。候选按4row×16列复用B：每输出仍按K升序执行分离FP32 Mul再Add，保留原RNE/异常策略和最后factor乘，不改为FMA或归约树。

显式 scratch 为256个32bit字，共1024B：
- A缓存：4×16，偏移0..63，256B；每个K16块读取一次，两个K8半块复用。
- B缓存：8×16，偏移64..191，512B；一个K8块给4行共同使用。
- 累加：4×16，偏移192..255，256B；每个输出tile从+0开始，跨K块保留。

缓存边界、尾行1/4/5/8、租约互斥、读错误释放、写挂起期间租约保持均有局部门。仅关闭局部generator不等于生产写事务已排空；完整transport错误drain接线仍待验，不能据此允许物理缓冲提前复用。

M16/M128两档分别抽取原冻结SSA的head0和head31（M128末head用chunk1），每个head取ut、predict、state_update，共每档6case。原kernel重算、新kernel重算和原实际SSA destination三者逐bit一致。参考只在计算后比较，没有填充计算输出。

实际局部read请求统计：
- ut：B 2,097,152→524,288B；A131,072B、factor16,384B、写/ACK16,384B不变。
- predict：B4,194,304→1,048,576B；A262,144B、写/ACK32,768B不变。
- state_update：B4,194,304→1,048,576B；A262,144B、写/ACK65,536B不变。
- Vector算术调用数不变、scratch高水位1024B；B子阶段读降4倍不能写成全chunk或全block快4倍。

当前只是独立局部算法/流量候选，尚未替换ChunkOwner的默认路径。原转置局部tile同为1KiB，但全owner所有跨yield局部值驻留尚未证明；正式复用该空间前仍需显式生命周期互斥、物理映射和完整drain验收。没有增加Matrix/Vector实例，也没有宣称全owner存储上界已经证明。

## 时序模型的实际实现范围

统一phase/resource事件账本及有限生产Scalar FSM已实现，36项独立测试通过。支持显式资源容量/冲突、Matrix context返回与同拍重发检查、DDR末ACK、完整phase窗口与互斥等待分类；Matrix/DDR只校验调用者明确提供的条件事件，尚无完整35B实际事件接线。三次Scalar原语示例在ready-low E2..E7下，接受E0/E8/E11、ACK E7/E10/E13，窗口14槽分解为issue3+compute3+retire3+held5。这个source-FSM样例不是实际prefix时间测量。必须采用一个显式全局时钟、真实issue/return/ACK事件、互斥wall等待分类；现有typed transport ticks不能直接输入为硬件时间。

已有可绑定来源：Matrix五级pipeline/5contexts/8tags/2-entry结果FIFO，Scalar基础FSM，单outstanding iDMA/512bit服务。新35B IEEE exp/Softplus、通用Vector IEEE Mul、DDR物理时延仍无完整生产映射，禁止填默认延迟来凑利用率。

## 清单

- done：冻结M128资源/DDR计数再核、条件界脚本及3项门；两档各6case真实SSA局部位值和请求计数；4项复用局部门。
- done：统一时间事件模型36项、整体冷门721项/75套/218源，全部零skip且源冻结一致；局部raw与时序模型独审通过限定范围。
- ongoing：小批发布及原CI工件闭环。
- todo：候选scratch全owner生命周期/错误drain集成；相同冻结输入实际ChunkOwner opt-in复验；固定资源下Scalar/Vector分派及预取/计算/排空重叠。原Dense已有K16双缓冲不算新优化。
- deferred：router真实gate获取/独立N256校准。官方网络尝试未完成，无权重/manifest，不继承下载成功；本批不混入router离线候选。
