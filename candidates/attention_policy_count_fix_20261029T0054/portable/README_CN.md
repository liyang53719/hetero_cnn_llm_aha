# 控制计数进位修复：便携微回归源码

本包只包含实际已通过的 Chisel 控制微测试源、来源核对器和依赖契约，不含 class、IR、SV、权重或输入数据。
生产源码唯一修复为 `countPolicy=attentionContextSlot+&1.U`；production 文件由同 checkpoint 的 SOURCE_OVERLAY 提供。本包不复制或改写旧 155-source 包。

## 范围
实际 Chisel/Treadle 曾执行 20,224 个案例（所有 256 opcode × 1 正常+78 单别名对），涵盖四 policy 互相别名、policy-tensor 别名、KV/softmax边界。生成低 FIR 已确认3位计数。这是逐字提取生产表达式的控制微测试，不是整个控制器接受路径或完整block数值证明。生产 policyGet 已提前拒绝重复索引，不能据此宣称原控制器可接受畸形命令。

## 复现
1. 定位固定生产 `HostBlockCommandsV4.scala`，其 SHA 必须为 `8cea5e8863e47ca14978871d23b7f80639e43ae3192c3e6c0ccf372b1c73a20f`。
2. `python3 -B reproduce_plan.py --production <fixed-source> --check-only` 核验实际微测试 source SHA 与连续8行生产表达式完全一致；`-O` 同样显式检查。
3. 按仓库 `candidates/fresh_original_top_recovery_20261028/SOURCE_AND_TOOLCHAIN_PINS.json` 下载精确依赖，保持其 Maven 相对目录；不接受系统随机Scala/Chisel版本。依赖manifest自己的SHA记录于DEPENDENCY_CONTRACT.json。
4. 使用显式 `--toolchain-pins <manifest> --jar-root <maven-root> --java <jdk21-java> --output <fresh-output>`（不加check-only）验证107个JAR并输出 compile/micro argv。脚本**只输出命令，不自动运行**。
5. 在已有受审资源监督器下建输出目录、执行compile（Xmx2g/RSS3GiB/300s），独立审核新class后执行micro。同一时刻最多一个heavy job，至少5GiB可用内存。成功日志应为 `PASS_CONTROL_EXPRESSION_ONLY cases=20224`；保存日志/hash和实际low FIR。

本包 plan 脚本仅做源级/依赖验证，不能用自身通过当成重跑结果。完整模型回归仍必须使用同一新共享4096 MAC硬件完成五块M128；之后冻结并最终RTL回放。旧16-lane或旧SV结果不迁移。
