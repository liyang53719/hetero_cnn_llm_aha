# 实际 frontend / 122-port ABI / 单 driver TU 有界证据；SV 整体 re-pin 暂缓

实际 run `41118989254` 成功。原始两个元数据 JSON 保存在 `metadata/`，逐字节不改。其 status 仍为 `FRONTEND_QUALIFICATION_OBSERVED_UNREVIEWED`；所有 `sv_accepted`、`numerical_pass` 保持 false。本包不修改 production 门、源码闭包或运行身份。

## 已确认范围

24 阶段 strict/native0，cleanup/EOF/gzip 完整、error0。实际 frontend、真实 122-port Verilator header（旧85逐项保留 +37只读输出/948bits）以及真实 GCC 单 driver TU `.o/.d` 的限定资格通过；object 是 ET_REL，不是完整归档/链接或 DUT。原件保留全阶段耗时/RSS/identity/完整依赖。host frontend 382.55016183 秒、RSS 9596760064 B；driver TU 9.280295733 秒、RSS 282021888 B。CPU avx512f=true 仅观察，runtime_qualified=false。五块 M128 完整数值仍0/5，最终RTL回放未完成，利用率未测。

预算口径仍 wholejob21000 / inner12000 / executionstep15780 / declared envelope17100；prep 保留原1800秒更紧动态约束，未因成功放宽。单元小编译旧证据不替代此次真实阶段。

## 必须继续审核的 SV 差异

同一现行 scanner 下92个SV模块名字/次序不变，82 normalized 相同，10改变：已审8个观察模块之外另有 `Public21QkvReductionRouter`、`TransposedDenseDownOwner`。这两项 HIGH canonical 相同仍不能证明后续 transform/SV 等价。61-bit key 受 SourceInfo 路径影响只是候选解释，尚缺绑定实际旧/新 SV hash 的严格差异证明。`TWO_MODULE_PENDING.json` 保留准确旧新摘要。**SV 整体 re-pin 暂缓，不能把此解释标 PASS 或自动接受新硬锁。** root 已安排最小 SV-only proof 方案设计，尚未启动新 job；不得重复 frontend 完整任务。

## 可移植复现（只读，本地轻审计）

准备 source `a06b51416090fce2ad3d04336c82a5b7a2d00b97` 的精确完整 checkout。设置 `HETERO_AUDIT_REPO_ROOT` 指向它；无变量时默认当前已发布 evidence 所属仓库根。脚本依旧核完整644 SOURCE_PINS SHA `99adde3413b505b67ee68939e992f6e11eb50274662a1042417ce8121b5797c8`，不是仅信任 checkout 名称。

```sh
export HETERO_AUDIT_REPO_ROOT=/absolute/exact-source-checkout
python -B /absolute/evidence/audit.py --metadata-dir /absolute/evidence/metadata --output /absolute/new-audit.json
cd /absolute/evidence
python -B -m unittest -v test_audit
python -O -B -m unittest -v test_audit
```

输出路径必须尚不存在；metadata目录只能有原2个JSON。5项测试为 synthetic，始终不授权SV/数值通过；真实资格依据原run元数据、严格projector及完整闭包，不来自合成测试。portable版本只改根目录定位，未改审计算法；`AUDIT_TOOL_PINS.json`记录原/portable源hash及原产物pin。原`ACTUAL_AUDIT.json`由原工具生成，本包复现输出须逐对象相等。

ZIP `13007774506`：33043 B / SHA256 `e40695d8b3fcce11b37834bfbcd420624f4afa0dbd5658a0e7932b23195f44c7`；root已核API digest、两个白名单成员及2MiB上限。解包不属于本脚本功能。无 raw SV/IR/annotations/classes/object/rawlog/weights 上传；只提交可复现源码/pins及有界元数据。
