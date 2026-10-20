# TEMP：Owner v3 driver-only 重链与有限运行合同

本候选只准备一轮 fresh driver 编译、链接、owner 局部运行。已有 owner model 的普通 archive 与 3 个 Verilator runtime objects 来自正式审过的 cache 编译；本轮不调用 make/Verilator，不重编 model C++、PCH、child library 或 backend。旧 driver.o 与旧 executable 不复用执行。

## 精确复用来源

原 actual 审查：review_owner_cache_actual_20261019T2348，MANIFEST 786 B / 0a832dcb156af5f8df8620b2b43846dd0071bd36afdf42c0b9e3091a7fafbdcd，SUMMARY 9476 B / 14bb3cbebaa5002dad596c235db675cec66904a60e0ec8c8101d735ac853f1b1；有限结论为 ACCEPT_ACTUAL_OWNER_CACHE_BUILD_NATURAL_ZERO_RUNTIME_RESET_REQUIRED_HIGH_ONLY。原 run 失败及未知上游原因完整保留，不把旧整轮状态改成 PASS。

固定 12 个输入共 24,151,608 B：2 个 generated headers、6 个 Verilator headers、3 个 runtime .o、1 个 VQwenOwnerKernel__ALL.a。该普通、非 thin archive 已含 model 和层级 child objects；链接不再另取 child archive。每个原件及 fresh 副本逐 size/SHA 校验，同一已验证 buffer 用于复制；原完整 608 项树（599 regular files，493,245,462 B）在各阶段前后复核，原 generation 来源树与固定 source closure 仍保留原门。

原成功 build log、owner_micro.d、top makefile、实际 receipt、树 inventory 及正式 review 均固定身份。生成 makefiles 只作为来源材料，不参与本轮调用。新 driver 的 include 全指向 fresh fixture/generated/Verilator header 副本，不能继续读取旧绝对 fixture 路径。

## 调用和输入门

新 driver 来源：owner v3 七件 production manifest 1019 B / 67ae76c51aacbcabb47bdf10cc59a8d1cb7c506760907d506c7f09681279b6fc；仅 owner_micro.cpp 与 v2 不同，六个接口/观察/辅助原件同字节。v3 SOURCE 审查 review_owner_micro_core_v3_20261019T2356，M1181/6b109cd2f3b65e6f0b57327966f595f4703edf9b5c05f8518d27c58a7a8430ec，S4658/947fb90d4aeae27c3b727efab7ea4b2784a0b367201a5453363da2af8e7aecf3，GO_OWNER_MICRO_V3_FALLING_LOW_SETTLE_SOURCE_ONLY。

编译保留原成功 g++ 的宏、-std=c++17、-O0 和有限 warning flags，仅替换 fresh include/source/output 路径，并沿原已审 relink 使用固定 -B compiler-search 与 39 项系统依赖。编译后只接收 fresh ELF relocatable object；新 .d 必须恰为一个固定 target、12 项精确依赖及顺序，缺项、多项、旧 fixture、PCH 或额外源都拒绝。

链接顺序保持：新 owner_micro.o，verilated.o，verilated_dpi.o，verilated_threads.o，VQwenOwnerKernel__ALL.a，-pthread -lpthread -latomic。新 executable 仍用原有限 ELF reader 核 interpreter/needed 库，link 后、run 前后重验内容身份。原系统 readonly mount profile、binding、编译器及依赖门不放宽。196 端口与 95 观察声明仍消费原 parser；固定 root header 使用已审的精确 4,630,258 B 同 buffer reader。

run 仍仅接固定 N0 与 Wq 两路径；原 full input hash 不变。driver 最多 500000 局部 cycles；300 秒窗口不保证达到预定目标，未知吞吐不作完成承诺。完整 bounded JSONL 原样保存，包含 raw_high_before_settle 的新增字段也不在 caller 里解释。自然 0 仅说明三阶段按本合同结束；目标、根因或数值资格仍需 actual 独审。

## 预算与首错

唯一总墙钟 540 秒，从父 outer 最早 t0 起计，包含加载、hash、原树复核及 staging。阶段完整窗口为 compile120、link60、run300，最后保留60秒落证；各 native work/CPU 分别105、45、285秒，原15秒监督清理/后验余量不变。阶段前和 preflight 后都必须剩下完整当前窗口加尾限，不足则 INCOMPLETE；窗口不会重置总 t0。

全程单 CPU、AS 6 GiB，原 MemAvailable ≥8 GiB / disk available ≥3 GiB 准入每阶段重核。父普通 Python -I -S -B 入口为530秒 TERM +5秒 KILL +5秒 parent receipt，合计不超过540秒。父 outer 不使用 -O。

首个异常始终优先，完整阶段日志和固定安全诊断保留。secondary log/save/restore 错误不能改写原首错。run 非零立即停；不存在恢复旧 owner/Host 状态或补跑未完成 job 的声明。

## 验证范围

READONLY_REUSE_RESULT.json 是只读原现物回放：608项树、12项输入、95声明，以及旧 .d 经明确路径投影后的固定12依赖规则通过；该投影不是新编译器产生的实际 .d，新的真实 .d 仍必须经过后验门。未复制实际24 MB库存，也未执行 native。定向 pure-mock 冷测的最终数量及模式见 COLD_RESULT.json。

本候选实际尚未执行。full_job/full_block=false；historical_host_failure_reproduced、official/application/typed-to-RTL 均为 null。现有 Host 失败和局部 owner 失败不合并为同一原因。私有 binding、COMMAND、outer、机器路径、库存、数组及日志不公开；SOURCE 与内容审通过后，才由父线程按已授权有限合同进行一次实际调用。
