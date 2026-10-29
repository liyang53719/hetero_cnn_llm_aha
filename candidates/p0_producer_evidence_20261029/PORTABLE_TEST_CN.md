# P0 producer 便携轻测（仅测试修订）

原 1339 候选与生产源码不变；仅移除测试对 scratch sibling/LOCAL_BINDINGS 的依赖。

```sh
python test_driver_dependency.py --repo "$REPO" --pipeline-dir "$REPO/candidates/ci_frontend_pipeline_r2_20261029" --global-mk "$VERILATOR_ROOT/include/verilated.mk"
python -O test_driver_dependency.py --repo "$REPO" --global-mk "$VERILATOR_ROOT/include/verilated.mk"
```

--repo 与 --global-mk 必填；--pipeline-dir 默认 repo 内原 pipeline。global mk 必须是已获工具材料中原 SHA74121398… 文件；本脚本不下载、不执行工具。driver/header/program/contract/overlay 均核原固定 SHA，七 Scala角色按已锁 overlay 路径和独立 contract SHA双验，缺失直接失败。测试仅合成/mock receipts、对象与binary，不能当真实编译或数值PASS。

18项normal/-O通过；所有测试断言方法AST不变，仅setUp/enrich_fixture改源路径。错误global mk pin在测试前拒绝。隔离test_repo缺失7源码已从实际d447 Git对象逐一提取并比原overlay SHA，无checkout、构建、联网或生产变更。
