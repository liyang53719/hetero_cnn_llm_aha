# Current work breakdown on consolidated main

## Closed and accepted

- L0-L3 control/upstream/wrapper/shared-fabric baselines.
- L5.1 Block128 component E1/E4, with effectively zero timing margin.
- L5.2 Revision8B-B 512-lane, five-stage/five-context Matrix E1/H3.
- L5.3 Controller and Block32-weight component E1/E4; the trace bridge is accepted only as non-single-simulation evidence.
- L5.4 one- and two-lane fused-SiLU standalone E1/E4 candidates.

## Current local-agent critical path

1. Build one integrated q128 QK -> Block32/Block128 M/L/O -> PV simulation using the deterministic vector pack.
2. Extend to q384 and reviewed q1024 rows, exactly 43,008 merges and random backpressure.
3. Freeze SiLU edge behavior, measure Matrix-producer stall and select one/two lanes.
4. Execute the 11-case integrated E3 matrix.
5. Run 28-layer q1024 >=300 token/s within SRAM and DDR limits.

## Sandbox v7.0 completed

- Attention pack: 1,536/180/108 q128/q384/q1024 rows, max error `1.0728836059570312e-06`.
- SiLU: 625 special vectors and 160 stall scenarios; two edge policies require review.
- Quant: 8,192 arbitrary K-tail schedules plus source-ready sequencer RTL.
- State: 5,000 adversarial transactions, generation wrap and zero page leak.
- E3: 11 coverage-driven cases and mandatory counter contract.

## Other local dependencies

CNN/AHA E1/E4; pinned llama.cpp parity and quant RTL/PPA; production state RTL/iDMA E3; official Qwen3.5/Qwen3.8 backends; real llama.cpp/GGUF; SRAM/post-route/PVT/SAIF and final Archspec promotion.

## 2026-11-13 当前云端 hetero 主线（中文状态，覆盖上文历史资格的适用范围）

上文历史组件/控制/局部接受不等于当前五块M128完整数值通过。当前仅hetero，固定4096 Matrix MAC、同一硬件定义/接口/资源与统一RTL身份；五块完整原Chisel为0/5，完整RTL与有效MAC利用率未测。

- done（范围限定）：新完整Host+17native+AXI checkpoint局部恢复；旧冻结Qwen2首RMS40/128行实际写回245760字节与独立参考相等。不是完整首RMS或block。
- done（结构限定）：独立ascending一致修复候选的Scala/Chisel emit/HWIR lower成功，全部接口/extern及105assert声明、17native保持；4项静态/边界测试通过。不代表数值或RTL通过。
- ongoing/TEMP：该候选仅改变Attention Commands/lease/router三处顺序绑定，norm C1/C2及RoPE B1保持。新源码/IR身份不得装载旧checkpoint或迁移旧通过；当前执行镜像未替换。
- ongoing/INCOMPLETE：L3双契约独立参考已到postnorm与完整FFN gate/up；旧ascending与安装pair序的数值差异保留。尚缺SiLU/down/final残差及原Chisel完整执行。
- blocked：原29364拥有线程poll为Unknown、无终态，未重复恢复。需确切终态或用户明确允许旧状态未知下独立恢复；下一管理器共享锁/原子发布已通过假负载测试，不能反证旧无锁任务已停。
- blocked：L0原underflow FAIL保留；35B两块真实权重缺失；MoE同分契约未擅定。
- todo：在新候选身份上完成五块M128原Chisel完整数值链，再冻结源码/输入/参考/配置，生成同一份RTL并同刺激回放。32lane共享Vector方案不减少4096 Matrix，仍须新统一硬件全重测。长档1024/1224待明确，不阻塞128。

本轮证据及精确局限见 [19:33摘要](round_20261113T1933/SUMMARY_CN.md)。源码/数据/原始日志仅本地，远端仅保存允许摘要与计划；未发布候选实现。


## 2026-11-13 20:33 当前状态（INCOMPLETE）
- done：L3独立分阶段Python双参考到最终M128×1024输出，56阶段文件hash串联复核；两项目契约最终347处BF16差异，不是官方框架精度/硬件PASS。
- done：20块真实checkpoint离线validator接管理器，4组/9错误拒绝；原fromOwner局部Chisel发射RTL映射1536向量通过。范围均不等于完整Host执行。
- ongoing：五块同4096完整原Chisel数值仍0/5，新ascending候选身份隔离，原参考不切换。
- blocked：29364缺终态，未知旧Host不重复恢复；35B真实权重缺失；L0原underflow FAIL保留。
- todo：获得原任务终态或明确允许未知旧任务并发风险后推进真实Host；候选完整真实前序ACK路由及五块重测，之后冻结同刺激RTL回放。不得将升序称唯一官方归约顺序。
- cleanup：核清单、工作区clean，清理0；没有完整block利用率实测。


## 2026-11-13 21:33 当前状态（INCOMPLETE）
- done：Qwen2原M128真实norm→完整QKV+bias独立参考，FP32存储/输出保留；不是Host数值PASS。
- done：真实历史恢复包父链及发布负例7项/13类通过；没有新DUT周期，不推定旧进程终止。
- done：新ascending候选Arc/llc完成，补官方ArcRuntime链接后真实17实例12周期reset-idle通过；105strict与绑定保持。未执行活跃profile、未迁移旧checkpoint。
- ongoing：五块完整原Chisel仍0/5；Qwen2独立参考后续RoPE/attention/FFN待续；候选需真实前序ACK链与完整五块验证。
- blocked：29364终态未知；35B真实权重缺失；L0原underflow FAIL仍在。
- cleanup：清单已核/清理0；未测完整RTL及完整block有效MAC利用率。


## 2026-11-13 22:33 当前状态（INCOMPLETE）
- done：Qwen2完整FP32 RoPE/因果QK独立参考，保原16lane折叠顺序；softmax/PV未执行。
- done：候选启动前16依赖pin校验及16坏pin拒绝；真实33周期非法命令AXI拒绝/背压。19strict回调注入仅callback资格，不是算术fatal。
- done：3个真实进程os._exit发布崩溃点保留合法完整LATEST，无新DUT周期。
- ongoing：五块原Chisel仍0/5；候选真实完整链与savable17新身份恢复待补。
- blocked：原29364终态未知，不重启；35B缺权重；L0原underflow FAIL保留。
- cleanup：清单已核、清理0。完整RTL数值及完整block MAC利用率未测。


## 2026-11-13 23:33 当前状态（INCOMPLETE）
- done：Qwen2原21命令算术路径的分阶段M128独立参考闭合至最终FP32输出cbda6ba0…6cb5，20实体hash串联。KV append仅参考复用，不冒事务/硬件通过；L3独立双参考已完成。
- done：新候选仅重链接savable17；cycle10真实AR已接受/R pending，新schema完整20块fresh-process恢复后32周期轨迹及20块终态hash全等，13负例通过。仅合成单beat非法命令、scratch空，不是全profile或非空写回资格。
- ongoing：五块完整原Chisel仍0/5；同4096候选完整真实数值及五块重测待完成，独立参考不能代替DUT。
- blocked：旧29364仍Unknown未重启；35B真实权重缺失；L0原underflow FAIL保留。
- todo：保新候选代码/输入身份，补完整真实数值链，先模型通过再冻结同刺激RTL。不得将墙钟速度当MAC利用率。
- cleanup：清单已核清理0，完整RTL/完整block有效MAC利用率未测。


## 2026-11-14 00:33 当前状态（INCOMPLETE）
- done：新候选真实Qwen2正常前缀cycle439/4真实beat保存20块，fresh-process续120cycle完整轨迹/20hash相等。scratch0、首RMS未完成。
- done：L0 M128 QKV/Z独立参考恢复；Dense末BF16转换参考过严断言已按实际政策纠正，保留失败及8见证。后续Conv仅现有逐步下溢候选参考，原strict/head4 FAIL不变。
- done：profile1–4 metadata原12pins一致；20静态MoE geometrycase满足当前物理尺寸，不代表执行资格。
- blocked：当前判据实际拒profile3/4，尽管MoE模块存在；不能盲开resident/transposed或切OfficialBF16。真实权重仍缺。旧29364状态未知不重启。
- ongoing：五块原Chisel完整M128仍0/5；先验证已有真实MoE topology的独立安装判据/phase/算术链，再统一重测。
- cleanup：核清单清理0。完整RTL和完整block有效MAC利用率未测。


## 2026-11-14 01:33 当前状态（INCOMPLETE）
- done：当前候选从cycle439无reset续至9266首64B真实ACK保存，fresh-process续120周期至9386/320B与独立参考0 mismatch；轨迹及20块终态hash相等。仅80个FP32字，首RMS未完成。
- done：L0候选完整M128 Q/K归一化独立参考，实际16-head选择ascending/gate0；不含gate，不是完整RawPrep，原strict FAIL不变。
- done：MoE离线契约4测试/12负例/640尺寸通过；原router exp/tie未资格，因此未开安装门，不改PyTorch基线。
- ongoing：五块完整原Chisel仍0/5，真实完整链/RTL及全block利用率未测。
- blocked：旧29364未知不重启，35B缺权重及router资格；清单已核清理0。


## 2026-11-14 02:33 当前状态（INCOMPLETE）
- done：当前候选从已保存9266续至10266/2432B再保存，fresh-process120周期至10386/2688B与参考0 mismatch；轨迹与20块hash相同，仅672个FP32字，未完成首RMS一行。
- done：L0实际gate0独立参考2048 gates完成，复用Q/K组成M128×6400 prepared；仅逐步下溢候选Python，历史strict FAIL保留，Chunk未做。
- done：MoE冻结源pin复核、8项独立数值边界诊断；当前Torch运行闭包缺失，未重验原kernel，不改topk契约或开准入门。
- ongoing：五块完整原Chisel仍0/5，同4096，完整RTL/有效MAC利用率未测；旧29364未知不重启，35B权重缺失。
- cleanup：清单核验，清理0；仅发布允许摘要/计划。


## 2026-11-14 03:33 当前状态（INCOMPLETE/局部数值FAIL）
- done：当前候选从10266续至11831，首RMS第1/128行6144B实际ACK与参考相等；新进程120周期轨迹及20状态hash相同，未完成首RMS。
- FAIL（独立参考）：L0当前候选输入按实际strict Chunk0执行，head0 phase5完成、phase6 row52/colBeat1/lane12最终pair Mul产生UF|NX。未到phase7/head4，不是历史同刺激重现，未改策略。
- done（诊断）：2150输入精确P7重放与现存候选同字；相对理想exp20样本不同，非Torch/硬件资格，原门禁不变。
- ongoing：五块完整Chisel0/5，统一4096，完整RTL/利用率未测；旧29364Unknown不重启，35B权重与原runtime缺失。
- cleanup：清单已核，清理0，仅允许摘要/计划提交。


## 2026-11-14 04:33 当前状态（INCOMPLETE/有界执行FAIL）
- FAIL：新Host第二行有界任务76291触发110秒超时，未保存新包；11831首行保底完好，未扩大预算重试。
- TEMP：本地补每1000周期安全排空/保存及90秒提前收尾控制，只语法检查，尚无执行/恢复资格。
- done（局部RTL）：原Scalar11事务及背压验证通过，P7无导出primitive flags；Mul和MulIeeeRne原UF错误策略区别已实测，不是完整Host/MoE资格。
- FAIL保持：Chunk两个normal输入乘积tiny/inexact、strict策略正确拒绝；无不改契约可转PASS的参考bug修复，未改策略。
- ongoing：五块完整Chisel0/5，同4096，完整RTL/利用率未测；旧29364Unknown，35B权重/原runtime与MoE资格缺失。
- cleanup：清单已核清理0，只允许摘要/计划提交。


## 2026-11-14 05:33 当前状态（INCOMPLETE）
- done：periodic控制统一后续AR背压刺激；95163真实续至20680，9个完整包，最终包fresh-process120周期轨迹/20hash相等。ACK仍首行6144B，第二行未完成，前8包只hash核。
- done（局部RTL）：Bank4例确认strict UF拒绝/7周期背压；adapter71例转发/身份隔离通过，但lease/Core为合成peer，不冒完整联合链。
- FAIL保持：Chunk原数值策略未改变，历史head4不迁移；五块完整Chisel0/5，同4096，完整RTL/利用率未测。
- blocked：旧29364Unknown，35B权重/原runtime与MoE数值契约缺失。
- cleanup：清单已核清理0，仅允许摘要/计划提交。


## 2026-11-14 06:33 当前状态（INCOMPLETE，持续在途）
- done：真实RMS前2/128行12288B参考零差异，23515包恢复验证；随后continuation01完成30703安全包及fresh120周期/20hash差分，ACK仍两行。
- ongoing：continuation02原23287立即接30703，不等整点，不重复旧29364；每1000周期保存、80秒收尾，沿原身份核后续。
- done（共享Scalar子链）：原adapter→真实Core/Scalar10例实际计数/背压通过，lease仍合成，不冒完整MoE授权。首次test采样过早失败保留，真实trace证实寄存计数下一沿更新。
- blocked：strict L0不能跳phase6故障；另立finite-gradual是新决策，未做。35B真实权重/冻结runtime及MoE契约仍缺。
- 五块完整Chisel0/5，同4096，完整RTL/利用率未测；清单已核清理0，仅允许摘要/计划提交。


## 2026-11-14 07:33 当前状态（INCOMPLETE）
- done：同候选连续至88401，首RMS 7/128行43008B零差异，最终包fresh120周期/20状态hash相同；每1000周期持久保存，继续原owner串行执行。
- done：新增L3真实输入lazy loader，13段全字节/22命令/261描述符核验；693正读、39负读，中间tensor未初始化，未跑L3 Host。
- ongoing：定位真实MoE lease allocationValid漏赋、8路常false，最小候选验证中，未改安装门或数值契约，不冒完整授权链通过。
- 五块完整Chisel0/5，固定4096；L0 strict FAIL、35B缺权重/资格，旧29364未知不重启；RTL/有效MAC利用率未测。清单已核清理0。


## 2026-11-14 08:33 当前状态（INCOMPLETE）
- done：连续真实首RMS25/128行153600B零差异，cycle298932整包及fresh120/20状态一致；原54419持续接续，不重复29364。
- done（候选结构）：MoE八路lease漏赋修复完整Host emit/lower成功，真实8路依赖、17native/105断言/接口核验；未替换运行库、未做完整授权或数值。
- done：L3原22命令/65根解码审计与负例、新runtime配对sidecar，避免选错归约参考；不冒实际准入。
- ongoing：五块完整Chisel0/5，同4096，完整RTL/MAC利用率未测；L0 strict FAIL与35B缺权重/契约保持。清单已核清理0。


## 2026-11-14 09:33 重连恢复（INCOMPLETE）
- blocked：环境回退丢失Nov14包及执行库，37765终态Unknown，历史50行不可继承可恢复PASS，不重复完整Host。
- done：155源重hash、Qwen2桥5测试、L3桥13段/680正读39拒绝/22命令65根独立重建重测。
- TEMP：MoE新两行候选typecheck/4静态测试通过；Host新恢复源码在途，均非旧丢失身份PASS。
- 五块完整0/5，同4096和数值契约；清单已核清理0，完整RTL及MAC利用率未测。


## 2026-11-14 10:33 新恢复候选（INCOMPLETE）
- done：新Host emit/1.62结构lower成功，接口17native及105断言数量保持；8项谓词因GQA路由依赖改变，语义等同比较未通过，不冒断言等价。
- done（独立参考）：Qwen2和L3完整M128输入RMS重新Fraction计算/核hash，不是Host或全block数值。
- TEMP：MoE源切片编译/发射与7规格测试通过，缺Verilator未做动态RTL资格。
- blocked：37765未知、完整执行库/包缺失，未重启完整Host；五块0/5、同4096，L0 strict/35B阻塞保持。清单已核清理0。


## 2026-11-14 11:33 执行闭包恢复（INCOMPLETE）
- done：官方Arc1.163及Verilator5.032完整pin/version通过，恢复179源码文件；非Host执行资格。
- done（局部RTL）：GQA源切片1280组合/hold正例及两原assert负例验证，非完整payload保持或Host等价。
- done：L0真实loader重建，14权重/16段、544正读56拒绝及原17命令219描述符核验。
- ongoing：wrapper生命周期最小修复、真实17/savable闭包重建；未知37765不重启、不继承50行。
- 五块完整0/5，同4096，L0 strict/35B阻塞保持；完整RTL及利用率未测。清理0。


## 2026-11-14 12:33 执行闭包（INCOMPLETE）
- done：927源逐pin、真实ICG编译及接口时序/生命周期测试；Matrix/DMA未编。
- TEMP：17 typed桥编译/字节负例、共享mock transport测试，新Arc脚本完整preproc保留106终止条件与17/17边界；未验证真实shared17/Host运行。
- done：三真实profile统一read接口485差分/171拒绝，未初始化中间值和35B缺输入fail closed。
- 五块完整0/5、同4096，旧37765未知不重复，L0 strict/35B阻塞保持；完整RTL/MAC利用率未测，清理0。
