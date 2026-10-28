# TEMP：原共同 Top 的 runtime 最终提交 fence

本批在原 Commands/Top 控制通路实现终端提交边界及真实排空观察，不增加执行器或参考计算旁路。**实际一次增量Scala类型编译：2源/994baseline→7新类；最终31源159类=29继承源152类+2新编译源7类，不是31源重编。** exit0、空日志、51.183秒、CPU41.09秒、RSS478900224B，前后各3660严格pin一致。

## 真实提交语义

- 原typed PROGRAM/POLICY：GDN v3 op6对应history/state/final residual；Attention v3 op4对应cache/hidden/final residual。目前只允许**完整128行冷启动**。
- profiles1/2 final output来自真实Residual2 receipt；profiles3/4来自真实allocator+Guard完整MoE retirement及写ACK，并跨原completion.fire保存最终输出身份。readonly预载或中间stage不能充当最终输出。
- 最后一条必须runtime fence，MoE必须预留后续fence命令。旧runtimePrefix缺fence、任意中间末条可能finish OK、MoE缺final Residual2来源快照的源码缺口在实际路径修补。
- Top的私有`runtimeFinalDrained`为十项真实观察：physical、Dense、arithmetic、selection、metadata reader、Guard busy/reserved、allocator reserved、lifetime、N1 image。不是Host grant、时钟计数、预期完成数或retained receipt。
- validate等待排空，再保持终端completion。**原host-facing completion.fire**才是原子提交沿，绝非随后单独result.fire；此时重核完整cfg/transaction64/末条/currentfault/实际drain/不可重复提交，一拍提交GDN双根+generation或Attention cache/context/length+generation。失败不半提交。

## 晚故障、结果与冷启动边界

held completion不得撤回或改payload，晚fault在实际握手否决根提交；resident resetRequired侧带现覆盖runtime fence及非零profile finish。成功提交之后更晚故障不能假称回滚既有根。

单独Host result首次valid前资格化status：无commit、fault或未drained则快照Protocol并poison；一旦offer，payload保持，后发故障由原resetRequired侧带报告。profile0结果时序/算术语义保持。

不把原仅7项GDN/6项Attention参数表冒充完整runtime checkpoint绑定。新checkpoint持久cold-only，完整carried-state参数身份尚未实现；后续非零profile launch仍拒绝。**profiles1..4全局Unsupported launch seal保持关闭**，不能据此声称完整block实际执行或根已在DUT提交。

## 公共命令数及固定资源

official public21精确21条限制仅profile0；非零profile仍受通用1..64及最后fence约束。原编译期开关的模型特定命令数分支不作为runtime支持证据。原profile0合法形状/角色和FP32存储保持。

同4096 Matrix MAC、共享32-lane物理服务；不改FP32顺序/BF16物化，不新增数值buffer、FPU、Matrix、DMA、bank或formatter。新增控制寄存器含Host844bit、transaction64、result status8bit（已知916bit小计），另两个DecodedTensor、三个标志、比较器/mux及1bit私有drain输入；不是零面积，也不是综合资源/时序证明。MoE路由、官方expert IDs和tie policy未改，tie契约仍待定。

## 检查、历史与复现边界

普通Python/`-O`：11协议模型（含350命令数边界）、17源码负控、Top1024布尔组合/10负控；独审另512有限生命周期案例，另4项当前准备metadata检查。这些不是Chisel/DUT协议或数值证明。

**保留检查器缺陷历史：** 原checker首次因legacy重复片段漏掉删除首处，后改为当前输入快照的片段计数；发布独审证明外部先删一处重复root-write后，raw checker仍会自校准并PASS。这不是已编译Scala源缺陷。公开checker固定使用精确已编译源提取的字面计数，外部重复片段删除也须拒绝；包hash另独立守护。没有改动原冻结checker或源码，未把原检查回写成更强PASS。

原独审`before_count_scope`绑定较早Commands hash，保留为历史，不当作最终源审批；最终源review及实际receipt/class/closure/source绑定明确分开，作者绑定文件不是第二份独立review。

前代993+8=1001，整族替换Commands4+Top3类后994=842历史+152继承。公开2新源、23已公开继承、6 requires-parent。当前class/source/tool闭包精确不等于历史JSON全图PASS；缺失原compiler receipts与budget-skipped边界未补齐或重扫。

`REPRODUCTION.json`只提供精确argv占位配方/caps，仍需父级完整source/build/class闭包、106 jars、314-file JDK及原严格有界supervisor；不上传二进制/权重、不宣称fresh-checkout完整复现，不是新启动授权。原runner保存的owned终态/cleanup证据仅后验复核，不重执行cleanup或重观察已结束handle。

从包目录运行，需保留相邻已发布`host_runtime_ffn`的精确Top源：

```sh
python -B verify_package.py
python -B check_final_fence.py
python -B check_top_fence.py
python -B tests/test_final_fence.py
```

将`python -B`替换为`python -B -O`复核优化模式。

**未运行Chisel elaboration、IR/RTL、DUT数值/协议或QoR；完整五profile M128 Chisel与同RTL仍0/5。** 无利用率新实测。后续须同一Top初始化/位宽/组合环/物理资源、冷启动完整128token数值与同刺激RTL，再评估完整carried状态合同；全局launch seal不能仅凭类型编译开放。
