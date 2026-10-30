# run 41108031789：编译通过，IR 前置准入失败（FAIL / INCOMPLETE）

- 原任务 attempt 1 / job 124242896965；source 0719dfbea5e984f2639e4db6b6bd97c1cb65e7d6、launch 400a8174b1ba7bc2ffb7d8c99f48fcc66f4d1b4f。18:36:49 UTC 终态 failure，不重试或复用原 activation。
- 受控原摘要逐字节保留：1776 B，SHA256 4cb03c6230bf2a05a4a02ecebba4bb77f2e6ae34781be85a4ff46693d1837828。artifact 13002876970 的 ZIP 为781 B / SHA256 6e7e3d106866e68b0af5674ba60cd36752949539d9612a2b0278fbbfe713f86f。原摘要没有 admission 字段，不回填或改造为新 schema。
- 六个准备/编译阶段均 native 0、complete true、error_count 0；R2 统一155源/8覆盖完整 Scala compile 实际75.941635151秒，观测RSS1585991680 B。此为编译通过，不是IR、SV、ABI或数值通过，也不迁移V1类/端口哈希。
- 原 job 日志与该 source 的控制流定位：original_ir 前置 census 抛出 preflight entry cap with stage reserve，尚未调用该阶段 supervisor.execute。HIGH/official LOW 未开始。计数在已观察19993项加8项预留大于20000时中止；19993不是完整目录总数，不能声称完整总数已超过20000。
- 根因是计数范围不一致：局部旧IR的20k门被用于当前仓库＋工作目录的 aggregate 扫描，而本入口先前六阶段已使用同一 aggregate 100k门。修复将IR对齐这个既有aggregate 100k条目预算，不删除观察根、不动预留8项或原supervisor；这是显式计数预算修正，不宣称旧20k保持。CPU/RSS/wall/tree/file/log/cleanup预算不变，100k仍需真实准入，不能预先保证通过。
- 新源码还记录有限枚举的 admission 结果（count/limit/reserve/census_complete/execute_called 等），拒绝将中止计数当完整census、拒绝将execute未调用当执行完成。44项normal与-O轻测分别通过，只是源代码/模拟状态资格。
- 新专用闭包618项，125813 B / SHA256 1277341d821c7ed915b15e4c500d88c6696dab23ff62a923137421b92265e0af；active598和原监督程序不改。新路径 observer_fixed155_original_ir_aggregate_scope_r3_20261030_once 仅在source/CI确认后另行单文件activation，当前包无activation，旧17路径拒绝重用。
- 新R2 122端口仅待测预期。五块完整M128 Chisel数值与最终冻结RTL回放均0/5；有效MAC利用率未实测，4096固定资源及80%/90%目标不变。本证据不含原始日志、IR、class、权重、张量或执行payload。

原始记录：https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/41108031789
