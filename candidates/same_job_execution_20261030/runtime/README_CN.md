# Fresh CI 三 runtime owner：源代码候选，未执行

`owner_fresh.py` 是新 `SHARED_THREE_RUNTIME_OWNER_FRESH_JOB_V3` 生产/消费路径，不更名旧 V1/V2、不复制旧三个 native SHA 或 SAMPLE_SOURCE。它不安装、不导入框架、不执行参考或 DUT。

## 调用与信任边界

拥有当前 reviewed job 的 controller **安装前**冻结 OWNER_BINDING.json 并保存独立 SHA。其 identity 必须是同一个 run_id/source_commit/launch_commit（三字段、source != launch）。binding 固定原 helper e853…、本次 Python/runner/phase/phase-binding、全部原 source/tool/archive pins（53 unique archive），三个真实输出布局、独立预期完整 argv/caps。

安装完成后，controller 从其本次三个 strict-supervisor 返回的真实 native/phase/install/sidecar 文件生成并冻结 RECEIPTS.json，保留独立 SHA。此索引不是自签资格，不是远端API证明；不能接受任意外部自造 JSON 替代实际 controller 执行。两份示例 JSON 仅字段合同，包含故意不可执行 placeholder。

实际 bind CLI（必须放在 strict outer supervisor 内，按metadata全树读取预算审准后执行）：
`python -B owner_fresh.py --binding OWNER_BINDING.json --binding-sha256 SHA --receipt-index RECEIPTS.json --receipt-index-sha256 SHA --output NEW_OWNER_DIR --execute-reviewed-bind`

原生 `bind(binding_path,binding_sha,index_path,index_sha,out)` 返回 owner pin。`verify(manifest,sha,job)` 与 `lease(manifest,sha,job,profile,out)` 的接口兼容 numeric_tail；调用方还必须比较返回owner.identity与当前build/run/source/launch身份，不能仅凭相同owner根推断同job。

## 验证行为

- 每次 evidence 重核独立 binding 全source/tool/archive bytes，原53 archive清单唯一；原三install语义与已审 V2相同，Python必须3.12，原wrapper/sidecar函数沿用固定 helper。
- native只接受本次预期argv/caps、native0/error空、完整original-group cleanup及日志EOF/gzip。
- 运行结果四pin与原布局精确关联；Qwen2原wheel-lock/25runtime安装清单、Qwen35原offline checks/trust-boundary、原sidecar源码pin仍验证，不盲接任意PASS字符串。
- bind对全installed树快照并复查；lease按原五→三映射、shared owner lock、8GiB free及P0 AVX512、tree/sidecar pre/post验证；跨整个outer cleanup保持lease。没有自动删文件。
- 资源峰值仍 `INCOMPLETE_SYNCHRONOUS_CENSUS_GAPS`，owner绝不赋予reference或numeric资格。read-only tree hash是新当前安装身份，不是历史PASS迁移。

## 轻测范围

11 tiny mocked receipt/tree测试 normal/-O均通过。测试使用53个极小archive与fake helper，验证实际参数化binding/索引路径/哈希/owner串联；并拒cleanup不完整、EOF缺失、错argv/caps、互换source/launch、sidecar/档案/tree漂移、binding篡改及旧schema。没有读取真实runtime大树或加载Torch。第一版test fake.pin未将str转Path，出现2个fixture错误；仅修fake转换后11/11，不掩盖该测试初错。

**尚不可启动CI：** 实际安装controller/runtime_phase/全job资源与deadline接线由父任务继续完成，之后须独立源码和真实来源审查。此包没有workflow/activation，也没有运行授权。
