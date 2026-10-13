# Qwen3.5-35B-A3B L0：真实 RMS→完整 QKV→Conv4/SiLU 软件前缀

## 范围和固定资源

基于 main 9765457，复用现有 0.8B typed Conv 控制和 Scalar 算术，增加 35B
8192 通道准入与官方来源身份。35B pinned 官方 causal_conv1d_fn 的完整 AST 与
0.8B 相同，但不因此继承数值 PASS。只获取官方 shard14 的 conv1d.weight：
BF16 [8192,1,4]、65536B；固定 revision、header、range 和内容摘要均由获取脚本验证。
不下载专家权重。既有 QKV 原始 payload 和完整 N8192 官方参考保持独立 SHA 身份。

实际共享同一 TypedMemory、Matrix4096、Vector16、Scalar1。RMS 使用 ConvScalar
继承的同一 SharedScalar；QKV 真实 producer 完整 ACK 并发布的 MemoryRegion
直接作为 Conv 输入。Conv 不从参考或先前输出导入输入。每组 32 通道的本地资源
仍是 weights/history 各128 BF16、input/output 各32 BF16，8192 通道使用外部地址
推进，不把全张量诊断数组冒充硬件本地存储。host 捕获的 preactivation 只供比较。

冷窗口的 65536B history_out 全部写 ACK 后仍为未发布 staging，generation=0。
它保存最后四个原 QKV token，不是 SiLU 输出。只有未来完整 block fence 才能提交。
本轮未实现 warm/carried、Prep/head 映射、GDN chunk、gated norm、O/residual/MoE。

## 生产 Chisel 差异与不能关闭的门

生产 GdnConv4Owner 的 channels 参数域支持8192，固定组资源可复用；原 Chisel
局部 finish 成功会置 historyCommitted 并增 generation。当前 typed 协议故意将其
改为 staging；这项差异尚未接入生产 Chisel 的完整 block 原子提交协议。不能把
局部 done 或本轮软件前缀当成公共 Command128、完整 Chisel block 或 RTL 已通过。
Scalar 固定算术的负 Conv≤-80 与 legacy Mul inexact-underflow 拒绝条件均未放宽。

## 精度和回归门

真实观测 Conv FP32求和后的 BF16边界，再观测 SiLU；二者与独立固定配方逐bit比较。
同一实际 QKV 输入执行原官方完整 [1,8192,M] fallback，Conv/SiLU 采用冻结合同
原门 ≤1 BF16 ULP；原官方 QKV 到 Conv 的端到端门 max_abs≤0.03125、mean_abs≤0.005。
同输入 raw history 要求逐bit相同。正负零数值距离为0，但位差单独计数，不宣称位精确。
固定配方、官方同输入和官方端到端三组各3份 raw reference 留在 ignored work 并记录SHA。

首个 M16 候选 runner 漏了同输入 1ULP 限制，只检查了 max/mean。独立审查发现后
保留原实际输出及运行源摘要，以独立锁定执行报告 SHA 的后验校验器严格重比，不重复
昂贵前缀计算，也不把旧宽门 PASS 继承为严格验收。新增2ULP极小差反例，确保即使
绝对误差门通过也拒绝。后续 M128 runner 直接执行严格门。历史首次启动还记录
Torch 合成相对 __file__ 导致算术前冻结失败；独立后验 CLI 首次因 interop 非1拒绝。
所有失败保留，不覆盖或改写旧报告。

## todo / ongoing / done

- done：8192通道固定来源准入；实际共享 Scalar/内存接线；history staging；最后 ACK
  失败不提交；原 1ULP 防回退门；M16实际前缀及独立严格比较；M128实际严格门及冷回归。
- ongoing：独立审查、小批发布和精确SHA的CI工件核验。
- todo：35B L0后续 Prep/GDN/head映射及完整 MoE；L3完整block；五block M128联合门；
  生产Chisel和RTL同刺激回放；固定资源完整block周期MAC利用率≥80%、争取90%。

每case保留 Matrix useful/executed MAC、Scalar操作与ACK、软件tick、宿主秒数。
模型没有可靠硬件cycle、busy、lane duty、stall或overlap时保持unknown，不把宿主时长
或软件调用数转换成RTL利用率。M16只有16逻辑行，Matrix物理pad128；M128是真128行。
Conv的四tap Scalar乘加另外计数，不能混入Matrix资源分母冒充更高利用率。

## 本轮已执行结果

M16真实前缀至Conv/staging为103.27秒；M128为259.57秒，包含后验比较为261.43秒。
M16同输入Conv/SiLU 856处、端到端857处仅正负零位差；M128对应6820/6817处。
二者最大数值误差和ULP距离均为0；这不是bitexact官方结论。实际结果均与固定配方
bitexact。原始history同输入bitexact，端到端保留前驱QKV的tiny差异，未因此放宽门。

M16 Matrix useful268435456/executed2147483648；M128均2147483648。
Conv Scalar四tap实际乘法M16 524288、M128 4194304，其中排除每通道六个冷启动
零padding tap后的非padding项分别475136和4145152。SiLU、RMS及Exp内部操作另报。
这些是工作量，不是带周期分母的MAC利用率或占空比，尚无流水重叠实测。

完整冷GDN 477项/36套通过，122份源前后不变；清单和典型block计划91项通过。
真实M16/M128不是CI合成小门，也不是完整block。精确发布提交的CI另行核验。
机器可读证据：[QWEN35_35B_RMS_QKV_CONV_20261013.json](../reports/execution/QWEN35_35B_RMS_QKV_CONV_20261013.json)。

## 复现入口

已验证的固定runtime使用现有 scripts/rebuild_qwen35_official_runtime.sh重建及审查新receipt；
设置HETERO_35B_RUNTIME_PROFILE到相应显式pin。Conv payload入口：

```sh
$PY -m candidates.qwen35_35b_conv.payload plan
$PY -m candidates.qwen35_35b_conv.payload collect --output work/FRESH_CONV
$PY -m candidates.qwen35_35b_conv.payload verify --output work/FRESH_CONV --manifest-sha256 "$CONV_SHA"
```

实际前缀沿用run_prefix，显式提供三张量payload SHA、完整N8192参考报告SHA、
Matrix/Vector编译receipt和原始官方源；增加 --conv-payload、--conv-manifest-sha256、
--full-qkv及 --wall-seconds 600。分别 --tokens 16、--tokens 128，输出必须是新ignored目录。
不使用缓存实际QKV替代真正RMS/Matrix执行。完整CLI参数见run_prefix --help。

单独后验门不执行owner，可对独立封存的实际报告和raw重比；它严格要求已有runtime
线程身份，不会偷偷改变调用者的线程配置。命令如下（本轮M16实际采用）：

```sh
$PY -c 'import torch,runpy;torch.set_num_interop_threads(1);runpy.run_module("candidates.qwen35_35b_conv.verify",run_name="__main__")' \
  --execution "$EXECUTION_REPORT" --execution-sha256 "$EXECUTION_SHA" \
  --payload "$CONV_PAYLOAD" --manifest-sha256 "$CONV_SHA" --output work/FRESH_STRICT_RECHECK
```

M16历史runner的唯一源码差异另存可逆patch，其重建SHA必须等于封存执行报告里的
8f8b605070ac28ec75e3aceab8fb6e45d688ee3c22371605ea31f034986f4abe。
该patch仅审计旧执行来源，不应将其中旧宽门恢复到当前正式runner。
