# 0.8B L3 M128 原attention前缀输入适配

- done：调用原pinned_block_payload.load_payload重验真实L3全11tensor的shape/hash/HTTP receipt。使用固定revision 2fc06364715b967f1860aea9cf38778875588b17。
- done：新增adapt_attention.py，严格按原StreamingDense.scala:87–90地址公式，将checkpoint Q/K/V [N,K]无损转成原runtime B[K,N]。Q完整4096列，保留query/gate布局，不按头裁切；K/V各512列。全部仍BF16，不引入浮点量化。
- done：提供128×1024输入，明确合成精确dyadic，不冒前0–2层真实输出；input/q/k norm保持原BF16，未预加1。总7个输入/权重文件10,750,976B。没有归一化或Q/K/V中间输出预置。
- done：原数据布局实际生成后逐位反转验证，9个真实权重列用相同ascending-k独立FP32乘加检查转置前后相等。仅布局/选列参考PASS，不是完整投影数值，不宣称该序列等于Matrix真实归约顺序。3单测普通及-O通过。
- todo：接原Host runtime RMS真实ACK之后，以role0/1/2连续提交真实Dense Q/K/V；保持HostBlockCommandsV4:1284–1336的producer/lease身份检查，不绕过rdLive、不用预置normalized输入伪造RMS完成。随后原QKNorm/Rope/KV/GQA。

原接口匹配：profile2，hidden1024，M128；rdAttentionWidth role0=8 heads×512=4096，role1/2=512。运行配置不同而非重elaboration。

原源码引用及哈希见ORIGINAL_PATH_PINS.json（已验源码快照）；本次不改任何DUT，不构建替代硬件，不声称硬件执行。所有五块完整128仍0/5。35B已策略阻断不再联网。此目录摘要可提交，兄弟l3_attention_payload内生成字节不可上传。

## 本轮追加：完整原Host程序绑定
新增bind_full_attention.py，复用同一原emit_cold128_programs.common(2)，绑定完整22命令至原分配地址，覆盖RMS/QKV/QKNorm/Rope/KV/QK/Softmax/PV/gate/O/残差/PostNorm/FFN/final_fence。训练payload的全部11tensor均被使用，13个只读segment共36,983,808B；命令和descriptor在本地可重建。所有中间仍未初始化，无预置值或伪造ACK。

状态明确TEMP_COMPLETE_READONLY_BINDING_TRIG_CONTRACT_UNVALIDATED：trig是调用方输入，本轮用独立NumPy FP32 theta1e7/rotary64→BF16 RNE生成候选cos32/sin32，尚无原PyTorch平台capture一致性证据，不冒原参考契约通过。此候选可完整供数，但不能因此声称已被原Host验收。后续可直接替换--trig为已验输入；严禁默默把候选变生产契约。

5个单测普通及-O通过，覆盖原22命令/role顺序、完整只读集合、O/FFN存在及明确未硬件执行。首次新增测试误将schedule名residual2当tensor名引发KeyError，已修正测试并重跑；实际最终tensor名output，无DUT/生成器变更。

## 原Torch平台trig重新执行后更新
已从同一官方wheel URL恢复Torch2.10.0+cpu，188,943,803B及SHA ee40b8a4b4b2cf0670c6fd4f35a7ef23871af956fecb238fbf5da15a72650b1d吻合；原lock的10个Torch/numpy依赖均逐字节校验，安装至独立site。未触及35B被阻断CDN。

generate_trig_torch.py从固定官方modeling源AST抽取compute_default_rope_parameters/forward/recomposition_frequencies原方法，default rope无动态更新，CPU DEFAULT/单线程下执行；不是重写近似公式，也不是完整官方模型运行。M128 BF16 trig重新capture SHA1156df1551f166fe3f816547b6a15eac1c2ff994683138d5276d2f64c68aa9bb；8,192字与NumPy候选比对0差异。该特定trig字节现已在binder pin，因此完整22命令输入绑定状态更新PASS_COMPLETE_READONLY_BINDING_NOT_HARDWARE，trig_contract_validated=true。其他任意trig仍TEMP，不自动认可。

修改后5单测普通/-O重跑通过。新输入在l3_full_host_torch210_payload，所有输出/中间仍由Host生产，未执行硬件。runtime目录附10依赖lock及官方获取脚本；包内脚本仅把外部锁路径改为本包相对路径，实际执行恢复脚本hash单独保存。严格不含wheel/权重/输入字节。
