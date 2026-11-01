# 空源输入 pin 的完整打包回归（仅合成证据）

此测试不编译、不执行 ELF、不下载、不读取旧 ELF/SV；不代表任何新硬件数值通过。

```bash
python run_fixture.py --source-root /path/to/reviewed-checkout \
  --old-payload /path/to/pinned-old-seven-files --output /path/to/fresh-output
python -O run_fixture.py --source-root /path/to/reviewed-checkout \
  --old-payload /path/to/pinned-old-seven-files --output /path/to/other-fresh-output
```

旧模板来自已闭合 O1 build 的 source/tool/build/frozen 四份元数据及驱动源；脚本内固定五文件 SHA。只复用其完整 Make/.d/编译阶段语法模板，不迁移旧构建完成或数值资格。

- 先逐文件核当前 SOURCE_PINS 与八项实际 producer implementation map。pack、proof、model_source_evidence 直接使用该 source-root 中的完整原字节，测试不修改 map 或返回值。
- 13,529 个旧 generation 输入槽和 11,689 个 tool 输入槽完整映射为小型本地合成文件并重新计算 SHA；**不声称恢复或重验全部 runner 文件字节**。IDMA `.gitkeep` 和 Python `urllib/__init__.py` 两个原空源槽仍为真实 0 B／空 SHA。
- 十个 source role 使用当前实际源码／驱动／头文件／program manifest 字节；另外两个 runtime table expectation 从真实 program manifest 合同导出。实际 `model_source_evidence.record` 产生完整十二 role，不 mock。
- 构造阶段的既有 synthetic constructor 只提供测试模板；最终受测链真正执行 record → pack（两次完整输入库存核验）→ exact 七件 → `verify_candidate_seven` → 完整 compilation proof。20 阶段收据／新身份／重建的 122 端口 header／ELF 与 SV 占位均明确合成。
- 反例：空源 SHA 错误、缺失源、空 artifact、source metadata 超过 16 MiB、role 改变但一般 pin 同步更新，均必须拒绝；原非空 payload／尺寸／精确源合同未放宽。

可信固定 IDMA 清单与其 `.gitkeep` 的另行只读小文件重验，证明该 provider 正常包含空源输入；不能证明远端失败日志中的具体拒绝文件（未取得该路径）。

发布仅本脚本、此说明和有限摘要。所有旧元数据正文、25,230 个合成 pin 文件、约 11 MiB 合成七件及原日志均不发布。测试输出不是下一次执行输入或批准文档。
