# M16 官方完整单层 capture 源码准备

当前状态：SOURCE_IMPLEMENTED / EXECUTION_DISABLED / NOT_NUMERICALLY_EXECUTED。
没有 import torch、numpy 或 transformers，没有实例化模型，没有 forward，没有运行 native、DUT、M16 算术或 RTL。
测试只执行 stdlib、纯 mock、完整源码 compile（不 exec）及临时微型 raw 文件的 hash。

## 入口与权限边界

公共接口是 `run_capture(raw_root, output_new, context)`，当前固定抛出 `ExecutionDisabled`，且不创建输出目录。
没有可开启的环境变量、布尔参数或 CLI。context 的 run_id、review hash 等只是数据，不是 authority。

完整待接入实现是私有 `_capture_impl(raw_root, output_new, context)`；当前禁止直接调用。
私有 Python 函数不是安全沙箱，也不宣称不可绕过。它仅为独立审查提供实际实现。
未来须由父级独立 launcher 完成精确源码/profile 独审、当前授权、一次性消费、资源控制和 import/maps 准入，再另行评审连接公开入口的修改。
不要把本次静态测试通过当作该授权门已闭合，不要以任意自行构造的 dict 调私有函数启动数值。

`raw_root` 必须包含 pins.json 指定的13个 `<local_name>.bin`：12个原始 BF16 参数及256行原始 embedding 前缀。
`output_new` 必须为不存在的目录，父目录先存在。不得是历史输出目录。
没有 producer_root、provider、旧参考目录、remote model ID、权重下载或备用填值接口。

context 的精确键集合如下，未来 launcher 还必须在进入本实现之前独立验证其真实性和控制有效性：

- run_id：新的一次运行标识。
- numerical_runtime_root：原 fixed11 数值 runtime 的 site-packages 根。
- transformers_root：固定4.40.1及新官方依赖 target 根。与上一根分开，不假装是一个根。
- config_path：原完整 config.json，其完整 SHA 固定，包含 torch_dtype=bfloat16 等全部内容。
- runtime_receipt_path / runtime_receipt_sha256：由 launcher 审过的完整运行闭包 receipt 绑定，capture 只核该文件哈希，不把它等同于已执行的闭包审查。
- softmax_source_sha256：必须等于固定 torch/nn/functional.py 的 f6335e443ce93ddf21ecf9d94bbb4d4a4d92e128c5bfb59826f35495c9c28703。
- launch_authorization / resource_controls：非空、可序列化的审批和资源披露对象；本实现不把它们当 capability，也不负责施加资源限制。
- reviewed_runtime_profile：精确对象，键为 cpu_capability、torch_build_sha256、torch_git_version、intraop_threads、interop_threads、deterministic_algorithms、python_major_minor。实际采集逐项相等才继续。CPU capability 没有硬编码 AVX512 旁路或硬拒，必须与独立核准的 profile 一致；固定主 profile 仍要求4/1线程、deterministic=True，不能悄悄变成1线程。

capture 不改 sys.path。launcher 须先建立双根、无系统 site-packages 回退的正常 import 环境。
capture 正常 import 完整官方模块，再核关键模块的真实路径、版本、源码哈希及完整 code 内容；实际完整 module/maps 闭包仍由 launcher 准入和记录。

## 正式路径的具体算术来源

1. 从固定完整 config.json 直接调用真实 Qwen2Config，真实父类为正常导入的 PretrainedConfig。
2. 保存实际 config.to_dict() 及 `_attn_implementation`。只有 eager 是显式 wrapper 选择；max_position_embeddings=32768、rope_theta=1e6、use_sliding_window=False 均保留。没有 rotary256 诊断混入。
3. 正常 import 全部 modeling_qwen2.py；完整原始 Attention/Flash/SDPA/Decoder 等类和原 backend 字典均在。编译完整源码只用于检查函数 code 指纹，不执行或改写 AST 子集，不替换运算表达式。
4. 实例化真实 Qwen2DecoderLayer(config, layer_idx=0)，官方构造默认 dtype 必须为 FP32，随后转 BF16/CPU/eval。完整 named_parameters 集合必须恰为12项。
5. raw13 每个文件实际全量 SHA、字节数、shape、BF16 均绑定。实际读入 tensor 的第二次字节也重核 SHA，防止 audit/read 间隙。原 output-major 参数直接 copy_，然后对实际绑定参数的原生字节分块核 SHA，不读 provider 转置结果。
6. x 是原 embedding 前16行，[1,16,1536]；position_ids 是0..15。mask 是显式 wrapper BF16 causal 参数，allowed=0x0000、future=0xff7f，136/120/16。它不是官方 mask helper 输出，也不是 DUT 捕获。
7. no_grad 中一次调用原 layer(x, attention_mask=mask, position_ids=positions, past_key_value=None, output_attentions=True, use_cache=False)。执行完整 DecoderLayer.forward，但不执行 Qwen2Model/ForCausalLM.forward、DynamicCache、Flash或SDPA 分支。

## 29个原值观测

严格顺序为：x、mask、n0、qr、kr、v、cos、sin、q、k、cache_k、cache_v、repeat_k、repeat_v、scores、logits、softmax_fp32、prob、pv、att、o、r、n1、gate、silu、up、act、down、y。

- module hooks：norm、projection、rotary return、SiLU、MLP上下游、decoder return。所有 hook 返回 None。
- Attention line trace：280前取 post-RoPE q/k、transposed v 及两个 cold alias；283前取 repeat_k/v；285前取 scores；300前取 logits；302前取 prob；304前取 pv。
- softmax_fp32：同一个 trace dispatcher 捕获原 torch.nn.functional.softmax 的真实 return。须是绑定的 code 对象、其父 frame 是唯一原 Attention frame、调用点300、input 是原 logits 对象、dim=-1/dtype=float32。不会从 BF16 prob 反推或重跑 softmax。
- 绑定并非仅行号：完整文件 SHA，实际 co_filename，完整 CPython code 的常量/字节码/参数/locals/freevars/位置/异常表递归指纹及运行 frame code identity 全部核。
- 立即 detach().clone() 保存观测快照，记录原 shape/stride/storage_offset/native dtype/device/storage 地址与长度。不会修改 frame locals、f_lineno 或原 tensor。
- cache_k 必须与 k 是同一原对象；cache_v 必须与投影 v 共享原 storage/offset，只是转置语义别名。没有调用 Cache.update，不能冒充真实持久缓存。
- 观测错误只累积，不从 hook/trace 抛出改变官方计算流程。重复、缺失、顺序、shape、dtype、调用次数或line次数异常最终一律 FAIL，无补值、无重算。off/on无干扰的实际数值证明尚未执行。

## 导出与终态语义

每个实际快照导出 `<field>.native.bin` 和 `<field>.f32.bin`。
native SHA 针对逻辑 row-major contiguous 原生字节，原观测 stride/offset 另存，不把底层 storage padding 混入输出。
BF16 的 FP32 导出是纯位扩展；softmax_fp32 是实际 FP32 return 原字节。完全不需要 NumPy。
绑定大参数的 SHA 使用64KiB块，不建立数千万元素的 Python list。

RESULT.json 披露输入、源、code、配置、实际CPU capability/build/thread、affinity/env、观测与输出原生/FP32 hash。
成功仅是 `CAPTURE_COMPLETE_NOT_NUMERIC_PASS`，并生成 SEAL.json 绑定全部二进制及RESULT哈希。
任何失败生成 status=FAIL 的 RESULT.json 并抛 CaptureFailure，不生成成功 seal。未完成目录不供比较。
异常进程死亡、磁盘不足或 RESULT 写入本身失败时，本文件不保证 receipt，必须由外部 launcher 写终态失败；不得把缺receipt解释为完成。

观测 shape/native dtype 校验与数值精度比较严格分开。原门槛完整保留为未应用信息：
operator BF16 max_abs≤0.03125 AND mean_abs≤0.005；block y max_abs≤0.05 AND mean_abs≤0.01；nonfinite不允许；FP32 softmax无获准误差门槛，仅diagnostic；rowsum误差≤2e-5。
本 capture 不宣称 DUT comparison、上述误差门或 rowsum 验收通过。实际导出非有限值会使 capture FAIL。

## 仍未闭合的执行门

1. 独立一用授权 launcher 尚未连接，公开执行固定关闭。
2. 双根正常 import 的全部Python/native依赖闭包、module/maps allowlist、无系统fallback尚需单独只import Gate；本次没有进行该Gate。
3. 实际机器 capability/build/线程/affinity/env 与精确review profile匹配尚未执行。仅代码支持核验，不是动态证据。
4. 32768官方RoPE缓存和完整层初始化的资源预算必须获准；导出仅3.72MB不代表RSS小。RLIMIT_CPU、进程树watchdog/RSS策略及终态清理由launcher负责。
5. 正式 raw13 此时没有再次读payload；未来运行才 fresh hash。当前测试只读小型临时fixture。
6. hooks/trace 在真实Torch上的顺序、软返回、code匹配及非干扰尚无执行证明；只有static/mock证明。
7. 新M16官方参考未生成，任何旧M128/旧M16 PASS均不继承。当前没有新的数值误差、M16/DUT/RTL结果。

## 允许重跑的测试

`python -I -S -B full_layer_capture/test_capture.py`

`python -I -S -B -O full_layer_capture/test_capture.py`

测试显式阻断 torch/numpy/transformers import。不要运行私有实现来“验证”测试结果。
