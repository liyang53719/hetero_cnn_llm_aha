# M128 新鲜完整链：双凭据准入与单次启动合同

## 中文计划

- 已完成前置条件：真实 M16 Public21 observed-gates PASS；M128 资产与 setup 来源层、native16→128 元数据绑定及来源闭包冷测试。
- 已完成准备检查：完整 setup/资产双凭据准入、原始入口 snapshot 绑定、监督运行器及独立工作流的68个普通 / -O 冷测试（含诊断修订）；独立审查完成后才可发布启动。
- 首次真实尝试：run38913368057/job117014509569 在 environment 的 backend-preflight 子进程失败，尚未进入数值阶段；两次 pip 安装命令已经返回成功。
- 进行中：仅增加嵌套 backend-preflight 安全分类诊断；没有放宽包、CPU、MKLDNN、线程或数值门槛。复审后才可启动一次诊断充分的尝试。

## 原始链与前置结果

目标是原始 PV16 ReducedPublicExecution、同一 Dense owner/banks、Matrix/Scalar 服务和 Public21 Host 完成边界。M16 安全凭据固定为 run38904754050，精确来源清单与七个 observer/transport/official-entry overlay 保持一致。只允许经过审查的 assets/setup/入口来源变体。M16 结果不能代替新的 M128 数据、参考、库或最终验收。

私有 setup 必须真实重新生成 native16 small_gate，再由原始 run_gate 验证该 gate 后执行 native128；两个生产器在独立进程运行。两种 sequential/block-pair 参考保持独立，真实128行 arena 和 token-major Q/K 布局按原生产器验证。

## 来源与数值准入

本层先执行原封不动的 setup runtime 来源组合，再用固定 import 替换及 backend-preflight 诊断入口替换的 patch 绑定新的 launch 模块。最终十个生成文件中七个旧输出不变。此前 M16、M128 preparation-only 和 setup-runtime 合同均保持冻结。

全来源清单用于 entry、assets 和 setup；没有旧183/187隐式过滤。原始 entry.prepare 生成 snapshot 后，运行器添加精确 `m128_launch` 身份，绑定 event commit、launch contract、实际 SETUP receipt 和已验证 M16 evidence。原始 run 的新 profile 授权分支重新核验该身份及 fresh setup/资产双凭据，然后才允许原入口继续。裸 READY 资产、旧 M16 setup、错误来源或单独复制的安全摘要不能获得准入。

授权仅适用于 canonical rows128、past0、raw=true 和该独立 profile。原始 M16 入口和900/1800秒限制不被修改。完整29节点验收仍为 false；必须保留原有27个 assigned observed gates及28个 observed fields，不能把来源检查或 setup完成记为数值 PASS。

## 单次有界执行

独立预算为 setup900秒、数值工作2400秒、外部数值阶段2430秒、整个包装器3420秒、job60分钟。外部数值期限从双凭据准入和原始 snapshot 准备之前开始，涵盖子进程清理、结果读取及最终来源校验。private clone、组合和 re-exec 保留同一绝对总期限。没有隐藏重试或自动 rerun；workflow只接受attempt1。

历史完整链约1548秒与独立 Attention loan增量约498秒合计约2046秒仅为粗略估计，2400秒没有完成保证。若超时或任一数值门槛失败，结果明确失败，不调整预算或复用旧 PASS。

## 私有数据与失败证据

权重、输入、激活、原始详细数值报告、两个参考、原生库和日志仅保留于私有 CI 工作区。上传仅为安全 summary/progress/source_hashes 三个文件，固定字段、有限计数/耗时/哈希及经过校验的仓库相对诊断位置；无张量 payload 或私有路径。

严格 JSON 规范化比较保留布尔/整数差异，原始 tuple 报告可正确与磁盘 JSON 比较。已验证但尚未完成 postflight 的结果只能作为明确 incomplete 的失败诊断，不能生成最终成功凭据。

## 重现冷测试

```sh
python -m unittest candidates.qwen2_resident_matrix.raw_kv_public_m128_run.test_admission candidates.qwen2_resident_matrix.raw_kv_public_m128_run.test_run_ci candidates.qwen2_resident_matrix.raw_kv_public_m128_run.test_prepare -q
python -O -m unittest candidates.qwen2_resident_matrix.raw_kv_public_m128_run.test_admission candidates.qwen2_resident_matrix.raw_kv_public_m128_run.test_run_ci candidates.qwen2_resident_matrix.raw_kv_public_m128_run.test_prepare -q
```

合同冻结220个非自身来源，加合同自身为221个，最终十个overlay。实际组合后的 entry/asset/setup 来源闭包逐项一致；原始 entry/official 哈希函数采用未改写 AST 提取和真实 helper 链进行来源专用检查，阻止数值包和自定义 CDLL。snapshot 来源摘要使用原始 indented JSON encoder，安全投影摘要另用 compact encoder，二者不混用。

## 首次 M128 设置失败证据

运行38913368057的安全结果为 FAILED/SETUP_FAILED/environment，总耗时43.983254秒。ZIP SHA-256为`1b2092d5dba51bf8f1e988ee2b8242160f232ef864e98a3883f4e15502d0a92c`。实际生成 setup.py 的506行运行venv backend_preflight；pip安装位于504行，二者先返回成功。非零退出不能证明具体版本、CPU能力或来源校验是哪一项失败；私有stderr未保留，不能猜测原因。

诊断修订只包裹原始 backend_preflight 调用，成功路径仍完整执行原验证器；失败继续抛出原异常。安全摘要可加入固定阶段、已加载模块的布尔/unknown检查、允许的异常类和仓库相对帧；不会复制异常文本、包版本字符串、配置转储、命令、路径或权重。原始失败记录不被覆盖。运行预算与三个安全artifact文件保持不变。

诊断检查值只描述失败后已加载模块的状态，不表示每个原始门槛都已执行。早期身份检查失败时，线程设置仍可能为 false；未加载模块或不可读 getter 为 unknown。诊断阶段及原始异常帧用于定位，不能把后续未执行条件当作根因。
