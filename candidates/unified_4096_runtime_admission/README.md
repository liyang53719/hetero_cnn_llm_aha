# 同一 4096 物理资源架构：第一批共享控制增量

本目录 **不是完整 block top，不是 4096 算术执行通过**。它实现了必要的共用 runtime admission，取代“每个模型一个 Scala 构造参数/不同 elaboration”的入口选择。现有已生成 full 8×512 RTL 仅作基线；五 profile 最终必须由一个新增完整 top、同端口、同 RTL hash 执行。

## 本批实际实现
- 一个无模型参数的 `UnifiedBlockAdmission`，五 profile 在同一次 DUT elaboration 中以 `profileId` 0..4 选择。
- 19 字段、179 bit 固定 descriptor；从三份官方固定 config 独立推导的五 profile 表逐项一致。Inactive operator 字段为 0；35B 的 GDN QK16 与 V32 独立。
- 固定 version/opcode、64-bit 地址、32-bit position/cache、16-bit 本次 tokens（1..128）；`+&` 后比较避免地址计数回绕。冷 attention 禁非空旧 cache。
- 完整 launch 与 profile 原子锁存；dispatch/result 在 ready=0 时保持；busy 不接受新 launch；完成须匹配 tag、profile 和本 reset epoch 内不回绕的 transactionId，且 drained。错误身份/未drained/后端 resetRequired 锁住直到 reset。
- `issuedSliceSteps` 只记录发射计数，不能换算 completed/useful MAC 或性能利用率。
- 小测试只注入后端完成用于验证控制，不冒真实 block 后端。框架 reset1 + 显式 reset2；全测试最多5000含框架时钟。

## 固定物理目标（本批没有按这些 max 分配 tensor SRAM）
Matrix 仅一套服务，8×512=4096 MAC、16×256 输出 tile、5 contexts；vector 沿一套16lane/scalar路径复用。最大 H2048、dense F8960、Attention Q16/KV2/D256、GDN K16/V32/D128、MoE E256/top8/expertF512。GDN 最大 FP32 state 2MiB、KV长cache、MoE expert权重均在DDR，按head/tile串流；不会把逻辑最大矩阵全展开到片上，也不复制五套kernel。

物理存储基线与新增需求分别记账：现有 Matrix 双16KiB结果tile buffer保持；现有 core 16×128×2240bit bank和score banks不能无证宣称已覆盖其他profile。共享block实现必须明确每个owner所需scratch tile/DDR搬运、仲裁、发布fence和带宽，不能用更大的Scala shape偷偷展开所有资源。

## 下一实际代码接线顺序（不是五个top并置）
1. 本 admission 成为同一个 Host front-end；统一 typed tensor descriptor/权重目录及版本化 operation≥8bit，不能把MoE16+截进旧kind4。
2. 同一个共享 owner dispatch 和 Matrix lease（唯一 `MatrixPipelineService`，原8×512）；Dense/Attention/GDN chunk/MoE expert time-multiplex这同一服务。保持FP32/BF16 materialization顺序，不为某模型改物理阵列。
3. 接已实际同DUT16/32测试过的固定32-head state-transfer owner：`activeHeads := profile.gdnValueHeads`，receipt head5bit。上层用锁存transaction/profile/generation fence绑定其私有stage receipt，叶子本身不自动完成root发布。
4. 修共享GDN prep：QK16/V32映射valueHead/2、AB参数多拍；conv8192通道运行有效范围；真实chunk64、M128两chunk。现M1 recurrent不能冒替代。
5. 统一Attention动态Q8/12/16、D128/256、rotary128/64、BF16/FP32边界；固定head index/count宽度和DDR cache寻址。RMS/elementwise共享16lane，H1024/1536/2048及F3584/8960运行有效范围。
6. 共享MoE路由/256专家地址表/top8与同Matrix逐expert dense，保持独立官方materialization/reference顺序；不能省略路由和最后reduce。
7. 五profile同时保留软件完整block参考测试；同一个最终RTL hash分别配置/权重运行， full128 / 数值 / MAC统计另作真实资格。当前尚未到达这些结论。

## 执行边界
原源准备阶段只完成源与纯 stdlib 对表；随后 r2 已实际完成独立编译门和单 DUT 控制测试门，详见 `ACTUAL_FACTS.json` 与 `evidence/ACTUAL_REVIEW_PROJECTION.json`。原 0648 编译 parser FAIL 保留；r2 仅将 11 个越界 Scala Int 字面量改为十进制字符串构造 BigInt，不改三份实现或算术。公开包不含私有 COMMANDS/运行准入；角色化复现见 `REPRODUCE.md`，compile/test 两门不能自动串跑。编译采用原106官方JAR/plugin，不带旧550/557模型classes，防止新类被旧模型shadow。root批准的预算：compile120CPU/150wall，test60CPU/90wall，1CPU/heap1GiB/AS4GiB/RSS2GiB；日志2MiB/新树64MiB。模型测试会生成该小控制模块FIRRTL IR，非Verilog/完整4096。

本次源不能检查完整DDR范围/overlap/typed张量版本、权重大小/内容、generation真实提交、真实后端drain与实际算术；它只是前述共享控制第一步。Reset epoch排除旧外部响应必须由系统恢复协议保证，transactionId不替代reset隔离。

## 本批验收边界
实际 PASS 仅 r2 类型检查及同一个控制 DUT 的五 profile 切换、13 个拒绝场景和 74 个独立边界向量。541 个显式 clocks；542 合计依赖框架 reset1 的源级记账假设，不是日志独立打印的总 clock 数。只动态测试了 wrong-profile completion poison；wrong transactionId/tag 单独错误、undrained、backend resetRequired 和 counter saturation 未测。资源与 cleanup 来自原收据及源绑定核验，不是独立历史连续采样或连续峰值证明。0719 reviewer 的原勘误与旧 parser FAIL 不回写。
