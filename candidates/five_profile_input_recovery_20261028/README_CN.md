# 五块原始输入恢复：TEMP / INCOMPLETE

基线 main 7afcf3adf0d9265a8e746ecc55979c80fc34b6d2。环境证据丢失后重新核查，不继承旧 PASS。五块完整 M128 Chisel 数值仍 0/5，同刺激最终 RTL 0/5，无周期或有效 MAC 利用率测量。

## 实际结果

已重新验证三模型官方固定 revision 的原始 safetensors metadata，再按完整典型块选择70个tensor，3,531,306,272 B：Qwen2 L0为93,595,648 B；0.8B L0/L3为43,111,008/36,705,280 B；35B L0/L3为1,685,402,304/1,672,492,032 B。35B包含两层完整所有专家，没有只取选中expert。排除MTP。初稿误匹配MTP被拒绝，最终计划已从原header重新推导并核对。

首次实际采集最多2 worker，每响应≤8 MiB，先核8个shard header SHA。实际完成30/70个tensor、357,664 B，五profile均有已核文件，并独立重读磁盘核hash；另35B M128实验hidden已精确重生，524,288 B，SHA c32e36dd356244838b17f8aebd8a0e647c5a09198365ad32c6f7996adef237bb。它是外部实验输入，不是embedding或前层输出。

随后35B L0 in_proj_b shard14 range409048–540119、并发Qwen2 k_proj range549367944–550154375均遇proxy tunnel403。任务停止，未重试、未改路由、未整shard回退，部分文件及原记录保留。总收到672,536 B（包括header），请求40次。访问尚不可用，不是checkpoint损坏或数值失败。ACTUAL_PARTIAL.json只保留身份/范围/hash，不包含tensor字节。

## 可移植复现闭包

本包为纯文本：原始固定revision manifests、原始header的UTF-8 JSON正文（仅name/dtype/shape/offset，无tensor值）、精确0.8B tensor hash pins、35B历史source hash集合、采集与重建脚本。reconstruct_plan.py为header JSON重加原8字节长度前缀，必须精确恢复原header SHA，再从完整header独立选择指定五层、排除MTP、验证形状/offset、与70条计划逐项核对。不需要旧机器私有路径或缺失父级文件。

- 0.8B有25份name→SHA精确pin。
- 35B语义身份以官方固定revision/header name/range绑定，hash集合只提供独立历史一致性，不证明无序hash与名称的映射。
- Qwen2原始tensor的hash是新获取记录，不宣称与旧transposed/FP32 provider字节相同。
- headers中的LFS advertised hash仍未验证整个shard，不升级为全checkpoint验证。

离线：python reconstruct_plan.py。普通及-O模式各10项metadata负向测试、10项transport测试和5项显式reuse测试。实际网络运行使用本包前身脚本SHA855781ae75554602e42311251fa57d1c06f80282a3a5fa5309945f16ce7fc7af；本公开版本只改consumer路径/独立metadata验证与显式reuse，其网络入口**未重新执行**，测试不是再次下载。

网络访问恢复且获得适用授权后，操作者才可显式运行：python acquire.py --output NEW_LOCAL_DIR --execute --reuse-from PRIOR_PARTIAL_DIR。不含自动定时/重试。只复用完整receipt已重新hash且语义一致的文件；不继续未知partial，不覆盖旧目录。每次仍核header，不能跳过既有验证。原始权重3.29 GiB，入口要求至少8 GiB空闲；这不是reference或编译峰值。469个≤8 MiB body请求（复用会减少），每请求90秒socket超时，不是总wall硬限制或性能预测。

只有完整70份采集成功后，python build_recovered_sources.py --data COMPLETE_LOCAL_DIR --output NEW_BINDINGS.json才会再次读盘核SHA并生成新原始source bindings。该脚本当前未对完整真实数据执行。新bindings不是旧provider source spec身份，也尚不是完整逻辑视图/后端export。所有payload、输入、参考输出、NPZ、probe hex仅留消费者本地，不提交。

## 继续主线所需

P0须采用recovered_execution_fixes/provider_candidate的原生BF16 Dense B候选，激活/输出/bias/Norm/RoPE保持原FP32；历史five_profile_byte_provider/qwen2扩展路线不迁移。新spec/manifest/逻辑hash均重新生成。

官方0.8B原forward确有多token chunk路径，cached seq_len==1才走recurrent，不能把项目入口M1限制归因上游整体。P2历史prefix capture依赖L0/L1/L2；后继可另立明确的新external-boundary输入与完整L3官方reference，不借用旧prefix身份。P3/P4保持原Torch路由，同分小专家优先契约仍未确认，不注入expert IDs。五块仍须同一4096 MAC硬件完整重测，reference、Chisel、RTL严格分层。

官方Python依赖恢复也受同一网络访问阻塞：Qwen2精确25 wheels锁（不是26），SHA8556b5ca104a64b9028a177b3029edb2a0b34d5ac93ed2dcd3e76b483c54960f，对应现有 candidates/qwen2_resident_matrix/portable_official_producer_launch/requirements-runtime.lock；Qwen3.5为38 wheels+官方archive，锁SHA806f6a7f409e85965261bf864fcc8de4558aaedf9f3da26759323625ca131497已从Git恢复。仅certifi 136,983 B已下载并校验，未安装任何runtime依赖、未执行reference。原锁不在本包重复提交。

本轮不清理任何已有输入或证据，不重写历史；下次恢复必须复核权限和当前文件身份，不能自动重试已拒绝访问。
