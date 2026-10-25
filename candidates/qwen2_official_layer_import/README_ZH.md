# Qwen2 官方 normal-import r2：独立证据小包

这是有限范围的已执行 import-only 结果、原样 gate 源码和脱敏证据投影，不是完整 runtime 分发，也不是 full-reference 或数值验收包。本包按独立小提交交付原样源码与既有运行证据；发布不授权再次运行，也不升级数值资格。

## 已建立的结果

- 独立的一次 r2 cold01 正常导入成功：Transformers 4.40.1、Torch 2.10.0+cpu、NumPy 2.3.5。
- 4 个选定类（Qwen2Config、Qwen2DecoderLayer、Qwen2Attention、Qwen2MLP）的自身源码与记录的递归自身方法 code 树一致；另有 9 项实际模块字典、基类、registry 与原始 ACT2FN 对象绑定检查通过。
- 这不证明全部方法 __globals__、继承方法、传递对象图或全 live-code。45 个 no-file 模块字典与 2 个 typing.io / typing.re 非模块元数据项合计 47 项仅为诊断，不提升为来源证明。
- 唯一精准例外是 urllib3.util.connection._has_ipv6 内一次 AF_INET6 / SOCK_STREAM / proto 0 的 (::1, 0) bind。审计事件发生于系统调用之前，只证明该事件获准，不等于 bind 成功。另行保留的真实观察是原函数精确 bool True、原 HAS_IPV6=True、相同 socket 在原返回时 native fileno=-1；没有独立内核 syscall trace 或 OS 全网络隔离证明。
- 18,622 个本地封存文件共 916,804,325 bytes 的 preflight、postflight 和独立复核一致。快照包括 1,671 个 sys.modules 项、172 条 map；不是完整生命周期 trace。
- worker returncode 0，已 reap，没有记录中的存活残留；worker wall 5.2409 s，RSS 峰值采样 294,002,688 bytes。RSS 每 20 ms 采样而非硬内存上限；30 s CPU 限额适用于 worker 进程及线程，不是内核全树配额。

## 不得扩大结论

没有创建 Qwen2Config 或 Layer，没有 forward、用户 tensor 计算、新数值 oracle、DUT/matrix、性能或 QoR 验收。full-reference 的准备与本包隔离，实际官方 Layer/forward/新 oracle 尚未执行。r2 的 claim 已消费，no_retry=true；本包不授权重试。

旧 cold01 总体仍为 FAIL_IMPORT_ONLY_GATE。其原事件缺少 caller/address 证据，对 urllib3._has_ipv6 的归因只能是高置信静态解释，不能回写成直接动态证明。旧 31 文件基线未变。

## 包内容与阅读顺序

1. evidence/REAL_IMPORT_RESULT.json 与 EXECUTION_REVIEW_PROJECTION.json：真实一次运行和独立执行审查的脱敏投影。
2. evidence/SELECTED_CLASS_IDENTITIES.json、SELECTED_BINDINGS.json 与 LOOPBACK_PROBE_OBSERVATIONS.json：有限身份与 probe 证据。
3. evidence/CONFIG_SUMMARY.json、STATIC_REVIEW_PROJECTION.json、SOURCE_TOOL_DEPENDENCY_PINS.json：配置、预审与必要逻辑角色哈希。
4. evidence/OFFICIAL_WHEEL_PINS.json、DEPENDENCY_REQUIREMENTS.json、PYYAML_PROVENANCE.json：12 个官方 wheel URL/SHA、历史版本依赖范围与真实 PyYAML metadata 来源。
5. 原样四个 gate source 和 test_gate.py；历史 normal / optimized 70-test mock 日志。

各 projection 明示原始 SHA 与变换，不能冒充原始 receipt、launchable CONFIG 或新的 approval。包含哈希不等于包含原字节，也不表示脱敏数据足以独立复验全 manifest。

## 可运行范围

只允许运行纯 stdlib/static/mock 测试，不会进入 worker.run 或 launch 路径：

    python3 -B test_gate.py
    python3 -B -O test_gate.py
    python3 -I -S -B test_gate.py
    python3 -I -S -B -O test_gate.py

Linux CPython 3.12 是原审查环境；测试在临时目录创建合成文件并清理，不导入 Torch / NumPy / Transformers，不创建真实 socket，不运行 ELF 或数值工作。这些是 gate 逻辑 mock 测试，不是正常 import 的再次执行。

真实运行的外部依赖、prepare 接口缺口、原 SHA 输入和恢复边界见 REPRODUCTION_BOUNDARY_ZH.md。不要运行 run_gate.py 或 worker.py 试图复用已消费的审批。
