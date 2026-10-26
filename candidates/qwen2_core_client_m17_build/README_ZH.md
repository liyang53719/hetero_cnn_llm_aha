# 固定 M17 chunk-aware 源码与 single-TU build-only

**PASS仅覆盖：**最终 M17 源码/整数期望/小合成资格，以及一次实际单TU编译链接和静态表闭包。**本批没有 M17 run、跨16实际行为或数值PASS**；source review当时“未编译”标签保留为历史，后来的build事实单列。原M1/M2/M3限定PASS、所有旧FAIL/STOP和canonical状态保持，整体任务不置done。

## 不是只把 m 改成17

`M3_TO_M17_SOURCE.patch`精确、可逆地修改已公开M3重建源；7个小文件原字节发布（6 Python＋910B `stimulus_m17.hpp`）。独立driver仅用accepted-group ordinal计算token/head/base/validCount：前192组为token0..15各12heads，后24组为token16每head的base0/count16、base16/count1。它不读取DUT observation或oracle表来产生tile。

原M3单chunk offerTile规则不能直接用于M17。新driver按local validCount填活动对角+0、其他位置qNaN；oracle以独立分层iterator产生期望，独审另外使用flattened ordinal推导。新增被动group/tag/globalbase检查，沿用已有observation_key作为keyBase；没有新增RTL探针或改原Core/PackedClient/Matrix数学。

- K读取必须chunk-major，再depth-major，再causal-key；token16先16keys的128次K读，再key16的8次K读，不是跨全部17keys的depth-major。
- 每head第二chunk继承max +0，不重置为-Inf；local selected回0，但有效scoreIndex为global16。期望token16/head0 prefix为0..16。
- Q/W各1632、K/V各14688，216groups、32640memory、14688PV、8964vector、1836retire、104448output bytes，**此处均为源码/静态期望，不是实测事件**。
- 独立整数RNE对照仅覆盖1/n、n=1..17；1/17期望FP32 `0x3d70f0f1` → BF16 `0x3d71`，不证明一般double-rounding/softmax。生成的1,929,176B `expected_m17.hpp`不上传，由小generator精确重建；只包含脚本零输入接口描述，不是模型权重或真实tensor。

源冻结前曾误把Qbase从0x100000替换为0x500000，已在最终字节恢复；log连续性键由(token,head)改为(token,head,keyBase)，允许两chunk之间真实K读间隔。draft记录保留，非实际DUT失败或旧证据修改。memory/PV完整字段未来只由执行harness被动断言支持，没有外部rawpacket重放承诺。

## clock新版本与条件下界

新独立case总cap **500000=499997 body+3 reset**，不是延长任何旧失败/运行进程；旧100000总cap不变。独立静态证明在原单debt端点和同一registered FSM、不earlyfault/abort且完整成功排空前提下：

1. memory accept于a，最早response为a+2；a/a+1/a+2三槽各处memReq/memRsp，下一accept不早于a+3；完整成功必须包含最后response。
2. 这些memory槽与同FSM的vector states互斥，故可加 **3×32640+8964=106884 body**，加reset为106887；旧106882仍为更弱保守界。**只知accept间距不足以直接相加**，非重叠FSM证明不可省略。
3. 这是完整成功的条件下界，不是提前FAIL耗时/预计总周期/CPU估计/更大cap能完成的保证。改变端点延时、并发debt、异步vector、clock计数或早退会破坏前提。

1200CPU/1500work/1530total/1560outer只是独立run提案，本包无run候选/GO/实际结果。新的source资源上界只限成功格式日志，不代表任意失败diagnostic；本次编译耗时不能线性外推M17运行。real Matrix shell草稿/实现不在本包，也不获编译或行为PASS。

## 本次真实compile/link

- 14不变staged输入：原7生成header、36-member模型archive、2runtime对象、新M17 cpp、原ABI、expected header、stimulus header。仅新增object/MMD/ELF，**17文件14,742,024B**；全run29文件14,765,656B。
- ELF **4,514,920B**，SHA256 `1eefdc81df6505cbd6f42fd1eda643adaf2d07687c40a56733ec88ed2b1b5075`。仅hash，不ELF/archive/object/生成模型bulk上传。
- object和ELF内216/32640/14688/8964表的语义字段独审匹配，Boolean精确0/1，padding未验。每份reference table共1,168,272B。**编入静态常量不证明driver执行、跨16实际行为或断言执行**。
- 200 model-marker函数名非硬件模块数；5已知native providers/13版本边、10项MMD literal依赖不等于live loader/dlopen或完整系统头trace。无make/codegen/旧模型TU重编/newPCH/model执行。空log非warning-free，stock9个-Wno保留。
- CPU25.599190959s、outer25.89357326697791s、采样RSS529,530,880B；5408前后pins、19inventories、1129aliases/285absence、原group清理链通过。采样RSS非连续峰值；本次build240CPU/300work/330total/360outer，不混为旧M3预算。

## runtime复用而非历史回填

本次parent runtime202，复用已公开M3 build的46端点（42 normal-cache候选＋4source）、10额外absence及C.UTF-8 locale前后门，外部记录相同。import AST/已审code-source关联复用，没有新probe或cache编译。42不等于42次已证实import opens；-B禁写不禁读，端点前后不证明连续隔离/所有条件import。旧未pin cache缺口不回填，parent8 ELF与native5闭包分开。

## 不运行模型的重建

依已公开codegen/M3 helpers及其transitive refs先取得 `M3_SOURCE_OUT/m3_source/{m3_main.cpp,generated_abi.hpp}`。本helper核两者和所有refs精确hash，再应用delta并生成expected header：

```
python3 -B candidates/qwen2_core_client_m17_build/rebuild_sources.py --repository-root . --abi-header M3_SOURCE_OUT/m3_source/generated_abi.hpp --m3-main M3_SOURCE_OUT/m3_source/m3_main.cpp --output NEW_M17_SOURCE_OUT
python3 -B NEW_M17_SOURCE_OUT/m17_source/test_m17_contract.py
python3 -B NEW_M17_SOURCE_OUT/m17_source/test_m17_build.py
```

`-O`只重复小合成模式，不是实际runtime。helper拒绝既存输出、symlink、穿越/hash漂移；生成失败可能留下新建部分输出而不改输入。role化compiler argv/环境是复现recipe，不是完整私有runtime或执行授权。

即使未来M17通过，仍是一个attention owner＋脚本Matrix/memory；活动值全0仍不能排除key数据alias/一般W005风险。28512 bookkeeping非MAC；fullFMA/full128/full29/fullprefill/物理DDR/STA/频率/90%MAC均未通过。
