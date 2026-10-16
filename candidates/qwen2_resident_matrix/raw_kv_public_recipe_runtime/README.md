# Public PV16 paired-reference setup runtime

## 中文计划
- 已完成：独立 native16/128 的 AVX512-BF16 实例数值通过与精确 dispatch prerequisite；旧证据/profile 保持原字节。
- 已完成：真实 setup/assets/entry 三处有界接线；46项冷测试 normal/-O 均通过（13.247/12.725秒）。其余七处 composed overlays、原始 Public PV16 owner/Matrix/Host、C++ sequential/block-pair hardware references 均不修改。
- 进行中：独立审查。待完成：linked admission/runner/workflow。当前 authorize_run 始终拒绝 Public 数值执行。

新 producer 使用原始生成 gate、双 Recipe 库、原始全部判据/export 校验与 Capture；不调用 standalone phase.run，不伪造它的 context。Public 输出路径为 native_m16/native，fresh16 prerequisite、同输入、双库和完整9条实际 avx512_core_bf16 matmul 必须验证。未知/incomplete/AMX 不满足本 profile。

setup 原七字段 context 保持原样，受检查的 producer_context 派生 contract 和外部 generated gate 身份；绝对 deadline 不刷新。两个库由唯一 setup supervisor 在新 recipe_kernel 阶段编译，共用30秒，外层 alarm 在该受限调用中暂时解除并在 finally 重置为原剩余时间。禁止在 setup child 内嵌 compiler supervisor。原900 setup /2400 work /2430 external /3420 outer 预算不提高。

ASSETS 新增 recipe 的有界文件记录：generated gate、双 ELF/compile receipt、两case报告与diagnostics。每个字节和实际source map重新校验，重新计算 RESULT→report/stage hashes→diagnostic 的绑定；原始232个 exports、shape、所有数值/语义判据继续逐项校验。身份只在原 runtime_identity 上添加已验证独立recipe和generated runner hash；不替换官方输出或hardware oracle。读取比较数组仍由原terminal fence控制。

源码准备先完成已有十个 overlays，再以零fuzz patch只修改 setup.py、assets.py、check_public_numeric.py。既有七个其它输出 SHA 必须不变。全模块 AST 在明确 control/provenance 节点之外保持相同；改变节点另由固定生成 SHA 约束，AST projection本身不声称证明全部运行语义。

冷测试与source-only composition不是实际 producer/setup/native/Public运行。本切片没有workflow或数值launch授权。

source-only 测试实际执行 composed assets/setup source snapshot 与原 entry source_hashes helper，272个源码身份完全一致，十个生成输出准确匹配；同时禁止 NumPy/Torch/Transformers 和 CDLL 加载。测试包含真实 composed native16/128 wrapper、原全局 deadline 优先级，以及原始 verdict/export/recipe 身份失败路径。没有运行安装、编译、producer、native 或 Public 数值流程。
