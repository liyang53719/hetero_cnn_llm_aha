# R2 便携轻测：保留原算术AST边界

基于实际fff882 Git对象生成FFF882_MATERIALIZE_AST.json（测试内固定文件SHA）。只改旧连接测试的materialize断言：原payload→bundle全部语句AST独立pin；isolated prelude AST独立pin；还原新函数去除共享参数/if wrapper后必须与原0403和fff882整函数AST同时相同。共享else入口限定精确原runtime选择语句、默认None、参数列表，不用替换整函数hash掩盖新算法变化。其它连接测试方法AST均未改。

14连接+6原物料normal/-O均在publisher实际fff882+5delta隔离repo通过；shared20 normal/-O复用前版原测试和publisher独立复跑，无重复实际runtime扫描。所有结果仅mock/control/source，不是数值PASS。

入口：`python test_connection.py --repo REPO --candidate-dir REPO/candidates/same_job_materialization_20261029`，`test_original_prepare.py`同参数；`test_shared_runtime.py`见--repo/--candidate-dir。生产源码与b7e772冻结候选不变。ADOPTION_PUBLIC_SUMMARY为前版同字节受控摘要，不包含actual owner路径、安装树或payload。
