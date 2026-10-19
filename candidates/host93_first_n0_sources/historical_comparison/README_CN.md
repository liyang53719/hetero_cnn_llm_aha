# 独立 historical N0 comparator：TEMP_SOURCE

本片是在独立目录中的最窄 profile 绑定，没有替换原 CI comparator、reference/PINS、主作业或 workflow。实际数组比较尚未执行。

## 精确源码差分

基线来源提交为 `a8de294523a9cc23d370d325cadd5d6bb9c2c713`，8 份 repo-relative 来源身份见 SOURCE_PINS.json。worker 唯一替换是 `ci31214` → 既有 `historical` profile，21000 B / `e2d1a644e369147772ccd3e6b074559a9b29e9230ace172a3f4bcb4594794800`。launch.py 与 test_cold.py 仅联动该 size/SHA，逆替换逐字恢复原件，详见 DELTA.json/PROJECTION.json。

保留原五个比较函数、FP32→FP64 与 NumPy 归约、196608 全值和形状/finite 门、B 退休/ACK0/捕获完整性、原阈值 max_abs≤0.03125 与 mean_abs≤0.005。numeric_pass、bit_exact、hash_exact 分列，容差通过不代表逐位一致。comparator 直接核完整 FP32 参考；原 BF16+FP32 双 SHA 资格仍来自上游原 reference，未新增 BF16 文件比较。

historical Python 精确身份 30894944 B / `fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7`、CPython [3,12]。原五个 native 库、四源码、Torch/NumPy 版本与 build、自然 AVX512、4 intra/1 inter-op 及前后验不变。该源码片没有重新执行 runtime 或数值比较。

## 可搬迁纯 mock 闭包

保留 13 个原件：6 个 worker/launcher/tests/loader，SOURCE_PINS.json、DELTA.json，和 fixtures 中 5 份原源码/合同。fixtures 没有 tensor、wheel 或 runtime。PROJECTION.json 和 COLD_RESULT.json 是安全来源/结果摘要；原 stdout/stderr、exit 文件和本地路径库存不发布。

唯一正常冷测入口为 `python -I -S -B run_cold.py`，优化模式加 `-O`；loader 合同入口为同 flags 的 test_loader_contract.py。run_cold 固定前验 11 个输入并 compile 同一已验 buffer，前后身份复核，审计 hook 拒绝数值 runtime import、socket、外部进程和动态加载。不要把内部 test 文件当绕过该入口的独立执行资格。

作者普通/-O 与独立搬迁普通/-O 各 49 项；loader 普通/-O 各 6 项；默认 launch 两模式只报告 N0_COMPARISON_NOT_EXECUTED。最初 loader 优化模式 spy 错选 stdlib compile 的假阴性已修正为固定目标文件名和同 bytes 身份断言；原失败日志留在本地，比较生产源码未因此改变。

SOURCE 审身份：`SOURCE_GO_ISOLATED_HISTORICAL_N0_COMPARATOR_BINDING_ONLY`；MANIFEST 3086 B / `7ce32313dffbfef61cef408f528a88af9888e8c049fff0b05d163c8f6247a8e2`；SUMMARY 2697 B / `fff46429a3bfcc51cb58e74eb4201472ad1469337ac95d244fe858132417bc6b`。独立审查在搬迁目录普通/-O 各 49 项、loader 各 6 项及默认 launch 两模式均通过。审身份仅作来源说明，不是运行时依赖。所有测试均为 stdlib/source/mock，没有 Host、参考 forward 或实际数组比较。未来实际须新调用者提供真实 capture/reference/runtime 并继续外层 provenance、监督、原 30 秒/CPU 25 秒/AS 8 GiB 比较资源和共享截止；该比较窗口须在原 N0 总窗口内，不增加 Host 原 AS 6 GiB。
