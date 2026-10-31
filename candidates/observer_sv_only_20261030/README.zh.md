# SV-only 原扫描失败最小性能修复（候选，尚未重跑真实 SV）

## 已证事实
run41151061202 前7阶段 strict/native0，old_svscan 182.287298s、wall cap180s、native_exit=null、error_count1，strict=false；清理/EOF/gzip均完成。原两JSON未导出错误类型，不能仅凭native null断言具体wall/CPU/RSS原因。new和projection未开始，0/5数值。

原collector先整SV调用原逐字节digest，再调用原module_fingerprints对所有模块再次digest，约2N Python词法遍历并额外模块raw读盘。本修复不扩180s或全job10800s，不增stage，不改原硬件、canonical、SVwhole/module期望、投影判据和scanner b49c源码。

## 单遍等价方法
新 `P/sv_inventory_single_pass.py` 保留每个模块一次**原b49c digest**，TeeHasher同时将同一份normalized bytes更新模块SHA与whole SHA。raw SHA和byte count由同一输入行更新。

终态证明：原digest成功排除终态block/string；强制每个块最后rawbyte为LF，line/escapedidentifier状态也必退出，因此每块成功终态code。第一块原始初态code；全file严格无缝由module块穷尽覆盖，归纳得到各边界code。逐块normalized byte串拼接与原whole digest输出严格相同。所有counts键逐块累加，包括recognized/directory_changed/unrecognized；末EOF SourceInfo不会换义，因为每块均末LF。

拒绝跨module block/string、嵌套假module、重复module、缺endmodule、前后/模块间空隙、无末LF、行/文件/模块上限超标。是对官方布局的保守收窄，不是宽松重解析。scanner.hashlib仅替换该模块命名空间且finally恢复，未修改全局hashlib对象。临时模块在原TMPDIR内，仍受原stage监督。

collector调用并校验新helper SHA，保持 `OBSERVED_FRONTEND_SV_V1` 原字段/schema。projection仅同步collector源码SHA，未改任何投影判据或旧/新known hash。

## 实测，不是假定增预算
受原严格supervisor RSS1GiB/CPU60s/wall90s控制，35.0MB/96模块合成对照真实完成：
- 旧 whole8.972270s + modules9.039329s =18.011598s。
- 新完整inventory9.235508s，约49%降低。
- 所有whole/raw/module hash、byte count、全部计数字段逐项精确相等。
- 监督native0、wall28.103336s、CPU27.31s、RSS12,173,312B；cleanup/EOF/gzip均真。

这是合成扫描可执行性证据，不是实际旧/新SV证明，不保证未来CI绝对耗时。stage仍180s/1GiB、whole3h全部原预算不变；净预算变化0。实际原扫描失败原因仍不可从丢失的errors恢复，因此安全诊断也修复。

## 安全摘要
`export_metadata.py` V2：error精确映射固定枚举（未知仅UNCLASSIFIED，不上传异常原文、路径、secret）；CPU观测无字段则null，不能猜0；明确wall/RSS cap。顶层期望hash改expected_*；只有完整project严格成功时才给observed_*，失败null。不改变严格终态与proof门，仍只两个≤128KiB合计白名单JSON。

## 验证/交付范围
15项原scanner差分测试，含100组确定随机样本、64KiB缓冲跨界、CRLF、pragma/string/escapedidentifier、跨模块恶意词法、无末LF、namespace恢复与真实collector入口；normal/-O通过。
安全export新增5负例，8export tests normal/-O通过。最终closure/全套回归交独审打包owner重算。
`SCANNER_SINGLE_PASS_BENCHMARK.json`是仅数字/pin的安全摘要；不上传合成SV正文、原SV、log/classes/IR、用户数据。

本候选无重构build，无CI/推送/activation。实际专项重跑必须由root按已授权范围与新source/nonce验证执行；本次SV专项许可不代表生产M128已授权通过。

## 新唯一启动约束
修复source发布不触发专项；后续新source CI成功且main无冲突、原run已终态、无活动重任务后，仅新增 `ci_launch/observer_fixed4096_sv_only_difference_20261031_scanfix_once.json`。nonce同文件stem，attempt必须1，严格single A和direct parent；旧20261030路径已消费，永久不复用。全job仍10800秒、声明9060秒、余1740秒；原15stage及180秒scanner cap均不变。本文以下是原发布时历史说明，不代表本次或上次已通过。

---
## 历史：原source-only发布说明

# TEMP / SOURCE-ONLY：旧新完整4096硬件的 SV-only 两模块严格差异取证

本候选不激活；后续仅独立审核后由新source提交的直接父子关系、唯一新增launch触发一次fresh CI。基线main `15e6374af13e0f9d68cad1c9314a0228905bba59`，不回退既有frontend证据或计划。尚未实际运行本15阶段链，不宣称projection或SV re-pin PASS。

## 输入及执行

旧新均从源码独立编译完整155，106个固定JAR+原插件，同4096资源。旧155使用独立 `OLD_FIXED_SOURCE_OVERLAY.json`（f8cb8f…；保留HostCommands attentionfix）；新用现行9be781… overlay。旧两helper原字节冻结在old_helpers，不覆盖活跃新helper或旧基线。两边各有全新class/helper/output目录；不搬localclasses、不使用已有运行classes。

阶段恰15：JDK/Python身份及native依赖（保留未知DSO/环境注入/alias漂移拒绝）→固定JAR→旧compile155/helper/originalIR/canonical/emitSV/scan→新同6阶段→严格projection。原诊断helper仍完整运行，不改成HIGH-only；旧/新canonical必须逐byte匹配90464ff…/00897f…，whole normalized必须6555ede…/ec70f91…，失败即停，不自动学习新hash。

projection只对2个指定模块的已列61-bit key的4个字段及对应ports/direct assigns（Router8个ports+4assign，DownOwner4个ports+4assign）及其闭合引用执行严格规则；任何非白名单差异保持不通过。即便证明成功仍 `sv_repin_authorized=false`、`numerical_pass=false`，只交独立审核，不自动修改production门。61-bit SourceInfo路径解释当前仍待实际输入hash绑定证明。

## 资源与身份

原phase caps最大RSS6GiB，freshhost至少7GiB；15 phase wall合计6360s，cleanup450s，parent三段各300共900s，内部执行严格7710s。GitHub step129min=7740s只做外层整数取整30s，phase不扩大；其他workflow1320s，保守总9060s，whole10800s余1740s。原monotonic起点在checkout前记录，不重置。整仓+work同一100k entry/12081306272B aggregate disk口径，原disk安全保留，不删除运行证据。

本地原IR84990身份/状态未知，保留5GiB预算，不在本地执行本重任务。source-only测试只用轻量fixture/AST，不执行Java/IR/SV。fresh CI不含serialVerilator、GCC、providers、archive/link、权重、reference、DUT，不继承runtime CPU资格。

## 输出

仅 `sv-only-summary.json` 与严格schema的 `sv-only-proof.json`，各≤64KiB、合计≤128KiB。导出重读15原RESULT严格终态、两canonical/whole hashes、projection输入和proof pins，缺失标观测不可用或INCOMPLETE，不当任务停止。禁止rawSV/IR/annotations/classes/o/rawlog/weights。保留原源码、源pins、运行hash、闭合差异摘要；临时数据不自动清除。

五块128-token完整数值仍0/5、最终冻结同RTL刺激回放0/5、利用率未测。这个差异取证不是数值主线的替代通过。

## 已有小fixture证据（不迁移为实际全SV证明）

`KeyFormatFixture.scala` 与 `FORMAT_FIXTURE_SUMMARY.json` 是官方emitter小AST格式/逐字节投影检查，绑定最终projection SHA `81aada0fd6c89db9f259d48089ba3f352f4ea7a4438693aa97a0bb708c2280a4`；不是实际两模块SV。`perf_projection.py` / `PERFORMANCE_SUMMARY.json` 仅合成8MiB并写出投影sink：监督3.483709716s、采样RSS43638784 B，函数2.708509237s；进程自报peak49020928 B与监督采样分开列。它不是整个300s proof阶段的耗时证明，不据此保证实际大SV通过。原脚本仅等字节重命名为sv_difference_projection.py，测试/perf双模块import原样保留。
