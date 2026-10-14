# f16 CI 源码、计划与执行组边界修复

## 原失败与处理原则

基线为 f16df50adfb0f1f4bc668c517a2e29accffe6753。保留原 CI run，不重启或取消已有任务；本地冷门不替代远端完整 CI。

- shape-layout 38512377090：shape_layout_vectors.json 的 Qwen2Block / QwenOwnerProtocol 源哈希过期。两项旧值精确匹配 f16 父提交，64个数值向量、两个 legacy TSV、生成器、C++ oracle 均未改变；仅更新源身份元数据。
- current-model-goal 38512377088：计划增加真实阶段结果后，ledger 的计划字节 SHA 未同步。逐项确认原任务、状态、证据、门限未变后更新绑定；本批性能进度再同步计划与 SHA。阶段最低80%/争取90%，最终完整RTL联合数值及90% MAC验收保持原定义。
- Qwen2 continuous 38512377127：冷 orchestration 测试错误地把四个真正执行组与六个 planner 分组相等比较。改为显式四组；两组真实外部fixture必须 NOT_EXECUTED、counted_as_pass=false、指向专用runner；保留全部suite唯一覆盖及缺分组硬失败断言。runner数值主体未变。
- Qwen2 model 38512377063：41个测试因活动模型源pin过期失败。只审查默认关闭 enableH2048RmsBorrower / externalElementwiseLoan 的原Qwen2路径；不把新RMS路径或局部RTL测量带入旧模型。

## 默认关闭语义边界

Qwen2Block默认 elaboration仍选择同一ElementwiseMemoryEngine，新增loan Option不存在、exclusive恒false；原ready条件归一化相同。HostBlockTop源字节不变且未传入新选项。QwenOwnerProtocol默认borrower为空，原Qwen2无native RMS owner，新增unavailable恒false，既有调度和Matrix仲裁不变。

四个活动模型的数学函数AST、容量/请求公式保持原样；21组父提交与提案输出对照只排除已列出的源身份元数据，生成的C++逐字节相同。源码归一化diff和默认H1024/准入门是有限边界证据，不是形式等价或完整当前block RTL。

保存的v0 census receipt原始字节和SHA不动，仅允许两对明确的历史→f16源码身份兼容映射；其他source漂移、未知旧/新hash、启用新borrower/loan或非bool配置均拒绝。输出分列historical/current source，current Host reexecution和current RTL measurement均false。

## 当前运行库存与历史证据

首轮六文件修复后，原完整workflow还暴露四个后续candidate观察门的历史源码库存失配。不能用当前源码冒充旧的75源执行receipt。本批将活动driver guard和observer升级为v3当前运行库存，原receipt/SHA保留；精确五项替换，剩余70项逐SHA严格。已有Matrix numerical替换保留，新增只涉及两个默认关闭Scala源和两个活动driver身份的版本化。

新输出声明 current commit=null、base commit=f16，列全当前源码SHA，results_inherited=false。两个活动driver的算术/协议方法、观察器捕获与调度方法AST不变；只改guard、版本、身份输出和测试断言。原历史数值结果不继承为本次执行，当前轻量软件测试也不升级为模型权重/完整RTL数值验收。

## 预发布一致性门

新增 scripts/check_generated_source_consistency.py，一次只读运行检查生成物、计划ledger、活动及下游pin、历史receipt兼容边界、suite唯一完备分组和外部fixture非PASS状态。不存在自动refresh/skip模式，任何失配都给明确失败。原模型workflow在全部原模型门前执行该预检及normal/-O负测，路径过滤只增加保护。

运行身份、原失败保留及最终各门结果详见 reports/execution/CI_SOURCE_CONSISTENCY_20261014/。这批发布前的本地软件门存在两项因缺Transformers4.40.1未执行，单独标明；远端安装固定依赖后仍须由精确新commit的原CI给最终结果。

## 本地验证记录与边界

- 四后续门最终分别20、5、71、118项通过；主模型pytest254项通过、2项NOT_EXECUTED；三个prefix pytest共107项通过。
- v3原34命令整跑中33项成功，唯一失败是临时审计副本挤占/tmp，低于原2GiB资源门。仅清理该审计自身可重建的parent副本和旧pycache后，完整12-file命令单独冷重跑为254+2未执行，资源门未放宽。最后三观察测试补充provenance输出/断言，再按原命令复验20/5/71；不宣称最后一次重新整跑全部workflow。
- 独审发现直接执行attention测试时main块位于新增类之前；仅将main移到末尾，在当前工作树直接执行也收齐20项并通过。production源码不变，原测试断言全部保留。
- 当前工作树的Qwen2 orchestration正常/-O各10项通过，是真实fixture packer与源哈希的冷编排测试，构建工具受控mock，无RTL或模型数值执行。
- 最终预检强化为14项，含75/5/70库存及commit=null/base=f16/不继承历史结果的元数据门；79项负测覆盖真实传播到子进程的-O模式。精确当前工作树结果和哈希在live_release_checks.json中。
