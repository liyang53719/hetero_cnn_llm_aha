# 官方 fresh M128 同层 pair：r2 源码 / mock 冻结包

当前只交 source/mock，不是 M128 数值参考结果，不是 DUT PASS，也不是执行批准。launch_ready=false、root GO=false。官方 runtime、raw13 payload、完整私有 CONFIG/manifest、权重、tensor、maps、私有原始日志和执行许可都不在本包。

## 固定语义

- 一个完整官方 Qwen2DecoderLayer，一次真正 cold chunk128，原 raw13 embedding rows [0,128)，不是tile16，也不截取任何旧输出。
- 原 config32768 / rope_theta1e6、eager、eval/no_grad、use_cache=false。相同layer及相同x/mask/positions先baseline再observed，恰两次完整forward。
- baseline没有capture Observer/hooks/trace，但安全profile仍在；立即冻结实际y/prob native bytes。三边界重新枚举原input/parameter/buffer，比较对象、存储和native hash。
- observed仍捕获29实际值。只主张实际y/prob及三边界状态比较，绝不扩张为all29 baseline中间值无干扰。
- M128 softmax1536行，causal99072/future97536；原FP32 rowsum2e-5、future正零、finite及其它阈值不改。

## 源码身份与公开适配

SOURCE_SHA256.json中的8项为r2审查后像原字节：capture、pins及6份gate源码。必要的通用Linux系统路径保留，不为脱敏改变运行源码。PUBLICATION_ADAPTATION.json记录排除项与适配边界。

PROFILE_DRAFT.json只是逻辑投影，不是可启动CONFIG。r2独审结论仅source/mock，完整原92项及额外独立9项在原审查环境分别以普通/-O通过；公开包不含该私有历史环境，不能据本包声称复现原92或独立9。

## 公开轻mock子集

仅需Python3.12标准库，从本目录运行：

    python3 -I -S -B run_portable_mock.py
    python3 -I -S -B -O run_portable_mock.py

18项=从原已审测试原文保留的10项终态mock＋8项新的source/逻辑检查。适配与源SHA见evidence/PORTABLE_TEST_SCOPE.json。它不运行完整all29 synthetic数值验证、不导入ML、不启动worker、不读取raw13 payload。测试可能创建临时稀疏文件，仅用于80MiB字节边界，结束后清理。

## 终态输出门与资源边界

全60个输出bin的shape整数投影为50,036,736 B。r2源码中的冻结候选资源仍是4CPU、4/1线程、60CPU秒、90wall秒、树RSS采样1.5GiB及最终成功输出80MiB。它不是已批准执行预算，也不证明CPU/wall/RSS足够。后续final执行profile必须另目录冻结、另作exact review和一次root GO，不能继承这份r2审查。

r2对清理后、postflight后、父receipt/seal精确encoded字节及写入后的实际总量/日志/hash闭合检查；最后仅pending→COMPLETION_SEAL原子改名，不再追加目录文件。假设输出目录独占、worker/子进程均已终止且无外部写者，不宣称通用并发攻击隔离。

成功必须有最终passed receipt、精确绑定的最终COMPLETION_SEAL及一致terminal budget；.pending、.REJECTED和早期候选不算成功。失败保留证据、写最终FAIL receipt且无成功seal；失败诊断可能超过80MiB，不删证据凑门，也不冒称硬磁盘配额。

## 失败历史

evidence/FAILURE_HISTORY_SUMMARY.json保留两类摘要及原件身份：初版测试自身位移常数计数纠正；r1独审发现终态输出门漏父证据与late-write，r2修复。原件仍完整保留，公开包不混入私有原始日志，不把静态发现称成真实数值执行失败。
