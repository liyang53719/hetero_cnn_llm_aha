# U00.2 原始 Public M128 超时定位与安全诊断（2026-10-16）

## 结论与边界

原始尝试run38952336951（job117146548710，checkout `ac3a074cd0e29342447844a7675425af628a39ef`）在numeric阶段超时。2587.336054秒是wrapper总耗时，不能当作Public实际执行耗时。没有完成postflight或数值验收；不能从遗失的私有文件推定native或Public PASS。新增诊断代码仅做冷测试，没有重跑该数值任务、下载权重或执行RTL。

总体目标保持：Qwen2-1.5B、Qwen3.5-0.8B、Qwen3.5-35B-A3B典型block，batch1/M128固定，实际RTL及有用wall MAC利用率90%仍待实证。

## 可复核历史证据

安全归档：`candidates/qwen2_resident_matrix/raw_kv_public_recipe_timeout/`。

- artifact12071740663；ZIP大小15278字节；SHA256 `85b9554eaedf9904760d1da4363470903dbd04e32c72016c131c55e9c89d4855`
- ZIP只含summary.json（1195字节）、progress.json（80字节）、source_hashes.json（39391字节）；保留原始成员字节，各成员hash写入checkpoint.json
- status=TIMEOUT、phase=numeric、numeric_started=true、postflight_complete=false、numerical_acceptance=false
- CPU只证明AVX512-BF16前置资格、未观察到AMX；eligibility_only=true，不能替代backend/native实际通过证据
- 源清单283项、生成源码12项；冻结旧launch contract SHA256为`3fb70fe4016b226bca41cf82bd8ca4e34845575f1216fe3c45af2d2108cce271`

绑定源码中，只有setup返回成功且再次context核对后才设置numeric_started；因此setup完成是控制顺序推论。归档没有独立native receipt。traceback `run_ci.py:608→222→setup.py:198`落在父进程`proc.wait(timeout)`；没有子进程内部栈或PC，无法判断超时位于prepare、Attention、FFN、比较或postflight。

## 预算诊断

保持setup900秒、内部执行2400秒、数值包络2430秒、总3420秒，不加timeout。

外层2430秒包络预留5秒进程组清理和1秒receipt，所以实际等待子进程约2424秒。admission、snapshot prepare、source核对、Public执行、comparison、postflight共用此期限。内层2400秒计时在snapshot核对和导入之后才开始，若执行用足，其余阶段名义余量约24秒。旧artifact没有阶段时间，不能据此断言余量就是本次根因。

历史1548.112413612秒来自commit`38b943cdf6a0e2d642a1aef07b30e6d23e3ceed8`、116源闭包；本次14项历史重叠源码不同。另一份synthetic Attention direct303.966秒/loan802.100秒属于不同library、public_profiles_executed=false，不能把跨运行加和当作完成保证。

原始M128 Attention静态工作量很大：99072个head/key pair、1585152个Matrix packet/raw-KV request、111360组、4096 unique KV lines；每包16KiB结果快照合计25971130368字节。无exp cutoff时标量调用55480320次，真实输入可能减少exp操作。这些来自源码的预期工作量，不是本次已执行计数，也不能定位本次超时。旧source manifest不包含后来的attention_batch/scalar_schedule/attention_scheduled源。

依据：`official_bf16/owners.py`、`ffn_attention/{attention_owner,matrix_service}.py`、`ffn_public/prefix_arithmetic.py`、`raw_kv_public/model.py`、`raw_kv_attention/{streaming,scalar_recipe}.py`。

## 新诊断设计

只修改最终`raw_kv_public_recipe_run`层及其严格生成entry，原始Host、owners、Matrix、算术模型、原验收阈值、三变体兼容规则、workflow均不改。闭包285源，生成文件仍12。

私有固定文件`numeric.progress.json`，原子replace+fsync，最大4096字节、最多256次；独占writer claim与context/source SHA256绑定，sequence和elapsed单调。首次context校验之后创建writer，elapsed原点为NUMERIC_WRITER_START，和wrapper总时钟不同。只允许固定阶段/事件/operator枚举、原始ordinal及有界整数计数，没有自由文本、路径、地址、数组、权重或日志。

entry标记preflight/input load/prefix/suffix/observation seal/comparison/source recheck/receipt。外层记录admission/import/snapshot/执行/验证/文件核对/postflight各阶段ENTERED/RETURNED。RETURNED只表示该Python阶段返回，绝非数值PASS。

在原`trace.event`之后旁观已有Host接受事件，原事件原对象先交原sink；只读request.tag低16位或completion.pc，以及host_model_ticks/request_fire/owner_result_fire/completion_fire/result_fire。没有新增逐tick hook或模型时钟，也没有硬件性能推断。最后快照时间可能早于超时；计数只是软件Host事件，不是硬件利用率。

父进程在子进程组cleanup后可以独立验证最后完整快照，投影到失败summary，不依赖numeric.validated或numeric.complete。半写.pending不被读取；没有有效完整记录就标记numeric_progress_unavailable。子进程记录不能覆盖冻结metadata/source proof或改变数值验收；成功必须经过原有严格receipt/postflight路径。上传仍只有原三份安全JSON。

## 计划与检查表

- [x] 核验原ZIP及三成员原始字节和hash，归档失败证据与边界
- [x] 区分监督器等待栈与真正子阶段，区分wrapper总时间与执行时间
- [x] 解释2430/2400预算嵌套及历史1548秒不同身份
- [x] 实现源绑定、有界原子进度与超时后安全投影
- [x] 保持原始数值调用/检查/receipt顺序的AST等价（仅剥离精确诊断with）
- [x] 冷测试覆盖unknown field、fake PASS、nonfinite、bool/type、oversize、stale writer、context/source drift、partial file、write cap及真实微型sleep子进程被cleanup后进度保留
- [x] 独立代码审查无阻塞；原CappedTrace合成事件回放的字节哈希/计数一致、原sink异常传播保持
- [ ] 主维护者复核后发布main并核对exact head/冷CI
- [ ] 在明确资源与诊断条件下另行审查下一次数值运行；本变更不触发重跑
- [ ] 原始Public M128实际数值PASS/postflight
- [ ] 三模型完整典型block、真实RTL/性能与90%有用wall MAC利用率

诊断写失败会fail-closed终止当前执行，而非静默忽略。单个父进程快照只验证当前context/source/writer绑定与字段范围；单调sequence/count由源绑定Writer在每次更新时检查。它不是抵抗有权限篡改同一私有目录者的密码学日志，也不作为数值授权凭证。

## 本次冷验证结果

135项定向测试normal通过（11.179秒），同135项在`-O`下通过（10.314秒）。包含34项历史归档测试和两个原始sink语义回归；仅CONTROL_ONLY微型子进程与metadata/source composition，没有native数学/真实Public/RTL。

最终launch contract SHA256：`2d315aac0cb48bcc91ceccef947a67369cc08ae781660e638869d9412f431e1f`（285源/12生成）。独立review未发现阻塞项。历史失败source清单中，除了最终launcher层，本次未改任何原source；workflow及batch/resource审计文件不在变更清单。发布与exact-head冷CI由主维护者复核后进行。
