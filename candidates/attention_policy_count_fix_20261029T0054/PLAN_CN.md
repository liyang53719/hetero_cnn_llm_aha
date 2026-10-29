# 2026-10-29 01:46 UTC：控制保进位修复与五块 M128 检查点

状态：**INCOMPLETE：原始 Chisel 完整 block 数值 0/5，最终冻结同刺激 RTL 数值 0/5。**
独立官方 Python 参考五块完整 128 token 输出及最终 cache 5/5，不是硬件通过。

## done（精确范围）
- 原 main b612426636f469a7f10142d343574d2c4f2053f9 已复核，原自然 CI 40790290264 / job123173546795 success；它仅为 Git payload guard，不是硬件数值 CI。
- 70 个原生权重张量共 3,531,306,272 B 恢复及完整 SHA/语义绑定核验，12/14/11/18/15 对应五块；完整 256 专家权重。已发布 acquisition pins 不重复上传数据。
- P0 Qwen2-1.5B L0、P1/P2 Qwen3.5-0.8B L0/L3、P3/P4 Qwen3.5-35B-A3B L0/L3：官方独立 Python full128 baseline/observer 输出与最终状态一致；完整摘要见 SOURCE_ONLY_REVIEW_5_OF_5_FINAL.json。P0 保留 FP32 存储接口，原生 B 权重 BF16，不擅改精度。
- 五块 byte provider 已构建；P3/P4 原 C++ loader 2480/2458 条记录、159723/158554 B 纯字节 probe 及拒绝测试通过。不是 DUT 数值通过，probe 数据不提交。
- 唯一生产修改 HostBlockCommandsV4.scala：attentionContextSlot+1.U 改 +&1.U；Matrix 3+1 原2位截断0，现3位4。实际 Chisel/Treadle 控制表达式测试 20,224 案例通过，非完整控制器/完整数值测试。
- 上游 policyGet 已有 prefixRevisit/policyRevisit 拒绝重复；本次补冗余校验防线，**没有证明原整控制器接受畸形别名，也没有证明输出数值错误**。
- 原始完整 fixed high / official low 发射通过，唯一生产模块变化；source overlay 154 个已有不可变 Git blob + 1 新源。4096 Matrix MAC、32共享 Vector/Element候选、容量/85端口/launch844不变。
- 新仿真后端 SV 实际生成 native0，404.43秒，RSS4414930944 B，SHA c7e9d25c128004bdfc90405171eead8a4441ba20e52e829d95de4bf1122e5d96。92定义仅 HostBlockCommandsV4 变化，91不变；Down/Matrix递归 SV 闭包字节相同。此为 Chisel 数值 backend 发射，不是先于模型通过的最终 RTL 数值回放/通过。旧 C++复用还须物理provider/tool/flags/wrapper契约核对。

## ongoing / TEMP
- 同一固定4096硬件的真实数值 backend 构建。此前整 Host codegen 受6/7GiB RSS限制，原生 Down C++ 出现约101MB单函数；保留失败，未以缩MAC或软件DPI替硬件。分区及 compiler split优化需真实整设计验证。
- V3 final-state/router witness driver仅源码及11项轻测试；尚未native编译、DUT执行。新增真实 BF16 router logits64KiB 最终DDR回读，FP32选择分数仍不在DDR witness中，不夸大覆盖。V3明确更正V2的35B静态辅助源码误指dense模块，现pin实际moe模块，布局结论不变。
- 标准16GB CI 单作业候选仍未operational，workflow未启用、未dispatch。可移植工具/依赖/磁盘峰值及同一binary五块链尚待闭合，不以微测试冒全链。

## todo / 必要决定
1. 完成固定新硬件 backend 编译，同一binary推进五块完整128数值；资源不足限制同时作业，不缩硬件、不将循环M1冒chunk。
2. 保留每步FP32顺序/BF16舍入、真实调度缓存，定位真实中间值与完整最终状态；Python/Chisel/RTL严格分层。
3. 五块模型全部通过后才冻结同份源码、输入、参考、配置，再生成同份最终RTL并同刺激回放。
4. MoE 同分小专家ID参考契约仍待用户明确；原Torch topk不改，不注入专家ID。P3/P4 18/8 token cutoff同分，假设小ID规则时10/4 selected set不同，**仅理论策略诊断，非DUT差异**。
5. 第二档1024或1224未定，不阻塞128。
6. 有效MAC目标至少80%、争取90%以上，分母固定4096资源与完整block周期；目前无完整block RTL周期/利用率实测，不报告达标。理想AXI功能供数不可当目标内存实测。

本次无清理：运行中/被引用/唯一失败证据保留；仅提交源码、pin、hash、摘要，无权重/NPZ/probehex/生成SV/IR/classes/binaries。旧证明包不覆盖，不继承遗失或旧16-lane PASS。仅 hetero，不操作 Voyager/Catapult。
