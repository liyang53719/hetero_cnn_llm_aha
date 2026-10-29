# TEMP：BUILD_ONLY 单份完整硬件 binary 源码提案
基线 `9cb9613388fc3aa652a23a31de4bf6affe39b172`。旧frontend/numeric入口不修改；新增入口复用相同155源码、固定4096MAC/Vector32、provider/include/define pins、canonical/transform/SV门和串行frontend。原compile155到run_frontend_serial调用段逐字节保持；不继承R8 binary/数值PASS。

## 唯一实际执行入口（当前未执行/未发布）
```sh
python candidates/ci_frontend_materialization_r2_20261029/bootstrap_build_only.py \
 --repo "$GITHUB_WORKSPACE" --pipeline "$GITHUB_WORKSPACE/candidates/ci_frontend_pipeline_r2_20261029" \
 --work "$RUNNER_TEMP/hetero-build" --reviewed-repo-sha REVIEWED_SOURCE_SHA \
 --artifact-identity REVIEWED_V2_IDENTITY.json --execute-reviewed-once
```
未来经审workflow/单次activation提供真实V2六字段：run_id/artifact_name/source_commit/launch_commit/launch_manifest_path/launch_manifest_blob_sha。source是实际checkout，launch是实际GITHUB_SHA；须首attempt、main push before/source与after/launch对应。不能把两SHA混用。当前没有dispatch或启动文件。

完整bootstrap加installed GNU工具inventory（仅identity无compile资格）；随后fixed frontend→实际Host.mk/classes/hier/header85port条件审查→冻结derived输入pins→3child archives→Host archive→link。不是要求事先知道临时Host.mk hash；任何官方5.032模板、ABI、文件闭包不匹配都FAIL，不能用通用make接受未知输入。

分段proposal：lane600s、endpoint1800s、Down3600s、Host archive3600s、link600s；每段RSS8GiB、file512MiB、stage-tree2GB，所有job-local roots仍12,081,306,272B +free1,500,000,000B，job总21000s不变；每段启动先核剩余预算。没有承诺完整compile在6h/14GB可完成。pack先核计划复制增量，再核结果aggregate，不自动删除唯一文件。

## Artifact合同
只有全部实际native0、cleanup完整、ELF/archives真实存在且pins不漂移后才写flat7-file root `frontend/frozen_artifact/`：dut.bin/hardware.sv/driver.cpp/source_manifest.json/tool_manifest.json/build_receipt.json/frozen_artifact.json。
- schema FROZEN_FIVE_PROFILE_DUT_ARTIFACT_V2；五profile同一份manifest/binary/SV。
- source_manifest原样复制条件admission生成版本，包括fixed源码/全部308 provider/完整生成输入和derived C++ pins，不只是topSV hash。
- 同时冻结installed工具/header/link输入pins。消费机器动态依赖兼容检查仍待实际ELF审计，不能因此宣称数值job ready。
- 无weights/NPZ/reference/runtime输入、object/archive/C++树上传；失败不得上传binary artifact，只可受控summary。
- 只有build资格，完整Chisel/RTL数值0/5不变；后续各profile任务独立生成输入/参考。

## 诊断
新增summarize_build_only.py保留frontend摘要，再汇总工具阶段与5build原生阶段CPU/RSS/caps/cleanup；实际compiler/link错误扫描完整已捕获gzip并核raw/compressed SHA、完整行与原%Error census。只保留首4/末4脱敏错误（含GCC/undefined reference/make终态），4KiB上限；超8MiB也可见，不改变reader线程。64KiB摘要溢出先丢可选文本但保留终态/哈希/计数。条件审查异常另写bounded phase/class/hash/脱敏message，避免仅有计数不可诊断。

轻测范围：5source wiring normal/-O、3合成packer normal/-O、4全流compiler/工具终态诊断 normal/-O、2summary normal/-O。合成ELF不是可执行硬件、不能当真实编译证据。helper作者另有9模板/ABI测试normal/-O及已存3child源只读验证。工具inventory/真实compile/link/CI/DUT均未执行。

R2源码小修：工具库存补glibc static pthread/dl/rt archive及libmvec pin；只读证据证明当前libpthread.a与libm.so GROUP引用存在。不是改变link flags，也没有运行工具inventory/编译。旧a55d71提案保持历史，R2仅该库存tuple+bootstrap scope说明更新。
