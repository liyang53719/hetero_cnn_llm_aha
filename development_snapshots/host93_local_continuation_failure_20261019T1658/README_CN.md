# 本地 continuation：autoconf 后有限合同拒绝

本次单次本地执行整体 INCOMPLETE，外层退出 1；不是 N0 数值 FAIL。原实际源提交 a2ba85252bf3f922044e84cf6464da36211c5b51，独立 actual 审查已闭合。原七件证据保持不变，本页与 summary.json 仅为安全字段投影。

## 实际已到的边界

- official_source473、local_flex_header_cached、flex_header_compile、fresh_autoconf 四个 native 阶段均自然退出 0、未超时且 cleanup_confirmed=true，原 waitid code/status 均为 1/0。包含真实 g++ FlexLexer.h 小探针；四阶段成功不等于后续构建通过。
- 原 outer traceback 明确停在 objcache_configure_witness 的固定拒绝文本“finite OBJCACHE cache branch”，位于 autoconf 成功后的父后验、configure 启动前。固定文本前后锚唯一性条件未满足；本摘要不据此推定生成配置语义是否等价，也不声称缓存已被错误启用。原 RESULT 只记录 ContractFailure，具体定位来自保存的 traceback。
- configure、make、Host 生成/编译/运行与 N0 比较均未到；不能将父合同拒绝改写为 native 非零或数值不匹配。四个成功行保留自身成功状态，整体仍 INCOMPLETE。
- 外层 19.522997 秒，协调器 19.469299 秒，分别记载不可相加。原总预算 6600 秒；没有自动重试。累计 child maxrss 不冒作各阶段独立峰值。
- 父数据步骤只复制已固定 16 输入共 94,920,448 B，不产生新的 frontdoor 或数值转换资格。既有五工具、FIFO、SV与历史参考按本次源码的前置条件使用；本轮没有重跑工具资格、FIFO、SV发射或参考 forward。

证据身份：MANIFEST.json 1005 B / SHA256 1df2aeb35058396f0ae93e3808f3fd7f7a6bd6f7b97f35ebfe363b35991cfe26；RESULT.json 13281 B / SHA256 aa84b58cb1e2a7e7f612c7369ec4a1b0dd25f8df9cb213e57ae611430c397d2a。安全摘要不含私有路径、逐文件库存、完整日志、生成配置/源码或数组。

本批仅安全 summary、本文和中文计划三路径；不改 workflow 或执行源码，不触发新的 Host/native 作业。后续若修复见证合同，须另有隔离源码与测试，不改变本次原失败事实。

正式 actual 审查 review_local_continuation_actual_20261019T1700：MANIFEST.json 601 B / SHA256 31b293e9394fe8a25b88c341e5a43816500ea1b6534bced6db41197081507f16；SUMMARY.md 4807 B / SHA256 7a9d23fbacc4c3be6d0467e7624d18638a3f35d9aad331ba8c383ebd8a275894。结论 ACCEPT_ACTUAL_LOCAL_CONTINUATION_AUTOCONF_WITNESS_FAILURE_ONLY，接受原失败证据与有限执行边界，不授后续构建或数值资格。
