# MODEL_CANDIDATE 打包到实际 exporter CLI 回归

范围为 **ALL_SYNTHETIC_CANDIDATE_EVIDENCE**。不编译、不执行 ELF／DUT、不下载、不读取旧 ELF／SV；只执行 Python 测试和实际 exporter CLI。旧 O1 source/tool/build/frozen 元数据与驱动源码仅作精确 SHA 固定的语法模板，不迁移旧构建或数值资格。

```bash
python run_fixture.py --source-root /path/to/reviewed-checkout \
  --old-payload /path/to/pinned-old-seven-files \
  --old-exporter /path/to/pinned-old/export_model_build.py --output /path/to/fresh-output
python -O run_fixture.py --source-root /path/to/reviewed-checkout \
  --old-payload /path/to/pinned-old-seven-files \
  --old-exporter /path/to/pinned-old/export_model_build.py --output /path/to/other-fresh-output
```

测试先逐项核当前真实 SOURCE_PINS 及八项实现映射；再构造明确隔离的合成 checkout/catalog、身份、20 个阶段及 8 个准备阶段收据。隔离 catalog 含当前 candidate Python 实现的原字节与必要 support/ABI 文件。实际 exporter 的 `source_pins` 必须重核这一隔离 catalog，不 mock；此 catalog 不冒充实际 GitHub 提交的构建回执。

完整受测链：真实十个 source role 字节及两个 runtime table expectation → 真 `model_source_evidence.record` → 真 `pack`（包含完整 13,529 generation + 11,689 tool 库存槽；未知 runner 字节明确以小合成内容代替，两项原 0 B 语义保留）→ exact 七件／完整 compilation proof → 真 exporter Python subprocess CLI。无 mock record、source_pins、strict 或 verify。

目录与真实任务一致：`work/shared/build/frontend/model_candidate_artifact`。CLI 以合成 GITHUB 身份和实际 monotonic 时钟运行，必须 native 0、summary ≤ 64 KiB、保留 UNREVIEWED 状态。最终 GITHUB_OUTPUT 的 artifact_dir／artifact_name 与 workflow 原七条枚举精确相符，各文件真实存在、非空、摘要 manifest digest 一致。旧 `frozen_artifact` 诱饵目录存在但不被选择。

反例保留原五类 pack 拒绝，另核九类 exporter 拒绝：旧目录、同 hash 但自报另一路径的 manifest、额外文件、空文件、缺文件、相同字节的外部 symlink、内容 hash 漂移、外部 run 身份不符、准备阶段缺 strict EOF。拒绝时不得生成 summary／GITHUB_OUTPUT。

发布仅脚本、此说明、有限安全摘要。不发布旧元数据正文、合成库存／七件、原日志或任何运行批准。源/路径完整性回归不等于新构建、模型数值或最终 RTL 通过。

另以原 bug exporter 的固定 SHA 原字节作对照 Python subprocess，真实导入当前 source-pins／verify 门、同一 work 布局及旧目录诱饵，要求非零且无输出；旧脚本放于测试控制目录，不改实际受审 source catalog。
