# 仓库布局与证据边界

新增独立候选目录，不覆盖现有生产入口；运行显式 --repo 指向同一经审checkout。CONNECTION_SOURCE_PINS保持原冻结production字节。consumer/LOCKED_SOURCE_CONTRACT.json的proof字段只是历史证据标签，当前代码不解引用，不声称该scratch相对路径在repo存在。

原独立复审41方法=33候选+3 P0 metadata+5 ABI wiring，另4组前置拒绝；不是数值或loader执行。原测试日志保留本地，发布仅摘要及可复现测试代码；portable测试修订以新manifest单列，不覆盖旧冻结包。

P0真实producer仍BLOCKED，预算未闭合，五块完整数值0/5。

## 发布闭包与复现
实际main f76f0162缺少20件selected-runtime源码，已按原219项依赖pin精确补入独立 candidates/ci_single_profile_runtime_20261029 目录；其余199件与main逐字节一致。不是凭临时测试树冒远端闭包。

在完整checkout根目录执行（无下载/安装/loader/DUT）：
```sh
D=candidates/same_job_materialization_20261029
python -B "$D/test_connection.py" --repo "$PWD" --candidate-dir "$D"
python -B "$D/test_original_prepare.py" --repo "$PWD" --candidate-dir "$D"
python -B candidates/runtime_abi_liveness_20261029/test_runtime_abi.py
python -B candidates/runtime_abi_liveness_20261029/test_abi_receipt.py
python -B candidates/runtime_abi_liveness_20261029/test_live_bytes.py
python -B candidates/ci_single_profile_runtime_20261029/test_selected_runtime.py
```
将python -B改为python -B -O可复核优化模式。测试里的mock只是metadata边界，不是DUT执行。
