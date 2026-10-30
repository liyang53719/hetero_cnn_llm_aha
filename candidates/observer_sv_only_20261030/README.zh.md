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
