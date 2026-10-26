# 真实 normal_m3：原 SV Core/PackedClient 限定行为 PASS

固定 M3 真正执行已生成 SV 的 Verilator 模型，使用冻结 harness 和脚本 Matrix/memory。**实际时钟行为 PASS**，不是源码/编译/mock 替代；source＋single-TU build 已在 `3ddeabb7536c74a53c055f8815a66a17819fefa4` 发布，本包只追加实际摘要/当前 runtime 门，不重复源码或纳入 M17。

## 直接观测与执行断言分层

- **21689 body +3 reset =21692 rising edges**；独审一次真实日志解析，25,285 事件条件、1260 有序 OBS，36 token/head 组内 Scan576/Fold576/Scale36/Retire72 连续。
- 72 个有效 scoreWrite 均 +0；token2/head0 打印 prefix **[0,1,2]**。max 共 1224 次 -Inf、36 次 +0：每 head 首 retire 为 -Inf，随后 key1/key2 pre-edge 为 +0；不是丢失更新、完整 max/softmax tensor 验收或额外 post-edge trace。
- 四口 payload recheck 为 group12/memory351/PV148/step73，总584；包含跨口重叠/release，**不是584唯一 stall 周期**。
- **1728 memory /576 PV** 字段依冻结源码、已独审编入表、同 ELF 实际执行、被动断言/完整消耗及 exit0 支持。token2 的288 PV请求 A0=**BF16 0x3eab**（1/3），另外两 token 分别为1/1与1/2，其他操作数0。**没有外部 raw PV/memory trace**；不是审核者对实际未记录操作数的独立逐包重放，不能混成直接 OBS 层。
- 1/3 期望采用精确有理数→FP32 RNE `0x3eaaaaab`→BF16 RNE `0x3eab`，独立直接 BF16 整数舍入仅在1、1/2、1/3这些有限值对照通过，不是通用 double-rounding/softmax 证明。
- QK288 steps、36 groups/results/dones、owner1、18432 output bytes。terminal status/reset/debt/8-edge payload hold/3 quiet检查，不等于所有 owner result 字段预期值验收；`--assert`启用也不是全断言分支覆盖。

## runtime 门仅限定当前运行

189 declared+2 self =**191 pins**、63 absence、6 aliases；2283身份检查与保存清理证据闭环。parent runtime **127+9=136**：新4 shutil链 source+4 cache+1保守 struct cache。root Popen 前/终态后保存 **56端点=47 cache候选+7source+2locale** 与11额外 absence，记录逐字相同；**不是56个cache**。

47 cache=46 当前候选（含3 startup）+1保守继承struct；audit查找尝试、候选存在、源码/code关联和真正成功载入不同，不能说47次实际 import reads。实际 parent LANG/LC_ALL/LC_CTYPE 都 C.UTF-8，child固定C是不同环境。`-I -S -B`无`-O`；`-B`禁写不禁读。已知端点不证明任意条件import/dlopen、持续TOCTOU隔离或完整host沙箱；parent8 ELF 与 child5 runtime闭包分开。

新9文件**不回填旧 M1/M2/build Python cache 覆盖缺口**，也不反向否定其分别核实的 native/事件事实。只发布角色/hash，不系统pyc/ELF/locale cache/私有路径。

CPU **39.401106874 s**，outer **39.48238628299441 s**，采样RSS **7,790,592 B**；非连续峰值，host耗时不等于硬件频率/周期性能。

## 仍未通过的范围

`1260/21689 =5.8093964683%`仅本case vector-phase占比；其余 **20429** body edges不证明idle。2880 bookkeeping不是有效MAC数；没有真实FMA分子与完整block硬件周期分母，**90%MAC目标未知**，不能由此占比宣布达标或不达标。

key0/1/2顺序控制被观察，但活动QK对角都为+0，不能排除数据alias或一般W005索引风险。仅3keys、一个packed组，不跨16→17。不是M17、完整Matrix FMA、full128/full29 RTL tensor、21计算/17jobs完整prefill、物理DDR/STA或fullblock利用率。M1/M2限定PASS、软件M128观测域及所有旧FAIL/STOP保持，canonical整体任务不置done。

## 只运行合成文本控制

原checker/reference/generator/tests按公开refs精确hash复用，新入口在临时目录组合4个原字节小源，仅运行选定4项log门与新增7项边界控制，不读真实日志/不执行模型：

```
python3 -B candidates/qwen2_core_client_m3_actual/test_referenced_log_controls.py --repo-root .
python3 -B -O candidates/qwen2_core_client_m3_actual/test_referenced_log_controls.py --repo-root .
```

后继不同active-key数据/更大M/分块边界须新源码、build/run审核及授权，禁止自动串跑。源资格审查自己的fixture标签纠错保留为审查侧历史，不当目标FAIL或新实测。
