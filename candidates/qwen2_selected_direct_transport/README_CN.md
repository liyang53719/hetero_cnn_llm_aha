# Qwen2 选定 Chisel 对应的直通 Attention 路径（TEMP）

## 结论与实际改动

K/V的生产与消费没有dtype或地址单位缺口：两边都是64字节/16个FP32容器，element地址乘4。BF16只在数值物化/Matrix入口发生。现有little-endian适配器已逐位无损，不需要新建packing层。

真正差别是可选raw-KV Public缓存。它借用Dense的原A banks，维持4096行valid，执行acquire → fill/write ACK → read/ACK → terminal release。选定HostBlockTop的iDMA window只对Dense开启，Attention走普通memory口。即使没有另分配SRAM，这仍是不同的cache寿命、控制和外存流量，不能称作表示差异。

本候选新增小型 `direct_transport.py`，在一个原Public Attention job上安装已经发布的QK16/逐head PV schedule，并复用原 `PublicExecution.attention_edge` 和 `fullgraph_execution.execute_attention_owner`。显式 `enable_raw_kv=False`，不创建ParentLoan、KvSupply、ScratchMux、Banks、MatrixService或payload缓存。`direct_guard.patch`只在新独立overlay内让选定模式每个Attention edge前检查真实对象/债务；默认源文件及已发布包均未修改。

检查项包括：原owner/Matrix/Scalar/银行身份、client及内层client绑定、物理regions的base/extent/reserved/dtype/容量/对象身份、Dense/prefix排空、scratch请求/保留payload/ACK债务为空、raw transport与binding均不存在。提前参数错误不先安装单次binding；替换或遗漏binding、同类型client绑错service均在下一owner/Host edge前拒绝。

## 精确来源

当前基线main `1bdf70eb42de8752edeb616e8ef01e166628ca35`，tree `cc48abbc5e4fe59782e04feac3baa2057f300567`。51项源码闭包见 `INPUT_PINS.json`，由独立Git对象比对确认旧源码与当前main一致；已发布selected schedule源码按先前交付逐SHA核对。

选定Scala来自原 `production_qk16_rebase` 五文件recipe，不是bare main文本。Qwen2Block postimage SHA256 `31b618680b4c750398a0dcf21fa34185dd9fc9b1732e370cfce502915814bd68`；HostBlockTop `15cc34f041228f38d69b15868a9f9c45fb3f9ea53a9275ec6a6d9fd70b4b0c25`。其余完整hash/行号和单端口证据在 `ARCHITECTURE_BOUND.json`。

关键源码定位：

- `ffn_public/prefix_owners.py:159–163,217–236`：`<16I`写包、K/V两半复制、地址×4。
- `official_bf16/owners.py:3–6,62–93`：BF16数值物化仍使用FP32 wire container。
- `ffn_public/prefix_execution.py:53–79,103–147`：真实region/reserved寻址、64B读取、完整写包和ACK/publication门。
- `ffn_public/fixture.py:212–214,259–261`：BF16改动只针对Dense B；cache_k/cache_v是同一kv分配的视图。
- 选定 `Qwen2Block.scala:101,183–190,215,260–267,310,569–576,626–627,645–649`：512b包、FP32 K/V、Matrix入口BF16、地址与KvAppend长度。
- `raw_kv_attention/numeric_bridge.py:48–64` 与 `raw_kv_public/model.py:79–82`：已有bytes64/tuple16→512bit little-endian→bytes64转换。
- `raw_kv_attention/model.py:36,60–67,111–179`、`raw_kv/model.py:14–18,64–70,103–129`、`raw_kv_parent/model.py:25–38,48–74`：真实cache元数据、两银行映射、借用与ACK/release生命周期。
- 选定 `HostBlockTop.scala:79–101`：Dense-only window与job/done flush；`QwenOwnerProtocol.scala:446–451`：原core memory路线。

## 可复现的源组合与有限测试

公开目录刻意位于resident重任务触发范围之外。先准备全新partial source overlay：

```
python -I -B candidates/qwen2_selected_direct_transport/prepare.py --source-root RAW_CHECKOUT --output NEW_DIRECT_OVERLAY
```

它先核对全部输入与两个新代码pins，调用已发布selected-schedule assembler生成原6文件，然后原样应用已有raw-public默认关闭hook，再加直通guard。输出9个代码文件与两份源码组合记录；原6个文件hash不变，物理IO driver的while循环AST不变。无native/import模型/完整run admission。目标运行模块位于 `candidates/qwen2_resident_matrix/production_qk16_model/direct_transport.py`，公共交付目录不是直接import的模型包。

新小粒度执行入口为 `direct_transport.run(x, physical, dispatched_attention_job, final_ack_stall=5)`。它只驱动既有一次Attention job，不是完整block启动器。真正全block仍需另行审查新的profile/source/input freeze，不准改旧门、继承旧PASS，或把M1循环当prefill。

```
python -I -B candidates/qwen2_selected_direct_transport/test_direct_public.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_direct_transport/test_kv_wire.py --source-root RAW_CHECKOUT
python -I -B candidates/qwen2_selected_direct_transport/test_architecture_bound.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_direct_transport/test_prepare.py --source-root RAW_CHECKOUT -v
python -I -B candidates/qwen2_selected_direct_transport/test_traffic.py -v
```

最终新批74项normal /74项 `-O` 全通过；另以原字节复跑已发布上一批76项normal /76项 `-O`，均通过。独立复核覆盖新批74项每模式。`test_kv_wire.py`自行固定verbose输出，不接受 `-v`；其余脚本可传。每项亦在 `-O` 下运行。Scalar必要界另运行 `test_scalar_bound.py --source-root RAW_CHECKOUT`，同样采用 `python -I -B` 与 `-O`。仅Python3.12标准库，source composition另需GNU patch；无pip依赖。每个进程1 CPU、20 CPU秒、256MiB、30秒wall上限，临时输出仅TemporaryDirectory。

直接路径测试使用实际PublicExecution/PhysicalMemory/原物理driver/selected owner与clients的固定AST；Host、Dense和算术service明确为synthetic。一个M2 job实际产生Q192、K288、V288外部读，192组write command/data/ACK，最终ACK停顿5个host tick，Matrix获取/释放各1次，raw/scratch银行活动为0。这是控制回归，不是新数值资格，更不是M128/fullblock/RTL通过。

线格式测试覆盖771种位模式（含512个walking bits、NaN/subnormal编码）、全部4096行两银行映射及真正RawKvPort的ACK/释放/abort fence，使用原16×1376×256 Banks。原Banks使用assert，测试显式以optimize=0编译这些未改AST，让原不变量在-O启动下仍被检验；这不是宣称生产Banks的assert在-O下仍存在。

## 固定资源、流量与架构上界

`traffic_plan.py`为逻辑64B读计数，不是AXI/iDMA周期或测得带宽：M128下K=V=792,576读，总计1,585,152读/101,449,728字节；原冷raw cache只有4,096 miss/262,144字节，其余1,581,056为hit，比例387倍。直通路不借用raw banks。数值存储表示无损不等于这两种流量/寿命相同。

选定源码证明只有一个MatrixPipelineService和一个normal step.fire。QK packed选择时Dense/legacy ready被禁止；PV mask1占用同一wide issue口，不能与其它slice的Dense同时发射。固定安装4096MAC，五个context也不增加issue口。

给定原fullblock有用MAC 6,014,828,544，QK55,296+PV792,576 slots，再极乐观地给Dense每slot4096个有用MAC，Dense至少1,462,272 slots。因此完整block硬件service-clock周期至少2,310,144，固定资源分母至少9,462,349,824，条件架构上界为30593/48128，约63.56590758%。它不是实测利用率、可达到吞吐或RTL运行结果，且故意忽略DMA、Scalar、控制、停顿与退休成本，所以只会更乐观。不得把它写成严格≤63.5659%的向下截断上界。

### 第二层：mandatory QK Scalar必要界

更强的当前源码必要界独立于上述Matrix issue计数。选定 `Qwen2Block.scala:107` 实例化同隐式clock下的 `BlockScalarFloat`；`:301,333–334` 接受真实request/result握手。`:581,589,594–599` 对每个有效score从+0执行16次严格Add，再1次严格Mul，未省略第一加法，也没有tree fold。128行/12heads共99,072个因果score，必需1,684,224次Add/Mul请求。

当前main未改变的 `BlockFloat.scala` SHA256 `9863718ca90089bf812eb07dbd82ce16d982a8c74b04d7543de1bd2dfb1e37b5`，Git blob `021c878dcb1106335d8a0cf768fdb862ab00533c`；专用 `SCALAR_SOURCE_PINS.json` 核对这一个额外源码。`:55,58,69,71–81,108` 规定request只在idle接受，Add/Mul经过normal，再done，result.fire后才回idle。最早e0接受、e1计算、e2结果退休、e3下次接受，因此N个请求从首次接受至最后结果退休的跨度至少3(N−1)+2=5,052,671拍，已去掉末尾不需要的下一次请求准备拍。

即使给所有Matrix/SiLU完全重叠的理想条件，整个block周期仍≥5,052,671；4096固定资源的完整分母≥20,695,740,416，故条件架构上界为1468464/5052671≈29.0631232471%。两种资源下界只能取max，不在未证明相位不重叠时相加。此界不依赖旧SiLU预算或PV6预算，也不是RTL实测；只修PV6、保留当前QK串行fold/scale仍受该界约束。若合法改变fold/scale执行路径，必须重新审查此证据，不能继续套用原上界。

因此该选定对应基线在这些前提下达不到80%/90%目标，不应在它上面启动长M128/RTL来追该目标。后续优先审计复用已有packed/batched PV或多query路径，保持4096资源，不能为通过对应测试悄悄更换架构。本批不实施性能架构改动。

## 仍未验收

整体INCOMPLETE / TEMP。额外默认legacy-QK完整M2回归超出当前固定synthetic服务能力；探针仅验证默认LegacyMatrixClient、无新binding及9次Q/K读取后停在fixture不支持legacy QK，不把它报告为生产失败或完整PASS。只有小粒度控制、表示和公式证据；没有完整M128数值、真实native/profile2组合、完整Host/Dense模型运行、Scala/RTL执行、硬件周期测量或长序列资格。Direct路线关闭本次发现的额外cache调度差异，但不能因此宣称整个模型已映射到硬件。
