# 三模型 block：计划与唯一执行清单

计划是 `three_model_typical_block_closure_20260917_zh.yaml`；唯一执行状态来源是 `block_checklist.yaml`。`BLOCK_CHECKLIST.md` 是自动生成的只读视图。

完整计划已迁入根目录 `doc/`。旧 `plans/` 路径是兼容符号链接，不再维护第二份计划；计划与清单统一在此维护；历史44个任务和后续新增的U00/U01共46个父任务均保留，验收门禁不因文档更新而放宽。计划中的“待执行”是编制时快照，不用于派工。Windows 未启用符号链接时直接使用 `doc/` 路径；不要把链接文本当作 YAML 解析。

## QK实际Matrix局部RTL更新（2026-10-15）

[真实Matrix局部数值单元](../candidates/qwen2_rectangular_qk_numeric/README.md) `876cf2c9` 的[唯一CI](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38729837511)已独审通过：实例化八个512MAC端点，每step只启用一个32列slice，89 step共45568实际FMA、704 B ACK，375632个有限值逐位比较和176个NaN分类检查通过。四场景包含符号零、M17尾块和因果非有限隔离。七阶段全部退出0，runner213秒；生成RTL SHA `452f875e1cf28277cd665e4026793c9c36327e480ae52f02a0af5048c14b9a90`。

本批只覆盖实际Matrix partial：B仍是80KiB host测试存储，完整十六stripe、有序Scalar fold、两次BF16、softmax和A/B真实SRAM接线未验。4313局部诊断拍包含测试背压/reset，不是整块性能。下一步优先exact64 Q/K投影、保持原图的QK与共享A驻留、原softmax及实际n1下gate的完整M128模型必要集成；Scalar接口和成本并行审计，暂不扩小单元RTL。原M128四项失败及完整RTL/90%利用率目标保留。

## 共享A与QK控制RTL更新（2026-10-15）

[共享A缓存接线](../candidates/qwen2_attention_shared_a_integration/README.md) `e471649d` 已完成18项普通/优化冷测试及11项合成M1/M2案例；使用原Dense A Banks，故障排空后仍保留Matrix需复位标志。

[默认关闭QK控制profile](../candidates/qwen2_rectangular_qk_profile/README.md) `7f9b5cbb` 的[独立单元CI](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38725277907)成功：Chisel确实生成控制RTL并经Verilator跑过3项测试，编译/仿真阶段283秒。Matrix返回由测试控制，真实4096MAC阵列RTL未实例化；host42+9+8项数值/ACK回归另行通过。下一步是冻结最小实际Matrix接线数值case及有界单元预算。原完整M128四项失败和五block待验状态保持，完整硬件周期与利用率仍无实测。

## Attention供数更新（2026-10-15）

已发布 [有限KV缓存候选](../candidates/qwen2_attention_resident_candidate/README.md) `8894ee2d`：M1/M2合成输入的输出及十个中间观察字段逐位相同，五正例、九故障注入、13项普通及优化冷测通过；[源码检查CI](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38719561588)成功。M2外部读取由49152降至16384字节，Matrix/Scalar请求数量不变。本地端口与ACK有成本，完整链A仲裁和Chisel尚未接线，未验证M128缓存prefill。

[raw到Bias有界交接](../candidates/qwen2_raw_bias_handoff/README.md) `4700cf99`与[转置写合并控制](../candidates/qwen2_transposed_exact_scheduler/README.md) `026b6a89`也已独审发布，分别14及15项普通/优化测试通过。当前主瓶颈转向实际PV32 K/V重复访存及有效lane；现行完整块独立带宽容量界约47.80%、Matrix issue容量界约55.39%，均非实测利用率。缓存只改善供数，原M128四项数值失败仍保留。计划与清单新增“Attention供数与完整块账本增量20261015”记录完整80/90预算及下一步，原任务状态不变。

## 精确树调度更新（2026-10-15）

已发布 `6576194c` 的五context、两A槽精确树行为模型，普通及优化Python各30项合成测试通过；[源码与条件资源账本](../candidates/qwen2_exact_tree_scheduler/README.md)、[源码上传检查CI](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/38712822743)。原M128完整数值验收仍FAILED，P2/P4固定六案例均未形成可接受图，任务状态不变。

当前串行M16模型为88448条件周期，冷B端口上界12.5%，性能NO_GO。下一步是复用真实transposed M128×N32布局，建模有界A转置写合并、有限权重供数和精确树frontier。现RMS写FP32容器到DDR、完整ACK后Dense再读；没有已证明的跨stage免费驻留。新FP32 Add/restore与相关控制尚未接入Chisel，所有硬件周期、利用率及占空比仍未实测。详细边界与改造顺序见计划、清单的“精确树调度增量20261015”节。

## 状态与防重复执行

清单状态仅使用 `to do`、`ongoing`、`done`。子项可以单独验收，但父项必须满足全部子项和原计划依赖才能为 done。父项 ongoing 可以表示“已有部分成果、等待剩余工作”，不代表后台进程正在运行。具体领取状态看叶子项和负责人。

截至2026-10-15，46个父任务中：34个 to do、12个 ongoing、0个 done。拆分后62个叶子事项中：47个 to do、13个 done、2个 ongoing。此次只更新进度说明，任务状态未变。

以下是2026-09-17首批已完成且不应重复开发的范围；当前全部13个 done 叶项以唯一清单及只读视图为准：

| 子项 | 完成内容 | 不包含 |
|---|---|---|
| C00.1 | 五个选定源文件Git字节身份、历史SiLU日志字节核对 | 全工作区/filelist/工具/SRAM资源验收 |
| C01.1 | 模型入口显式校验，修复 python -O 绕过、未知family误接受 | 官方forward/固定权重重新核验 |
| C03.1 | hidden/Q/KV/GDN独立宽度与容量预算合同 | 实际Chisel shape和payload改造 |
| P00.1 | 归档Qwen2计数复算、非法回执拒绝、单512-bit通道上界检查器 | 最新HEAD的RTL性能测量 |
| P01.1 | 继承已发布SiLU组件数值/异常结果 | 完整Host+pinned-iDMA双层A/B |

每个 done 子项都有固定设计提交、范围、文件和 SHA256；新完成项还绑定实际选定回归报告。历史组件仅复核字节，不冒称本轮重跑。生产 `OVERLAP_SILU` 默认仍为0，本轮没有改变RTL或浮点配方。

## 当前主线（2026-10-15）

Qwen2 M128 的同次 fresh 完整 public21 软件链已实际执行，21 completion / 17 owner jobs / 1 launch result，协议、same-live、退债、cache copy、来源和资源门通过；原24个数值门中4个失败，因此完整链仍为 FAILED。scores/logits 共用一个观察字段，另有 prob 与 FFN gate 失败；最终 y 通过原 block 门不能覆盖中间失败。

当前先做 QK/prob 同输入算术与传播隔离的独立复核、FFN gate 同 n1 隔离，以及独立 Q/K 归约候选与固定4096资源成本核对，不盲跑完整 block。详见 [完整链失败与后续范围](QWEN2_M128_FULLBLOCK_NUMERIC_FAILURE_20261015_CN.md)；唯一清单末尾的 20261015 节为当前 done / ongoing / todo 入口，旧日期段落保留历史。

软件 useful/executed=0.911591 仅操作效率；硬件 cycles/utilization/duty 均 null，RTL 未执行。先 Qwen2 完整 block，再 Qwen3.5-0.8B、35B-A3B 各 L0/L3；后四 block 本轮未推进。128 仍未通过，1024/1224 长度待澄清，不阻塞128。

## 本地 agent 操作

先同步、校验，再读取仅属于自己的可执行队列（Python 3.10+、PyYAML）：

```bash
git pull --ff-only origin main
python3 scripts/block_checklist.py validate
python3 scripts/block_checklist.py next --executor local-agent
```

队列须由上述命令实时读取，不沿用旧正文派工快照。C06.1、C08.1、Q21.1等历史子项已 done，不应重复领取。`done` 和已有负责人领取的 `ongoing` 叶项不会进入队列。不能为了获得空闲任务而直接清空状态。

领取例子（请使用能区分机器/会话的负责人名称）：

```bash
SHA=$(python3 -c 'import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("doc/block_checklist.yaml").read_bytes()).hexdigest())')
python3 scripts/block_checklist.py mark C00.2 ongoing \
  --owner local-agent@workstation --expect-sha "$SHA"
python3 scripts/block_checklist.py render > doc/BLOCK_CHECKLIST.md
git add doc/block_checklist.yaml doc/BLOCK_CHECKLIST.md
git commit -m "work: claim C00.2 baseline integration"
git push origin main
```

**只有领取记录成功推送后才开始执行。**文件锁和 SHA 比较仅保护同一工作区；跨机器必须依靠普通非强制 Git 推送。推送冲突时重新读取远端清单，确认未被他人领取，不覆盖别人的状态或强推。

完成时使用 `mark <编号> done --owner <相同负责人> --expect-sha <当前清单SHA> --proof <JSON证据记录>`。证据记录字段为 `文件`（仓库相对路径）、`SHA256`、`设计提交`（40位）、`范围`；可附 `关联文件` 的路径与哈希。先保存真实测试/门禁结果，再标完成，最后将代码、证据、清单、只读视图一并提交。校验器验证文件存在和哈希，不会替人审阅实验真假或替代模型完整门禁。

缺工具或权重写在说明里，不引入第四种状态。需要释放自己正在执行的事项时，用 `mark <编号> 'to do' --owner <相同负责人> --expect-sha <SHA> --reason <保留进度与释放原因>`。已完成的 done 不允许通过此工具重新打开；源码或证据变化时先审阅并创建明确的增量/集成子项，不能让旧组件开发再次进入待办。

## 历史独立子项边界（以下三项已 done，不再派工）

C06.1：长命令容量与live-set专项控制测试（63/64/65/255/256/588边界），不需要官方权重；仍不能称作588条模型命令数值RTL通过。

C08.1：完整tensor/state回执schema与比较器框架，先覆盖缺失、重复、来源与全量覆盖检查；误差公式等待C02正式冻结，不擅改0.002。

Q21.1：通用权重转置、分块、BF16打包与字节回读，可先用合成数据验证；真实checkpoint导出为Q21.2，不互相替代。

## 历史代码与测试（2026-09-17）

源代码提交：`a027e6f3d0d3956ebad09666b1bc530e08150965`（模型校验/几何）、`a1265299b725ecff616d3ab751fcf9638d896d9a`（清单工具/计数审计）。

选定回归164项，普通Python和 `python -O` 均实际通过；更新完成清单后另跑33项清单测试通过。范围是编译器、派生几何、计数、清单与计划测试，不是完整仓库测试、RTL或官方权重推理。

```bash
python3 -m pytest -q tests/test_model_geometry.py tests/test_qwen_family_contracts.py \
  tests/test_block_performance.py tests/test_block_checklist.py tests/test_typical_block_plan.py
python3 -O -m pytest -q tests/test_model_geometry.py tests/test_qwen_family_contracts.py \
  tests/test_block_performance.py tests/test_block_checklist.py tests/test_typical_block_plan.py
python3 scripts/audit_block_performance.py tests/fixtures/coalesced_real2_terminal_summary.txt
```

原始日志、修复前后实际Python进程输出、派生几何、归档计数和来源身份保存在 `reports/execution/BLOCK_CHECKLIST_ADVANCE_20260917/`。此前163项的中间运行日志仍保留；以 `regression_164*.log` 和 `tests_execution.json` 为本次最终选定回归结果。
