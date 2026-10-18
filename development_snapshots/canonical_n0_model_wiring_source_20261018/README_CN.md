# Portable tiny N0 wiring SOURCE

本包 12 个生产 C++ 文件、3 个测试构建文件和 2 个 Python 执行文件与原已执行 gate 逐字节相同。仅相对来源/状态元数据、README、安全结果摘要和 manifest 作可移植投影，详见 SOURCE_PROJECTION.json。所有 15 个构建输入均在本目录，由 BUILD_INPUT_PINS.json 固定；无需本地历史审计目录或生成模型头来运行这个 tiny fixture。SOURCE_PIN.json 仅记录真实项目相对来源。

## 已观察的有限结果

原单次 O0 gate 实际 PASS，RESULT SHA256：535ac8f22a57f40a7385938c7bec69e743db122faf954f3f8342e60940e87d5c。

- 436 个 checks，单配置，不是 436 个独立 case。源码计数可分为原 payload/rawbits 218 与私有 fixture 218；实际程序只报告总数。
- compile 3.990129s，run 0.023365s，均含监督时间；两 stage exit0 且 cleanup=true。
- tiny arena 1024B；modelbinding、adapter_runtime_bound、canonical_input_sha_verified、actual_n0_execution、full_host_ready、launch_ready、eda_executed 均 false。
- 本包准备没有 native 重跑；历史运行不证明真实模型/ABI 已绑定。安全摘要见 BEHAVIOR_SUMMARY.json，其实际结果独审状态以该摘要创建时记录为准。

不包含 ELF、构建目录、当前 compiler/系统身份清单、完整日志、tensor payload 或生成数据。未来 runner 仍动态记录当次所选已有 compiler 的路径、字节数和 SHA256。

## 测试究竟执行什么

`test_launch_payload.cpp` 是唯一启用测试友元的 TU。`fixture_model.hpp` 的 83 public/root alias、78 scalar/3 array 名称来自真实 getter，提供脚本化 C++ 字段存储，未伪造 completion tag/epoch 端口。它不是 VHostBlockTop、Verilator 模型或 ABI 替身。

真实私有 scheduler 模板在此测试类型上实例化并执行：offer/low/high 保存已接受 launch epoch7、保留 job 身份、AW 停顿/首 fire ID37 锁定、W staging、pre-edge B 同 allocation 提交和 raw completion 发布/只读路径。错误 epoch、owner、PC、status、signal、宽度、held-B ID 检验具体拒绝边界与 RAM 不变/poison。B 后 completion 前的公开读取被拒；completion 后公开 byte/beat 读回原 allocation 的实际提交字节。

明确注入：1024B 小 policy；job high 与 completion high 的现有输出字段变化由 fixture 脚本设置；core→hub/DMA 接收以及原 tag response/writeback/done 由测试调用真实私有事件 gate。没有直接设置 payload/mask/published 获得成功，但不能据此声称真实模型产生了这些事件。详细边界见 COVERAGE.json。

## 复现门与预算

先获执行授权，再在本目录运行：

`python -I -S -B run_behavior.py --compiler c++ --output /absolute/fresh-attempt`

单 O0 compile：wall30s / CPU30s / AS256MiB；单 tiny run：wall10s / CPU5s / AS256MiB。两 stage 串行，固定 C++17、Wall/Wextra/Werror/pedantic、无彩色诊断，不读外部 CXXFLAGS、不安装依赖。无额外 version 子进程、O2 或负编译。

原 WNOWAIT/unreaped leader、kill-before-reap、各最多5s清理、失败保全/no retry 保持原字节。40s wall /35s CPU 是 stage 上限算术和，非父硬截止；另各最多5s清理。每 child 文件限制4MiB，可接受日志64KiB，core=0。严格单 JSON 结果拒绝多余/重复/尾随/非有限字段及 true/0 冒充 false scope。

冷测可运行 `python -I -S -B test_runner_cold.py` 和 `python -O -I -S -B test_runner_cold.py`。这些测试只有固定 Python 与 mock，不调用实际 compiler、ELF 或 signal。

## 仍未验证

真实 generated headers/GeneratedBinding/registry、resident-before-N0/reset/profile/single-instance admission、真实 N0 计算和完整模型事件链、canonical 大 RAM、Host/EDA 均未验证。原 compile_generated_contract.cpp 与 negative_model_access.cpp 未进入此包/本门，状态仍 PENDING：前者缺真实头，后者尚需精确 private 诊断合同。不能拿当前 fixture 或历史其它包 PASS 替代这些缺件。
