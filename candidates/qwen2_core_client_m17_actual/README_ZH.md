# 真实 normal_m17：原 Core/PackedClient 跨 16 尾块限定 PASS

真正执行冻结原 SV 的 Verilator 模型，使用脚本 Matrix/memory 端点，**固定 M17 跨 16→17 控制与限定字段 PASS**。不是纯源码/编译/mock 替代；source＋single-TU build 已在 `ccebf248c9597a489ff36f38d45c379b20aab00a` 发布，本包只追加实际聚合证据及 runtime 门。没有 realMatrix 候选或其执行结论。

## 已发生事实与证据层级

- **404951 body +3 reset =404954 rising edges**。独审一次真实日志解析，190348 事件条件、8964 有序 OBS；216 chunk groups、204 token/head，Scan3456/Fold3456/Scale216/Retire1836。原模型与 SV/archive 不变。
- token16 的 **全部12 heads** 先 keyBase0/count16、后 keyBase16/count1；尾块 local selected=0、global scoreIndex=16、pre-edge max=+0。打印 token16/head0 prefix **0..16**；全部1836有效score写为+0。max直观测为6936次-Inf、2028次+0：每head首全局retire前-Inf，后续与第二chunk继承+0；并非丢失更新，也不是完整post-edge tensor/softmax验收。
- 每个chunk内部phase连续；12个base0-last到base16-first间隔均为80 rising-edge differences，**没有把间隔分解为memory/MAC/idle**。本包省略逐事件cycle/line行，保留原审核hash、聚合事实与边界。
- 四口payload重检 group114/memory7074/PV2740/step359，总10287；可跨口重叠且含release，**不是10287唯一stall周期**。
- **32640 memory /14688 PV /216 groups** 的完整字段由冻结被动C++断言、独审实际编入表、同ELF执行身份、断言计数及完整消耗/exit0支持；不是外部raw PV/memory trace逐包重放。Q/W各1632，K/V各14688；固定1/n（n=1..17）有理数→FP32 RNE→BF16 RNE，1/17为 `0x3d70f0f1`→`0x3d71`，token16有1632 PV消费。有限值验证不是通用double-rounding/softmax/FMA证明。
- QK1728 accepted steps，216results/dones，owner1，104448output bytes；脚本QK活动对角+0/其他qNaN、PV零回复、memory零回复。`--assert`生成并实际运行不等于全断言分支覆盖；terminal不等于所有owner结果payload预期值完备验收。

## 条件下界与实测并列，不构造效率

已公开独立条件下界 **106884 body edges**，实际为 **404951**，实际总404954低于本新版本500000 clock上限。下界依赖完整成功、一个memory debt、响应延迟至少3个不可重叠pre-edge位置、同一FSM的vector phase与这些memory位置互斥；spacing单独不够。下界未包含全部额外工作，**二者比值不是利用率、性能提升或实现效率**，也不推导下一次CPU预算。旧100000版本与所有历史budget FAIL保持。

`8964/404951 =2.2136011517%`仅该case vector-phase占比，剩余 **395987** body edges不证明idle。28512 bookkeeping不是有效MAC；没有真实FMA分子或完整block硬件周期分母，**90%MAC仍未知**。

## 当前 runtime 与资源限定

194 declared+2 self=**196 pins**，63 absence、6 aliases；2279身份检查、保存清理链闭环。parent runtime136沿用精确M3 tuples；root Popen前/终态后 **56端点=47 cache候选+7source+2locale** 与11额外absence相同。47来自历史M3的46候选+1保守struct，**本次无新M17 live import probe，不声称47次实际cache读取**。新M17 reference同胞cache缺失已检查，parent C.UTF-8三项与child C环境分开。

`-I -S -B`无`-O`；`-B`禁写不禁读。已知门不证明任意条件import/dlopen、持续TOCTOU隔离或whole-host沙箱；不回填旧M1/M2/build Python缺口，亦不否定其已分别核实native/事件事实。CORE0不保证系统piped core handler禁用。

CPU **686.463916637 s**，outer **686.6752345440327 s**，inner686.6007166079944 s，采样RSS **8855552 B**；不是连续峰值。固定1200CPU/1500work/1530total/1560outer预算内终态exit0，保存原会话清理/reap闭环，审核者未重跑或发送信号。host耗时不是RTL频率/硬件周期性能。

## 未覆盖与复现边界

真实跨16控制已覆盖，但活动key值同为+0，**不能排除数据alias或一般W005风险**。仍非realMatrix/FMA、full128/full29 RTL tensor、完整21计算/17jobs prefill、物理DDR/STA/面积/90%MAC。M1/M2/M3有限PASS、软件M128观测域及旧FAIL/STOP不变；canonical整体状态不置done。

原checker/reference/generator/tests按10个公开refs复用。新入口临时复制4个小原字节源，只跑8项原Log控制与7项新边界控制，不读真实日志、ELF或运行模型：

```
python3 -B candidates/qwen2_core_client_m17_actual/test_referenced_log_controls.py --repo-root .
python3 -B -O candidates/qwen2_core_client_m17_actual/test_referenced_log_controls.py --repo-root .
```

源码资格里的历史“未执行”是运行前记录，实际结果由独立FINAL绑定；未来不同非零刺激/realMatrix必须另经source/build/run审查，不从此PASS自动外推。
