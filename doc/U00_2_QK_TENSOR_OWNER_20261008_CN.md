# U00.2：Q8/K2 全头与 token-window owner（有界门禁通过）

## 执行前冻结范围

在已有默认关闭的 Matrix → Norm → SharedL2 → RoPE 分支增加显式 tensor 模式。
每个 Command128 descriptor 加快照 sideband 管理一个角色的全部 Q8 或 K2 头，
按 token、head、32列 tile 顺序推进；不另建架构 top，不改变旧默认路径。

本轮实际 RTL 主门禁在执行前冻结为 baseline/AVX2 两套来源，各四命令：
cold token0/1 的 Q8/K2，以及 carried token126/127 的 Q8/K2，共40头/来源。
carried 的 RoPE position 为254/255。全部输入由固定真实 checkpoint 的官方前缀重新生成；
Matrix 直接接收真实 preprojection H1024 与原始权重，中间结果不能由软件注入。

单来源预期589824个K步Matrix输出包，18874368个有效FP32累加器观察值。
这些是四个 token 的全头检查，不是 M128 全量数值验收。完整三模型 block、PPA、
固定资源整 block useful-wall MAC≥90%、U00.2/U01完成均不能由本门禁替代。

## 固定资源和生命周期合同

- 继续使用实际512-lane Matrix与1,572,864B SharedL2；activation、weight 各64KiB
- 仅复用 packed单头、Norm512B、RoPE512B staging；每头所有DDR写 ACK后才复用
- 原六位 tile 计数只表达每头16Q/8K；独立八位 per-token总数表达128Q/16K，不截断4096列
- token start/count 用33位加法检查，范围为 descriptor M≤128；全头模式从head0开始
- 首次DMA前检查全部选定DDR窗口及整个weight跨度，两两不重叠；local staging及整个trig范围也不得越界或别名
- norm/rope分别按8×64B DMA写出；Norm/RoPE异常flags跨head OR（不导出Matrix中间或BF16转换flags），completed计数只在末端ACK后推进
- 单个命令接受时快照所有sideband；下一头/下一token不读取变动的外部输入
- trig以绝对源token索引选择显式cos32/sin32；位置生成和cache仍未接入
- reset必须同步清空外部fabric响应；已提交外部写入不承诺回滚

冻结机器合同：`config/upstream/qwen3_5_0p8b/matrix_norm_rope_tensor_contract.json`。
实际仿真、独立 trace、全部来源与硬件 manifest 的末端复核已通过。


## 最终复验结果

终态：`PASS_Q8_K2_TOKEN_WINDOW_OWNER_RTL`。
简短来源、哈希和结果摘要位于
`reports/execution/U00_2_QK_TENSOR_OWNER_20261008/result.json`；
独立复核位于同目录 `independent_review.json`。

- baseline/all：41个事务，7成功、30预检拒绝、2故障、2reset；704,512个实际Matrix输入/输出包，1,552个明确写ACK，其中729个同周期ACK
- AVX2/main：4个命令、全部40头，589,824个实际Matrix输入/输出包，1,216个明确写ACK，其中575个同周期ACK
- 每来源四个primary命令覆盖40头；两来源共37,748,736个有效FP32逐K累加器观察值，由整数 dyadic 与独立C参考逐位复核，实际RTL与事件消费器共同验证
- baseline主门禁全部Q/K头通过原native门限；Norm/RoPE最大绝对误差7.62939453125e-6。AVX2最大绝对误差0.015625。各头和各命令均按原max_abs≤0.03125、mean_abs≤0.005检查，未放宽门限
- 两来源Q gate均保持原始projection；完整producer/native block审计仍为false，其失败没有被选定窗口通过覆盖
- 已验证末端DMA错误不计入失败头、128-token范围可入场但故障后零完成、跨head/token reset与恢复、真实1.5MiB上界、完整DDR跨度的未来head/token别名拒绝
- baseline仿真调用2,407.065s、AVX2仿真调用2,143.322s是runner测得的工具墙钟，不是硬件延迟、PPA或MAC利用率

最终runner在实际RTL回放后再次校验完整临时输入库存、每个memh哈希、官方来源receipt、
源文件哈希与生成硬件manifest；无原生projection注入，无整tensor片上缓存扩容。
生成RTL SHA256：`5d4cf714637a579a50b9fd79eed3569c7e2a2bf39de9ba27775f0eb41d31aaf6`。

## 回归与独立复核

- 446项相关Python测试normal与-O均通过；独立审阅另运行249项tensor测试normal与-O均通过
- 全仓3,116项通过，仍有原5项基线失败，完整名单保留在结果摘要；不记为全仓全绿
- 修改后的候选路径复跑旧单头实际RTL/all：7成功、21拒绝、10故障、7reset；141,319输出包的独立trace通过
- 默认关闭生产路径：省略候选依赖的source-closure lint通过；decode两模式各8例、writeback10例/15,360值、iterator4尾部/5拒绝、descriptor planner3,072 tiles通过
- 补充检查的旧VCS取向完整controller testbench在Verilator上有既存BLKANDNBLK混合赋值错误；原HEAD复现相同错误，未声称完成该testbench仿真
- 静态独立审阅未发现新P0/P1 blocker；未进行综合、物理资源推断、时序或QoR验收

Git只包含源码、pins、哈希与简短摘要。checkpoint、NPZ、memh、完整轨迹、生成RTL与二进制
均留在忽略的work/临时重建；CI仅保留摘要。主分支精确提交的CI结果另以实际运行终态为准。

## 仍然开放

当前四个选定token的全头owner通过，不扩大为全M128或M1024数值验收。
generic Command128完整集成、position系数生成/cache、KV/Attention/FFN、三模型完整block
数值与RTL、PPA和固定资源整block useful-wall MAC≥90%仍OPEN；U00.2 ongoing，U01 to do。
