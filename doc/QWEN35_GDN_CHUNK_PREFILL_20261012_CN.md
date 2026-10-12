# 0.8B L0：真实 chunk64、完整 typed 模型接线与数值阻断

当前实质增量是 true chunk64 软件计算、共享 Vector 的显式 IEEE 异常策略、gated norm/残差/SiLU×up、真实 FP32 prefix 恢复的两段 Down，以及同一物理内存/Matrix/Scalar/Vector 的16阶段完整 typed 协调器。协调器目前仅通过控制与真实 driver 准入小门，完整模型数值仍待执行。它不是公共 Command128 已接通，也不是 Chisel/RTL 仿真；这两个缺口不因软件模块齐全而关闭。

## 已执行的实际数据

前一提交 ada0a8a 的103小测试、两项CI和紧凑工件已核验闭环。实际 InputPrep M128 仍是两个独立 cold 输入窗口，不能当 cold→carried GDN。

本轮从前一实际 M16 Prep 的成功写回边界重放输入，在新实例执行全16头、每头完整128×128 FP32状态、padded64 chunk。174.48秒到达成功 staging terminal，32,768个BF16 core字和262,144个FP32 state字全部对独立固定算术逐bit一致。13,959,168B scratch、core及state全部真实64B写ACK；输出与state仍未公开，generation未推进。这是边界重放，前置RMS/投影/Conv没有在该实例重算。

官方相同实际Prep输入的完整16头chunk对照：core只有1个BF16 ULP差，state maxabs4.84288e-7。纯官方整层前缀对照则保留24个core位差、state maxabs0.0002851039。将原全块FP32 state门逐元素套用到这个实际冷M16状态，262,144元素中1个超限，最大容差比2.52094，必须保持FAIL，不能用固定算术PASS覆盖。

首个分歧在QKV投影：RMS和AB逐bit等于官方，QKV有142/98,304个BF16字差；原投影绝对门通过并不保证状态门通过。独立反事实只替换QKV为官方值，随后保持原固定Conv→Prep→chunk，状态门变为0个失败、最大容差比0.00446651。这只是因果诊断，不向actual owner注入参考，也不是完整实现通过。通用投影归约顺序仍需独立全形状验证和实际接线。全K1024的pair高半优先候选仍失败，已明确不采用；唯一同形状官方Linear重放逐bit一致，生成指令显示每batch K512及有/无旧partial Add的变体，但动态batch/调用次序尚未证明，不从kernel文件数量推断。

## 合法下溢与保留的失败

据M16实测预估，原M128尝试给600秒上限，却在0.153秒正常到达 Numerical 拒绝；没有耗尽预算或继续盲跑。head0/chunk0/row18/lane4的有限乘积 b7ae8141×07dd24d3→804b5f58 是正确的渐进subnormal，原Vector flags[4:1]把UF+inexact当fatal。原失败、实际源快照和全部产物hash保留，不能重标PASS。

新模式必须显式选择 ieee_rne_finite_gradual_underflow；默认仍为legacy_vector_fatal_underflow。它只改变有限UF/inexact的错误分类，保留原FP32结果和5位flags，invalid/div0/overflow、非有限、非RNE、FTZ/DAZ仍拒绝。batch仍先完整Mul再完整Add，分别舍入，不是FMA；失败Mul不启动Add。现有Chisel ElementwiseMemoryEngine仍按flags[4:1]拒绝，此显式模式的控制选择与物理共享Vector路由尚未接入，不宣称当前硬件具备该模式。

ExpNegative算法没有随此次策略改变。相同M128准备输入有70,688个exp请求，其中4,705个绝对值≥80，1,618个官方非零结果被原饱和归零，最大丢弃值1.77457e-35；非饱和区最大绝对误差1.25170e-6。它是局部原语诊断，尚不是完整输出/state误差上界。

## 完整模型的实际依赖与提交边界

16阶段按实际字节依次为 input RMS、QKV、Z、AB、Conv/SiLU、Prep、chunk、gated norm、O、第一残差、post RMS、gate、up、SiLU×up、Down、第二残差。所有源和参数在launch前初始化；所有中间目标有哨兵，只能消费前一真实写回。保留原BF16物化节点：gated norm先把归一化core舍入BF16，再乘原FP32权重（不加1）及FP32 SiLU；MLP则先把SiLU结果舍入BF16，再乘up并写BF16。

Down K3584复用原五个accumulator bank及共享Matrix，先真实计算K0..2559并把完整FP32 prefix写入私有DDR，全部ACK后真实seed读回同一资源，再继续K2560..3583，最后才BF16舍入。prefix容量524,288B；不由参考初始化、不重新分配阵列，也不当普通tensor公开。

Conv history和chunk state一直为独立staging。只有完整第二残差全ACK且成功terminal被接受的同一软件提交点，才同时更新双root和generation。carried只能读此实例此前实际成功提交的双root；失败/abort/reset保持旧root，排空已接受事务后才能复位。只读初始hidden可用于第一残差A端，其他残差/SwiGLU输入仍需要真实producer覆盖。新修复的坏tag/长度ACK保留Protocol错误，只按锁存物理请求失败退休，不计成功ACK、不留下无法排空的pending。

gated norm的软件流式staging时序与现有Chisel整head缓冲时序不同，因此这里只证明算术/所有权映射，不宣称逐事务轨迹与硬件相同。

## 资源和性能口径

宿主批处理把相邻Mul/Add合到一次C调用，头0由13.65秒降至10.72秒，但逻辑issue、lane运算、读写、ACK、software tick全部不变，硬件速度提升字段为空。

这条保精度映射M128需要21,238,784次16-lane Vector issue、70,688次exp、12,030,976次64B物理请求（769,982,464B），scratch26,869,760B。Dense有效MAC为128×21,528,576=2,755,657,728；即使Vector每拍一issue且其他工作完全重叠，全块固定4096 MAC/拍分母下乐观上界也只有2,755,657,728/(4096×21,238,784)=3.16763898%。这不是实测cycle或普遍架构极限，绑定当前软件映射；实际Vector延迟、仲裁、寄存器分配与DDR还没有硬件闭环。80%/90%目标未达到，不能将宿主加速记为利用率提升。

## 验收清单

- done：全16头M16真实chunk固定算术逐位符合；原M128异常拒绝和原state门FAIL完整保留；IEEE策略边界/旧模式回归；真实Down两段seed小闭包；pointwise错误排空与原始hidden准入；完整typed协调器控制与源封存小门。
- ongoing：QKV首差因果及通用顺序机制；完整M16与cold128→carried128的实际模型/官方逐节点与state门。
- to do：公开Command128完整M128生命周期与Chisel实现对应、精确刺激RTL重放、0.8B L3及35B-A3B L0/L3完整M128。

所有原门限保持；未来节点未执行就缺失，末输出通过不能代替整块。源码、小测试、原失败和紧凑证据见[本轮记录](../reports/execution/QWEN35_GDN_CHUNK_PREFILL_20261012/)。不提交权重、NPZ或tensor字节。

本地冷环境检查保留两次harness失败：首次导入GITHUB_ENV漏掉第三个证据目录变量，第二次git archive只有源而无Git元数据，导致故意读取HEAD固定Chisel源的准入失败。两次都没有修改数值实现或CI门；补与actions/checkout相同的精确HEAD元数据并复用已成功的同源构建后，完整轻门重新执行。旧失败不记为DUT数值失败。

最终冷源码完整workflow顺序小门为271项、20个独立进程全部通过，包含真实小C++共享Matrix与Vector算术及完整控制/负例；没有跳过，也没有下载权重或启动RTL。构建产物、源码和日志hash均封存。相关远端CI仍以新提交精确SHA为准。
