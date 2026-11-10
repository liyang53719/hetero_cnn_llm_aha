# TEMP：Legacy FP32 storage / pipeline 接法修正

此前仅由 `bf16Weights=pipelined` 推断强制 BF16 存储不成立。原源码不需要存储解耦修改：该名字实际是 BF16 admission 能力开关，不是强制格式。

已验同一 original162 闭包；只改 emitter 的固定构造为 `HostBlockTopV4(shape, weightReadBeats=16, pipelined=true)`，保留默认 LegacyV0。shape 仍 retainedMatrix=true / matrixColumns=256。没有按 profile 重 elaboration；没有改 DUT、require 或 numerical policy。

## 原源码证据
- `HostBlockCommandsV4.scala:813-814`：nativeWeight 只在 dtype5 时生效；dtype7 始终被 validDTypes 接纳。1752 将 nativeWeight 写入 runtime job.weightBf16。
- `StreamingDense.scala:87-92`：runtime 格式选择每 beat 16 FP32 /32 BF16，地址按4/2字节步进。
- `StreamingDense.scala:250-274`：FP32 路径读取16个32-bit words，finite检查32-bit，再 TensorMath.bf16Rne；BF16路径直接取halves。activation亦按runtime dtype选择，不注入中间值。
- `Qwen2Block.scala:295-301`：原 Legacy Matrix 入口同样将 FP32 存储读值作 BF16 RNE，不是新增量化策略。
- `StreamingDense.scala:130-148`：按每context递增 K，clear仅K0，last仅K末；context交错不重排单context K顺序。
- `MatrixPipeline.scala:66`：8份 RetainedMatrixEndpoint，每份512 MAC，共4096。acceptedSteps注释中的512是计数粒度，不能据此把整体报512。

## 精确范围
这是源级路由/精度审计与原始顶层发射尝试。FP32 存储不是 FP32乘法器：原契约是FP32存储、BF16RNE Matrix ingress、FP32累加。静态顺序检查不是数值通过。独立 Python LegacyV0 完整参考缺失，真实 Host bench 尚未编译运行，五块完整128token回归0/5。统一runtime其余四profile admission及共享容量仍待完整证明。

实际结果：162源码编译 exit0，56.9925秒；真实CHIRRTL发射 exit0，13.4056秒。24个elaboration warnings未掩盖。IR仅本地留存，见SUMMARY哈希；未生成SV或运行bench。
