# post-terminal launcher 测试时钟修复（2026-10-24）

**状态：本批测试修复；full-model/native/RTL 仍未重新验证。**

## 原失败证据保持不变

- fce6102 的 CI 40102957026 仍记为 FAIL：91 个 suites 中 90 个通过，执行 960 个测试方法；259 个源文件 pins 稳定。
- 唯一失败为 `LaunchTests.test_success_is_process_completion_not_numeric_pass`：原测试直接用绝对浮点时刻相减，得到 `329.99999999999994 != 330`。
- 固定旧测试的 monotonic 为 `200.00000000000006` 可独立稳定复现同一失败（1 个方法，exit 1）；这份失败不会因新补丁而改写为 PASS。

## 本批变更范围

- 仅修改 `candidates/qwen35_gdn_prefill/postterminal/test_launch_cold.py`，并新增本说明。synthetic fixture 默认 monotonic 固定为可精确表示的 `100.0`，保留原 `330 / 300 / 325` 精确差值断言。
- 新增 1 个测试方法，覆盖 `0.0`、`200.00000000000006`、`1048576.125`、`1099511627776.125` 四个代表性时钟；精确核对绝对 deadline 等于同一 start 加预算，以及传给 runner 的 stage/absolute stop。
- 不使用近似断言或放宽容差，不改生产 deadline、实际协议或预算检查；不改生产代码、`CODE_PINS.json`、bounded runner、strict cleanup、source algorithm 或已有候选冻结。

## 已验证与尚待验证

- 已通过：launcher 14 个、terminal_gate 37 个、cold_postterminal 25 个 synthetic 测试方法；普通 Python 与 `-O` 各 76/76 PASS，共 152 次方法执行。新增时钟方法每次含 4 个子案例。
- 已验证：其余 portable package 文件与来源 payload 逐字节一致；3 个生产 adapter pins 与源文件匹配；3 个既有 helper 的固定 SHA-256 均匹配。
- 预期后续自动 CI 为 91 suites / 961 tests / 259 pins。该数字仅为新增 1 个方法后的预期，须以新提交对应的 CI 实际结果确认，不在本说明中宣称全套 CI PASS。
- 本批未执行模型、native、实际诊断或 RTL；没有扩大任何数值验收。portable actual 仍为 `TEMP_NOT_EXECUTED`，历史原始 `FAILED/exit 1` 和 combined `INCOMPLETE` 归属不变。
