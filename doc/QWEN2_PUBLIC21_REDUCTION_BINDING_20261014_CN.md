# Qwen2 public21 与归约控制器的当前源码绑定

## 结论与主线位置

独立候选现把真实 Command128/typed descriptor parser 的 Q/K/V 请求接到实际 `DenseBlockReductionCoordinator` 与 `DenseTileSumBridge`。普通 owner、驻留 FFN、Matrix window、Vector、tile 和 DDR drain 的服务返回仍由测试台控制。这关闭公开入口到归约调度的控制缺口；实际共享银行/owner 仲裁、算术、完整 block 数值与性能尚未关闭。

生产 `QwenOwnerKernel`、生产默认选择及原历史数值回执不变。候选固定读取 `8e0b2bbd35b3fee5ba2ca3e1f37e9274266b7689` 的源码，以及 `36dd2c473815a931e1f74463e9d43e538c11f2f6` 的公开 metadata 生成器/默认控制测试。当前执行 checkout 为 `700d756e13f25ee506a21616f617202543fe2b52`；全部被消费路径同时核固定 Git、执行 HEAD、工作树字节。HEAD 本身不作为语义等价证据。

## 源码与默认行为

- 76 个固定 postimage：70 Scala、6 SV；20 文件历史组合变更，9 处显式冲突解决均有固定记录。历史 patch/helper 保留来源，只将严格最终 patch 应用于固定字节，无 fuzz/offset。
- 两个后继 patch 各仅改变 `HostBlockCommands`：official-enabled Attention 全程序 typed-root 预检；尚无 owner 债务时在 issue 安全点处理 resetRequired。
- 编译闭包为 70 仓库 Scala + 20 逐 SHA 校验 HardFloat + 1 harness；另有 2 个测试类。fresh sbt project 禁止继承源目录，实际 `Compile / sources`、`Test / sources` 再核 91/2 精确集合。
- 原默认 19-owner profile 在同一组测试保留：M16、M128、高地址重定位 M16，每次 21 events、236 metadata reads、2769 控制拍；原六类错误拒绝仍过。
- 显式 official/resident 候选每次 17 accepted owner：13 ordinary、1 resident、3 QKV reduction；21 completion、650 metadata reads。原 default-off 不启用新 scan/fence。

## 实际控制事务

Q/K/V 同时检查角色 PC1/4/7、Dense、H1536、N1536/256、M16/128、BF16 weight、原始 FP32 A/D、writeBytes 和 materialization 字段。返回路由在 request.fire 锁存，不能用后续 pc 或可变 job 选择。

每档都有 28 个 partial window、14 个 drain、3 次 reduction 终态；Vector mock 返回 M16 为 2048 次、M128 为 16384 次。窗口是 K0–1024、K1024–1536，pair-high-first。所有 payload 为 mock zero，不承担数值验收。FFN gate/up/act 的真实 parser 合同逐字段检查，resident 服务返回仍 mock。

## 原失败与修复边界

第一轮候选实际读 443 条 metadata，与软件控制预检预期 650 不符，原失败保留。根因是软件 Attention admission 已有 whole-program typed virtual-root 扫描，原 Scala 仅有 FFN 扫描。现在复用同一 scan 状态，限定 score 的 QK-dst/Softmax-src 与 probability 的 Softmax-dst/PV-src，拒绝未来 pc20 的 alias。score/probability 已在 pc10/11 保留，Attention 不重复增加虚拟分配。拒绝发生在 Attention job 接受及其可见写之前；先前合法 pc0–9 已执行控制事务，不声称在整个 block 的第一个 owner 前拒绝。

新增三类控制缺口已通过实际 RTL 负门：

1. metadata fetch、typed 读取、whole-program scan、held ordinary issue、held resident issue 五处取消：已接受 metadata 事务继续自然退休，harness 同拍禁止所有新 owner 接受，最终 issue 发 Protocol 错误。不是固定延迟或即时取消承诺。
2. unexpected ordinary/reduction/resident 返回同拍封锁新准入，registered fault 保持 poison；不合成完成来消除旧债务。
3. residentActive 仅由真实 request/result.fire 建立/退休，拒绝无主 resident 返回。旧返回通路继续处理实际已接受债务。

原 window wrong-tag、short drain ACK、held-success reset、accepted-window abort 均保留。新测试还覆盖 reduction 运行期间 wrong-owner resident，以及 idle ordinary/resident stray 与 launch 同拍。最终共有 14 类候选拒绝标记；默认 profile 的六类负门另列。

## 验证与资源口径

- 本地硬化轮：2 tests、22 markers、0 skip，77.063756 秒，源码前后不变；输入/生成物已独立冻结。
- portable 第一轮：2 tests、22 markers、79.923281 秒，source/metadata/toolchain 前后不变；随后审核发现 timeout 组清理及失败 receipt 执行字段需加固。原通过记录与 runner 字节保留，最终入口另做 fresh 复验。
- 最终 portable：2 tests、22 markers、0 skip，83.308106 秒，全部 source/metadata/toolchain 前后不变；31 项冷门在干净 NumPy/PyYAML venv 的 normal/-O 各通过，14 项生成物一致性预检 normal/-O 各通过。固定 source manifest 为 `75caad6c8db95ba5470a5d97b6d691f96af17e0bfe58f2ca207693c92097864c`，新实际回执见 `reports/execution/QWEN2_PUBLIC21_REDUCTION_BINDING_20261014.json`。
- fresh fixtures 只有 10 份 command/descriptor/gate metadata，没有权重、激活或参考输出。两份 FIR 和两份 SV 从当前隔离项目保存、逐 hash 核对。
- 实际控制 DUT 只有 6 个 elaborated module 定义，无 Matrix/FPU 算术模块或 SRAM macro；bridge 保留 16×32-bit lhs 寄存器及控制状态。完整生产计算资源没有在本 harness 实例化，不能把此控制拍数当完整 block 周期、MAC 利用率或资源性能分母。
- enabled M16/重定位 M16 的 15755 拍、M128 的 87435 拍含人为 metadata/backend backpressure，只有协议测试含义；不与 2769 默认控制拍相除宣传加速。

## 复现与 CI

`python -m unittest discover -s candidates/qwen2_public21_binding -p 'test_*.py' -v`；另加 `-O`。

`python candidates/qwen2_public21_binding/run_control.py` 默认输出 `NOT_EXECUTED`。实际执行须先取得固定 8e0/36dd Git 对象、配置既有固定 Chisel 工具链，再显式使用 `--run-rtl --out <fresh-output> --toolchain-root <pinned-tools> --hardfloat-source <pinned-HardFloat>`。

新独立 workflow 覆盖完整消费依赖与本候选，保留 600 秒单次 RTL watchdog、25 分钟含工具准备预算、normal/-O 冷门、实际 2-suite RTL。只上传有限日志、summary、source receipt、4 份 RTL 和工具来源摘要。没有删除或排除既有受影响门，也不触发旧全 Host 长作业作为这个控制候选的替代证明。

下一步回到完整 block：在同一固定资源库存中接实际普通/驻留 owner、银行租约和真实算术，先最小公共 QKV 数值子链，再完整 M128 公开 21 命令执行。不能用这里的 17 个 mock terminal 关闭五 block、80% 阶段模型目标或最终完整实际 RTL 90% 联合门。
