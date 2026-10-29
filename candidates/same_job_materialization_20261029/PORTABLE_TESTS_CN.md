# Same-job 测试路径修订（仅测试，不改production）

连接测试接受 --repo、可选 --driver、--candidate-dir；driver默认已发布repo路径 candidates/five_profile_execution_v3_20261029T0148/host_axi_driver_non_dpi_final_dump.cpp，不引用私有scratch sibling。原物化测试接受显式--repo（兼容明确HETERO_REPO）和--candidate-dir。

BASELINE_FUNCTION_AST.json由既有独立审过R3消费器和原selected materializer源码函数AST生成，保存两个原source SHA及每函数AST SHA；测试精确pin此fixture，比较候选数值/观察函数不变，仅允许execute的既定clean_env keyword差异；不需要未发布scratch源码路径。此为测试基线，不是新硬件/数值PASS或producer来源资格。

测试14连接项normal/-O通过（真实driver bytes、mock metadata/ABI）；6原物化项normal/-O在既有source-only检查树上通过。**这不证明实际远端f76仓库闭包完整**：single-runtime等依赖未发布的阻塞须另行补全并审查，不能用这份local fixture通过代替git树可复现。实际driver默认路径在f76树存在；当前本地sparse未checkout时可显式--driver给已pin文件，未为测试改仓库。

其余ABI两组测试只使用同包module及临时合成文件，无旧scratch路径。原freeze/production不改，本包只有两个测试、AST fixture及本说明。
