# 五块实际 DUT 执行/最终状态比对入口 — INCOMPLETE

本目录是已有真实 external-AXI driver 的执行/比对集成，不是新模型、资格外壳或软件算术替身。没有执行 DUT、编译或完整数值 PASS。所有五块必须使用同一份已构建 binary、SV、源码清单、driver 和 build receipt。Python 参考保持原 Torch topk；同分 small-ID 规则尚未获用户同意。**严格逐字节比较仅作诊断；即使全部相同也不自动声明完整 block/RTL PASS**。没有添加容差。

## 参数化执行

```sh
python run_compare.py --binding /ABS/FIVE_PROFILE_BINDING.json --output /ABS/NEW_RESULT --validate-only
python run_compare.py --binding /ABS/FIVE_PROFILE_BINDING.json --output /ABS/NEW_RESULT
```

`--validate-only` 校验输入/参考/pin、构造纯字节布局参考，不执行硬件。实际执行每块一次原 Host launch，五块均被纳入本次运行，不因前块数值不匹配跳过后块；资源许可下单进程串行，绝不缩减 4096 MAC。此脚本只用于 Chisel 发射 IR/SV 的数值 backend，不是最终冻结 RTL 回放。

所有 pin 格式：`{"path":"/absolute/regular/file","bytes":123,"sha256":"64hex"}`。相同内容迁移后允许不同绝对路径，需重建 manifest 及重新审核绑定，不依赖工作区固定路径。

binding 结构：

```json
{
  "schema":"FIVE_PROFILE_EXTERNAL_DUT_V1",
  "layer":"CHISEL_EMITTED_SV_NUMERICAL_BACKEND",
  "matrix_macs":4096,"vector_lanes":32,
  "moe_reference_contract":"ORIGINAL_TORCH_TOPK_PENDING_SMALL_ID_ACCEPTANCE",
  "common":{
    "binary":{"path":"/ABS/actual-driver-binary","bytes":0,"sha256":"REQUIRED"},
    "sv":{"path":"/ABS/HostBlockTopV4.sv","bytes":0,"sha256":"REQUIRED"},
    "source_manifest":{"path":"/ABS/source-manifest.json","bytes":0,"sha256":"REQUIRED"},
    "driver":{"path":"/ABS/host_axi_driver_non_dpi_final_dump.cpp","bytes":0,"sha256":"REQUIRED"},
    "build_receipt":{"path":"/ABS/build-receipt.json","bytes":0,"sha256":"REQUIRED"}
  },
  "profiles":[
    {"id":0,"runtime":{},"views":{},"reference_result":{},"provider_receipt":{}},
    {"id":1,"runtime":{},"views":{},"reference_result":{},"provider_receipt":{}},
    {"id":2,"runtime":{},"views":{},"reference_result":{},"provider_receipt":{}},
    {"id":3,"runtime":{},"views":{},"reference_result":{},"provider_receipt":{}},
    {"id":4,"runtime":{},"views":{},"reference_result":{},"provider_receipt":{}}
  ],
  "limits":{"address_space_bytes":12884901888,"cpu_seconds":18000,"wall_seconds":20000,"file_bytes":67108864,"max_active_cycles":1000000000}
}
```

空 pin 必须填充**实际已审核产物**；示例不能运行。build receipt 必须由实际编译步骤产生，字段 `config_only:false`、`software_arithmetic_substitution:false`，以及 `binary_sha256 / sv_sha256 / source_manifest_sha256 / driver_sha256`；不得凭想象填产物 hash。receipt 与二进制之间的编译因果仍需既有构建日志/recipe审核，JSON 不是自动证明工具。

原 runtime.tsv 中 `views` 必须精确指向 pin 中的 views.tsv。views 的所有实际源文件由原 C++ loader 按同一 mmap 文件大小和 SHA256 校验；runner 禁止 `reference_only` 路径入刺激。provider receipt 审核必须保留原全权重、commands/descriptors、input_only 绑定，无官方专家 ID 或输出预加载。

原始输入来源：P0 `p0_cpp_transport_20261028T2330`；P1/P2 `p1_p2_provider_reconstruction_20261028T2322/actual/profile{1,2}`；P3/P4 `p3_p4_provider_reconstruction_20261028T2344/actual/profile{3,4}`。移到 CI 时调用原 provider 的参数化生成入口，不复制本机绝对 paths。
参考 RESULT 来源：`full_block_P0_cache_20261028T2313/reference`、`full_block_P{1,2}_20261028T2307/reference`、`full_block_P{3,4}_20261028T2340/reference`。所有 tensor bytes 从各自 RESULT 的路径/shape/dtype/hash 校验。

## 最小 driver-only 变动

原 driver 在各 command completion 后导出 `.actual.bin`，读取必须经过 SparseWrites 的全字节已初始化检查。新增最终观察仅在完整结果被消费且总线持续 quiet 后，读取外部存储相同 span 导出 `.final.bin`：y/output、cache/cache_k/cache_v、history_out、state_out。全字节 ACK 可见性再次检查，并记录地址、dtype、长度。没有新增请求、算术、内部信号 poke、金值读取或硬件改动。**需以新 driver identity 重新编译，尚未编译/执行验证**。

## 物理布局审计（见 LAYOUT_SOURCE_PINS.json）

* P0：Qwen2Block `ropeIndex=token*ropeWidth+head*headDim+col`，KvAppend 通过原 ElemOp.Copy，按 `owner.m*owner.n*4` 将 K/V 写连续两段。外部 cache_k/cache_v 为 `[token,kvHead,dim]` FP32；官方 `[1,head,token,dim]` BF16 仅作字节重排及两低字节零扩展，不进行浮点运算。
* P2/P4：Bf16KvAppendRuntimeOwnerV13 `planeOffset=capacityTokens<<10`、`appendOffset=appendStart<<10`、inputAddress 连续拷贝；固定本次 capacity=128。cache `[2,128,2,256]` BF16，参考两 `[1,2,128,256]` 转 token-major 后拼接。入口要求精确 262144 B 观察，其他容量拒绝，不能冒充已覆盖未写尾部。
* P1/P3：GdnRuntimeConv4OwnerRecoveredV7 `historyOffset=group<<3 + beat<<6`，history `Vec(32,Vec(4,UInt16))`，每 token 左移3旧 tap再存 raw；最终 `[channels,4]`，四 tap 均比较。
* GDN state：GdnRuntimeChunkExecuteOwnerV8 phase14 `ket @ vnew` 得 `[key=128,value=128]`，phase16逐元素写 next_state，`(row*cols+(colBeat<<4))*4`。GdnChunkStateTransferOwner 按 `head*PerHeadStateBytes` 和连续 beat 原样拷到 stateOut。独立官方两版 `recurrent_state_shape=(batch,num_v_heads,k_head_dim,v_head_dim)` 与 `key.transpose(-1,-2) @ v_new` 一致：**直接 `[head,key,value]` FP32，不转置正方128×128状态**。

## 本轮验证范围与缺口

6 个 Python 轻量测试，普通和 `-O` 均通过：非正方缓存布局、BF16位扩展、尺寸拒绝、首差及差数、缺字节、正负零不容差。五个真实 RESULT 的最终参考 shape/hash/bytes 已读取校验，仅参考布局构建。没有使用 Torch/NumPy 或重新执行参考。

尚缺真实 common DUT binary/build receipt；driver 新尾部未编译；尚无 actual `.final.bin`，因此 Chisel 完整数值仍0/5、最终RTL仍0/5。原始数值验收契约/容差尚未核准，本入口输出永远 INCOMPLETE + bitwise diagnostics，退出2，不能让 CI 误转绿。资源/吞吐只来自实际 DUT 日志；该外部内存服务不是目标 LPDDR 性能模型。不得上传 raw weights/参考二进制/actual.bin，只能白名单摘要/hash/scripts。

## V2 2026-10-29 01:24：真实动态 MoE 路由与进程清理

V1 保留不覆盖。本版新增最终外部DDR route map读取，profile3/4各8192B。源证据：HostRuntimeMoePhaseAllocatorV5 `region=c.host.regions(3);base=region.base`，Metadata=0，held.metadataBase=base+Metadata；UnifiedMoeRouteGroupV2.pack 定义 Reserved23|token7|rank3|expert8|weightBF16|groupRow7，token-major槽index，写后收到真实response才递增index。最终output完成前原专家循环和merge消费该map。只有原 scratch 的实际已ACK字节允许导出，没写满直接失败。

比较原参考 `stage.mlp.gate.0.2` int64[128,8]与`stage.mlp.gate.0.1` BF16[128,8]，检查每个token/rank、专家无重复、保留位零、按专家计数groupRow。任何同分导致的ID/weight差异仍报告，不豁免。**该map保存归一化后BF16权重，不保存原始FP32 selection score**；raw-score观测标为INCOMPLETE。

完整raw-score只读witness方案（未实现，不猜generated成员名）：待新硬件header生成，审阅真实hierarchy/成员宽度和sourcehash；采样 UnifiedMoeRouterNumericalOwnerV2 的 `io.selection.out.valid && ready` 边沿、`arithmeticToken`、`out.bits.rank/index/score`，每token8个、总1024个；另采`io.route.valid&&ready` token/rank/expert/weight，和DDR最终map交叉关联。仅读取现有信号，不force、不poke、不加硬件逻辑、不馈参考ID。若生成器优化不可见，继续INCOMPLETE，不能用参考重算代替DUTscore。witness必须在同一时钟采样相位审核后再使用。

执行器改为waitid(WNOWAIT)保留leader作PGID锚点，清理原进程组后才reap，消除p.wait后killpg的PID复用窗口。此处不保证清除主动逃离原session的任意后代，外层仍需既有strict/cgroup/subreaper supervisor。11项轻量测试普通及-O通过，含1024route正确/错误/缺失、原ID差异不豁免、/bin/true进程清理；不是DUT运行。

## V3 01:48：保留真实 Router Dense logits，不混淆 FP32 softmax score

实际新增 `router_logits_bf16.final.bin` = region3.base+65536 起 **65536 B**，BF16 `[128,256]`；直接与原参考`stage.mlp.gate.0.0`逐字节比较，无浮点运算或参考馈入。不能按FP32读取128KiB：后64KiB已经是Gather区。`UnifiedMoeRouterDenseV2` j.outputBf16=true、writeBytes=m*512；`UnifiedMoeRouterLogitReaderV2` 每token读8个64B beat后才内部扩展FP32/softmax。故这关闭的是Dense logits观测，不是原FP32 top-k probability score观测；后者仍INCOMPLETE。

### 本次固定程序的生命周期依据（仅source证据）

1. allocator定义非重叠6MiB phase arena：metadata[0,16KiB)、descriptors[16,32KiB)、router[64,128KiB)、gather[128,640KiB)、gate/up/activation、routedDown/sharedDown/merged各独立。runtime lease geometry再次检查所有区域不相交。
2. Router Dense唯一dst是routerLogits；LogitReader只读。RouteGroup仅写metadata两8KiB map。Gather写gatheredInput；routed/shared FFN写gate/up/activation/routedDown/sharedDown。SharedGate dense复用gateOutput，sigmoid写upOutput；merge写mergedOutput，residual写用户final output。没有这些后续writer指向router区。
3. 共享Dense prefix workspace可能使用相同region3，因此单靠arena不重叠不足。HostBlockCommandsV4设置splitK=2560。Router K2048、专家/共享gate-up K2048、down K512、shared gate K2048，均不超过splitK；TransposedDenseOwner chunkDepth=min(K-chunkBase,splitK)，初始chunkBase=0，savingPrefix=chunkEnd<K恒false，因此本次后续这些任务无prefix workspace写入。prefixAlias admission修复并不改变该写地址条件。
4. 原P3 manifest末三步post_norm→moe_full(pc11)→final_fence(pc12)，P4为pc15→pc16→pc17；之后没有另一个Dense/下一block重用该区。final_fence不写DDR。driver在完整terminal drain/result消费后才dump。
5. 以上结论只绑定LAYOUT_SOURCE_PINS及本次manifest。新hardware/source guard identity仍需重新核这些公式/编译绑定，不自动继承旧源码证据；无DUT实测。

V3审计pin更正：V1/V2的35B辅助源码曾误列同archive的dense qwen3_5模块，不能作为实际35B依赖。V3替换为实际qwen3_5_moe/modeling_qwen3_5_moe.py（sidecar对应SHA），lines291/365/383确认同样[batch,heads,key,value]及K^T@V布局。未修改参考或旧产物。
