# 新平台 CI 执行准备

状态：源码冷测中；未触发完整数值 CI。只接受已验证的 GitHub runner checkout 根，Python 3.12.14 新 ELF 身份与原五个 Torch/NumPy native 文件分别核验。

- `platform.initialize(execute=True)` 必须在新进程重新初始化。历史 CI 摘要不能输入此接口。
- `inputs.prepare(execute=True, download=True)` 固定八个 QKV 范围、十四个全 fresh tail 范围及九加五物化角色；默认不执行。
- `native.build(execute=True)` 用原严格编译器旗标和原数学源生成新 ELF；之后加载须精确绑定新 receipt digest。新编译身份不继承旧 ELF 通过结论。
- `python -B -m candidates.qwen2_fullblock_ci_execution.prepare --execute --download` 顺序执行独立子进程平台初始化、输入恢复、native 构建，只写本地 PREPARED。不会生成审查或 GO。
- `summary.checked_aggregate` 仅在本地核对完整 29 输出及仓库已存在的固定期望；可导出固定状态、29 计数及源码摘要，不导出逐项 tensor 名称、shape、hash、stride、file、路径、权重或历史拒绝元数据。源码摘要必须由源码闭包产生，不得包含输出或 receipt。

两阶段：先经独立源码审查授权一次新平台 bootstrap，生成未验收的官方参考观察，并仅报告允许的聚合结果。再审核并冻结数值作业的输入、源码、平台和参考契约。当前没有可运行的完整 DUT 入口，也没有完整 block 数值或 RTL PASS。Python 动态 libpython 身份仍需在数值平台冻结前补齐；现有六 native 检查不等于整个运行库闭包相同。

冷测（无下载、无真实 native 构建、无参考/DUT）：

    PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s candidates/qwen2_fullblock_ci_execution -q
    PYTHONDONTWRITEBYTECODE=1 python -O -m unittest discover -s candidates/qwen2_fullblock_ci_execution -q

假子进程测试仅验证进程隔离和拒绝路径，不计业务通过。

## 第 1 阶段实际入口（尚待独审与外部证书）

新增 `qwen2-fullblock-ci-bootstrap.yml` manual dispatch 与唯一自身文件路径 main push，整体 15 分钟；安装最多 7 分钟、准备 5 分钟、capture 与聚合 3 分钟。原参考监督器内部 120 秒、独立 watchdog 122 秒仍保留。只在经授权发布该唯一 workflow 文件时触发一笔 bootstrap；不支持 pull_request/schedule。run_attempt 必须为 1，禁止 Actions rerun。

`bootstrap --admit` 接收真正外部审查证书的原字节与独立 SHA256，核新源码闭包后只在 CI 本地保存；`--capture` 在准备完成后派生未独审的真实输入身份，由明确的 issuer 展开已经外部批准的固定源码 policy，执行唯一 `ci01/bootstrap`。展开文档不声称由独立 reviewer 编写，也不声称未来观察已被其独审。

聚合前核完整成功库存、每个 payload 与观察记录对应的 SHA/bytes、退出与收尾状态、固定预算，再与仓库原有期望在本地比较。细节、checkpoint、逐项 hash/shape/stride、源 receipt 和 GO 均不上传；任一失败仅报告固定阶段失败并停止。只上传 `aggregate.json`，其中源码摘要由 source-only closure 计算，不混入 output/receipt 摘要。

外部审批目录固定为 `candidates/qwen2_ci_bootstrap_authorization/`，只读真正独审生成的 SOURCE_CERTIFICATE.json 与 EXTERNAL_PINS.json 原字节。该审批输入不参与源闭包，避免自哈希循环；缺失、额外字段、错误 SHA 或源闭包不符均在安装前拒绝。CI 不能生成默认批准。
