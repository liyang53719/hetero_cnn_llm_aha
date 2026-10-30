# 实际同 job backend→五 profile 接线候选：INCOMPLETE，禁止启动

本目录是本地源码候选，不含 workflow/launch，不运行 DUT、不发布、不上传二进制/SV/权重/参考。仅 Chisel 测试生成 IR/RTL 的仿真 backend；不是原生解释器，不是完成模型后冻结刺激的最终 RTL replay。

## 已实现的真实调用链
1. 原 `bootstrap_build_only.py` / `one_job_build_only.py` 四件 producer 硬 pin 源保持不变。未来上层作为父进程调用，不改原 P0 证明身份。旧一次性 workflow 不重触。
2. `numeric_tail.py` 接真实 owning build RESULT + 七文件原manifest，原 local_build_proof 校验 run/source/launch；原 ABI CLI under strict outer 取得/冻结 startup loader/libraries。
3. 所有五 profile/完整 M128 先登记；一份70 tensor权重，三 runtime owner lease。`provider_from_frozen.py` 不下载/安装/重算参考，复制已冻结独立参考文件，调用原 programs、P0 RoPE/rebuild/emit_tsv、P12/P34 providers。禁止参考 output/router 输入 DUT，原 consumer 二次检查 views。
4. 原 `connect_bundle.py` 消费 fresh P0 producer 的12角色/真实driver depfile/retained receipt，不伪造旧证明；再执行新 `consumer_owned.py`。
5. 新 consumer 仅生命周期改变：不 nested setsid，继承实际 strict outer；校准只缩执行 wall，不改原bundle20000边界、完整128刺激、maxcycles、固定4096/Vector32或数值比较。结果永久INCOMPLETE/exit2，不把诊断当PASS。
6. `locked_phase.py` 在 supervisor 已持锁启动的进程中实际 inode census/deadline admission 后 exec；原 supervisor 不改，cleanup/EOF后才能释放父lease。进程采样仍有同步census盲区，绝不声称连续RSS峰。

## 执行前确定尚缺（不是用户网络许可）
- fresh CI 三 runtime 安装→新 owning receipt→shared owner 仍需实际接线。现本地 V2 owner 严格硬锁本机3receipt/安装binding；不可改schema/冒用到未来CI。不能只把本地绝对路径填进workflow。
- 尚无实际 fresh backend/ELF 供本候选ABI/consumer接线测试；历史成功binary未保留，不继承其哈希/PASS。
- 未来上层必须保留作业开始 monotonic deadline，不在build完成后重置350min。所有5 initialization+7 provider+5connect+ABI+5DUT/cleanup须全额登记预算；没有DUT速率不得准入完整5×20000。只能另行审核同刺激短wall标定，timeout仍INCOMPLETE。
- 磁盘账本须实际同job census：历史install约3.506GB/70weights3.531GB/参考44MB不能当峰值上界；CPP历史1.228GB，object/link真实同时存活未知。8GiB原门与12.081GB总cap不降。尚无自动删除代码；只有可重建/已完整保存副本且不再被P0/source proof引用的中间文件才可能另审退休。
- `numeric_tail` 需要独立审的实际 binding，包含所有脚本、原219依赖、owner/70权重/5参考、当前build、whole roots、runtime/工具pin、阶段资源。phase_extra_bytes只做准入预留，不是独立增长硬限；实际外部profile写入受总树采样cap，run_dir受512MiB stage cap。当前没有可执行binding或CI launch，故绝不称operational CI ready。
- 原P0 gate/up内部观测仍未覆盖，MoE同分小ID未获确认；原严格诊断策略不改，Chisel/最终RTL完整数值仍0/5。

## 已有真实参考与当前资源
本机2026-10-30 06:38轮新五参考5/5，仅独立Python。ROUND SHA964fde7bdd3b734e8a75672ab238ad0d701dbfb895ba945476b8d3642a938a1c；120 tensor records已全hash，135证据pins本轮再核。未为本候选重算。
07:38 MemAvailable约9.22GB，低于历史Host9.592GB，禁止本机完整frontend贵试跑/缩硬件。

## 测试范围
consumer原函数AST/mock7、live-budget真实小文件树/预算8、reference拷贝/篡改4、tail登记/资源/生命周期AST5，每项normal/-O。没有真实loader/Torch/provider/DUT；没有安装/下载/新CI。完整接线仍待独立审，不能以这些小测试代替运行。

交叉审修复：初始化参考拷贝/programs已移入strict受控phase；DUT阶段继承CPU hard保留原18000，outer aggregate CPU/wall仍受短标定限，AS必须>=原12GiB，避免preexec试图提升hard限制。所有own roots覆盖owner/repo/payload/build，权重不进旧supervisor的read_bytes pins，parent流式pre/post复核。

独立复核后真实stdlib fixture一次：原supervisor→新consumer execute→/usr/bin/true，native0/errors空，0.208s，observed RSS12.98MB，完整cleanup/EOF/gzip；receipt e17db0b78eb8e99505b5704a19db0d6ffebae7cc260f40f896524af474197886。不是实际DUT或loader资格。预算更正为23×60+5×30至少1530秒清理/启动预留，另必填父lease/hash/census预留，不当免费。

R3新增实际成功Popen后的startup receipt（内部PID/group及binary/runtime SHA，不公开PID），tail不再把exit2当已启动：必须核RESULT.json/唯一profile/同artifact和bundle/INCOMPLETE以及startup身份，缺报告或preexec失败无startup即failclosed。分类timeout/native失败/完整诊断/观测不足；数值算法不变。新6测试和consumer7 normal/-O通过，未再运行真实fixture/DUT。

R4环境前置：execve环境只接受基础白名单，HOME/HF_HOME/HF_HUB_CACHE/TRANSFORMERS_CACHE/XDG_CACHE_HOME/TORCH_HOME/NUMBA_CACHE_DIR/MPLCONFIGDIR/TMPDIR均显式新建于watched job/cache_roots/stage；locked_phase持锁后复核实际目录、无alias、覆盖roots与offline flags。拒绝继承PYTHON/LD/credential环境；原runtime wrapper仍负责其已核site。4环境负测normal/-O过，不声称曾发生外写。

R5 startup与本轮outer严格联结：tail保存实际runs/pN_dut/RESULT.json pin，verifier核worker_started/native2/errors空/cleanupEOF及cleanup同owner identity；startup consumer PID/自己的/proc/self/stat start tick/group/session逐项相等，拒错轮receipt。不把瞬退DUT /proc作为必要采样。8证据负测normal/-O，7consumer AST/mock normal/-O，未DUT。ABI/DUT cache白名单整合尚待下一候选，当前不声称所有exec cache已闭合。

R6完整owned ABI/DUT环境：新runtime_abi_owned ca7e9d…使用SAME_JOB_ELF_STARTUP_ABI_OWNED_ENV_V2，原f682原件保留但不作为本次loader/DUT入口；稳定同job execution_cache九目录用于ABI→connect→五DUT。新connect_owned只改consumer路由/环境参数/source pin集合；P0派生函数不变。补原run_compare原件供attach_bundle原pin/need工具导入（不调用其execute），避免模块闭包缺失。早期测试发现该缺件已修；ABI测试首次用错unittest发现模式缺--baseline，已按显式baseline重跑12normal/-O通过。新增3接线测试及7consumer AST/mock每模式过。fresh CI tail只接受新V3 owner同run/source/launch、参考receipt匹配该真实runtime/sidecar，不继承本地V2资格。

R7修输出接口：consumer_argv及validate_only_argv显式含--strict-outer-supervised；验证也必须在真实outer上下文。tail不再重复追加flag。原require_outer_context不降低。3接线测试normal/-O过。
