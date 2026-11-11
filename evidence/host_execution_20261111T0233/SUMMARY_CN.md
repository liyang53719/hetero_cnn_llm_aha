# 02:33 两路原Host实际推进：部分数值PASS，完整M128仍INCOMPLETE

## L3原状态继续，不重复前缀
先核main65701de8/CI42940877552成功及原receipt407025f6…92eae4。新增显式receipt路径+可信SHA入口，无旧默认、无DRIVER/PRIOR_CUT覆盖；7项入口拒绝测试通过，原步进、硬件及数学不改。
连续三段每段先完整事务保存再恢复：364899→464903→564907→664907，原sessions35263/24304/30943均exit0，耗时268.13/250.85/252.17秒。最后pc1/completed1、Matrix issues81920，总DDR已写905344B。无第四段。
最后21组件manifest：4292ba443003133d257856595b73aa782c2fc7941045d99a6478385353c88659。续跑receipt segment400k_CONTINUATION.json SHA afda4f3901a3be4ca5721ef50a12fa167a99b6fb94db997c04878af84a93a329。
独立直接解析driver sparse validmask和seal、核21组件：321600个已提交Q BF16元素与同刺激128×4096参考逐位一致；202688个未写元素排除，无半有效BF16。参考SHA ea5a74825cdf0e9ddadf48f251ed551bd9508bd0b9bf0620ac67563d32328336。仅部分Q数值PASS，不是完整Q/Dense/block。

## Qwen2同硬件原FP32独立新实例
并行使用同冻结4096 Host及17native，不借L3状态，原16输入文件hash先验。首100k到安全屏障后driver保存失败：观察数组序列化约9.3MB，封装总payload误用typed vector的8Mi元素上限。旧组缺driver.bin，明确不可恢复，保留全部失败证据。
实质修复仅外层byte blob的seal/open路径，256MiB总cap及typed vector8Mi元素限额不变；12项独立边界/损坏/长度测试通过，硬件/数值/fatal/生产guard不变。修后唯一必要冷重跑session46984 exit0/201.74秒，active100000/cycles100005，pc0 Norm、completed0/jobs1、Matrixissues0；真实读ACK1615，写ACK768=49152B，低相空AXI/reset0。
21组件manifest e74d64236cafbdb83baaf4c734de45a033014c09cdc4b8d30826c00039a898f7，组完整校验、native及driver零步恢复通过。续入口 qwen2_start/recovery/RECEIPT.json；下轮从此真实状态续，不能再冷启动前缀。
独立validmask核原同刺激参考：12288个已写FP32 Norm值逐位一致；184320未写排除，无半有效FP32。参考SHA ccf1e6c065c6bc4e90458194aeda7475149451ac73479a6781d2fd638bf631df。仅已提交Norm子集PASS，不是完整Norm或21-op通过。

## 其他三块、层级和阻塞
原emitter实际生成并核profile1/3/4配置记录图：17/219、13/199、18/241命令/描述符，8项测试普通/-O通过。当前冻结FIR已明确specialized flags=false、runtime streaming=true；旧12/17-op门槛不限制当前13/18-op，不误报新故障。此仅配置编码资格，不是Host数值。35B两层真实完整权重仍缺，未绕网络；L0原head4 underflow FAIL保留。
五块128 token完整数值仍0/5。固定4096及同Host定义不变；本轮是原编译IR+真实native混合模型执行，不是最终RTL回放PASS。完整block有效MAC80%/90%未实测达标，软件墙钟速度不冒硬件利用率。

## 工作区、清理、后续
开始全round临时清单43090项约10.776GB，资源约9GiB可用内存/47GiB磁盘；未删除文件。所有失败/唯一checkpoint及原输入保留。仅发布允许中文摘要和hash，不上传候选源码、原日志、checkpoint或权重。
DONE：两路真实执行及部分数值、可恢复状态；TODO：显式选各自最新receipt并校验完整pin/closure，继续原完整执行链。Qwen2新codec仅该driver执行身份，不可套用L3状态pin。阶段全完成才比较完整输出并升级范围。
