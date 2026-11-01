# TEMP：GitHub 仅构建，云端另行验证

本包只接原始单份 4096 Matrix MAC 硬件的 BUILD_ONLY 路径；122 ABI、原始 Chisel/HIGH/canonical/SV、编译选项、archive/link 和严格监管不改。32 vector 标签不构成实际 II=1 证据。GitHub 不运行 Python 模型参考、模型权重获取、DUT 或完整数值验收。

**2026-11-01 00:35:33 UTC 用户已明确批准上述七文件传递。** 固定 `TRANSFER_APPROVAL.json` SHA `e8326625484725b0597ee87c831bbc8e77f7b50fd9bc09ba58a02cdde486cafc` 由 guard/export 校验。授权不包括权重、NPZ、输入、参考或原始日志；不将接收等同执行权限。源码发布后仍须唯一直接父提交、single-A、attempt1 启动；不重用已消费nonce。此源码提交本身没有launch文件。

## 预算（不扩大原阶段上限）

- workflow 总 150 分钟 = 9000 秒；声明 step 合计 147 分钟 = 8820 秒，剩 180 秒。
- 记录时钟1分钟 + 两次 checkout各4分钟 + guard1分钟 + build122分钟 + export5分钟 + upload10分钟。
- build 核心仍 `maximum-build-seconds=7200`，**包含**原 bootstrap（原更紧1800秒仍有效）与实际后端；122分钟step仅给wrapper/退出120秒，不给任何stage加时。
- 首step开始的9000秒时钟不重置，prepare要求7200+900秒后段保留仍适配；原bootstrap/one_job的逐阶段剩余预算与cleanup守卫继续运行。旧内部21000只为既有代码的绝对天花板，实际新job9000、build7200更紧。
- 8个prep的各阶段最大值相加不能塞满1800；全部build阶段最大值也不能保证7200完成。不得宣称最大组合必可完成；资源/剩余时间不足时拒绝，保留INCOMPLETE，不缩硬件或自动重试。

## 七文件与跨身份

唯一payload为 `dut.bin`、`hardware.sv`、`driver.cpp`、`source_manifest.json`、`tool_manifest.json`、`build_receipt.json`、`frozen_artifact.json`。不含权重/reference/npz/IR/classes/raw log。export重读8 prep+20真实build RESULT的native0、errors=[]、原cleanup、EOF、gzip，精确原阶段顺序与七文件hash，总展开≤4GiB；未全部成功不上传。builder保持原六字段实际Actions身份，不能制造cloud执行身份或继承数值PASS。

`receive_zip.py` 不下载、不运行、不调用ldd：调用者必须先经授权API核验真实run/source/launch/artifact id/name/expired/原API储存size，以及实际下载ZIP字节数/digest（不假定API储存size等于下载ZIP大小），再从ZIP外部传入受信API回执与ZIP SHA。脚本核SHA、精确七名称、禁止重复/路径穿越/symlink/设备/额外文件、限定总展开与各类size、逐块提取并核实际字节。ELF与其余文件一律0600，不授执行权限。失败保留未完成唯一证据，不自行删除。通过仅说明字节接收，不代表ABI或资源可运行；后续先readelf等静态检查，完成真实资源审批后由独立cloud identity执行原严格ABI与数值流程。不得让包内自述取代API认证或用户授权。

## 轻测范围

17项 synthetic normal/-O：七件原样接收、0600、错误ZIP/API/run/过期/大小拒绝、路径穿越/symlink/额外payload/漂移拒绝、严格receipt失败、批准receipt核验及缺批准launch拒绝、mock批准后的direct-parent/single-A/attempt检查、预算常量及mock来源/授权的完整28receipt→实际七文件validator→export链。fixture仅伪ELF字节，不是实际编译、链接、硬件或完整数值PASS。实际源码闭包由集成owner最终重算，最终包需另一审查者交叉确认。
