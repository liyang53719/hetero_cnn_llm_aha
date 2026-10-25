# 官方 M16 同层两-arm参考：源码与脱敏证据

完整官方 Qwen2DecoderLayer 的32768配置参考已生成并通过自检与独立执行审查。一次受控worker中仅构造一个层，先运行没有capture observer的baseline，再在同层、同原x/mask/positions对象上运行带全29观测的第二arm。

这不是Qwen2Model/ForCausalLM全模型执行，不是DUT PASS，也不是项目既有rotary256配置与官方32768配置的等价证明。

## 本次实际结果

- 原官方config：max_position_embeddings=32768、rope_theta=1e6、use_sliding_window=False；eager是明确wrapper选择。原config完整SHA为a58e896d2756a7947f23f3db55667c19ca3b8524188a30c8c640cd7ff72a5136。
- 全部13个原始BF16输入身份已绑定，合计94,382,080 bytes；公开的只是name/shape/dtype/size/SHA，不含权重或输入payload。
- baseline立即保存实际y/prob native bytes；observed返回与其逐字相同。三边界重新枚举原inputs/parameters/buffers，身份、元数据和native hashes一致。
- observed全29字段的geometry/native/f32导出、finite及已定义语义关系通过。仅y/prob返回与状态边界有paired无干扰证据，不声称无observer可观测所有29中间值。
- softmax_fp32的192个行和最大误差1.30385160446167e-7，小于原门2e-5；1440个future位置为正零。BF16 prob行和误差0.00279998779296875仅诊断，未增加FP32精度门。
- 资源实际worker wall约25.46秒、CPU约27.71秒，峰值采样树RSS574,599,168 bytes。提案4 CPU/intraop4/interop1/deterministicTrue/CPU60秒/wall90秒/1.5GiB采样RSS未扩大；采样RSS不是硬cap，AS未变。
- 独立审查121/121检查通过，89个run文件重hash、87个receipt清单项闭合、60个capture二进制身份绑定，完整18,648项source/runtime/input重新流式hash无漂移。此次公开准备没有重复import、forward或tensor算术。

## 文件边界与SHA含义

运行源码逐字复制，不改默认路径或逻辑。SOURCE_INPUT_TOOL_PINS.json给出逻辑source/input/tool pins及外部闭包数量，不发布完整私有CONFIG/manifest。

OUTPUT_IDENTITIES.json只有29字段及baseline y/prob的shape/dtype/size/hash，绝无payload。输出SHA是本次新观察的内容身份，不是事先已知正确答案或旧reference PASS。

EXECUTION_SUMMARY和EXECUTION_REVIEW_PROJECTION是脱敏摘要，不是原receipt/seal/review的逐字副本。它们引用的原件SHA只标识未公开的私有原件，不能拿该SHA直接验证摘要字节。发布allowlist另行绑定这些公开投影自己的SHA；没有伪称投影继承原seal。

r1的路径/PID问题、r2的修复及single-arm被superseded事实保存在REVISION_HISTORY。没有改写旧失败，也没有复用旧审批/claim。

## 可复现的纯mock范围

历史作者测试68项normal/-O已通过，完整原测试源码与历史日志原样保留。公开portable入口仅原样运行其中66项，并明确排除2项依赖未公开历史源码的测试；另跑2个新的公开source/helper哈希检查。新增哈希检查不算原68项复现，不宣称原suite全量无skip复现。具体名称和原因见PUBLICATION_ADAPTATION.json。

纯mock命令，均只使用stdlib与临时合成数据：

python3.12 -I -S -B run_portable_mock.py
python3.12 -I -S -B -O run_portable_mock.py

fresh checkout没有外部固定runtime/official dependency target、原raw13或原config的可执行布局，也没有私有4MB CONFIG和一次性授权。它只能自包含复现上述纯mock子集，不能自包含重跑数值参考。实际数值复现的前提见REPRODUCTION_BOUNDARY_ZH.md，不要直接启动worker。

## 后续比较

DUT、项目rotary256对照、M128及RTL均NOT_RUN。未来仅在参考与DUT各自完整终态、封存和独立资格确认后比较；不把进行中或部分输出流当比较输入。原operator/block-y阈值保留但尚未用于DUT比较。
