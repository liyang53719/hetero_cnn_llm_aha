# 三模型 block：计划与唯一执行清单

计划是 `three_model_typical_block_closure_20260917_zh.yaml`；唯一执行状态来源是 `block_checklist.yaml`。`BLOCK_CHECKLIST.md` 是自动生成的只读视图。

完整计划已迁入根目录 `doc/`。旧 `plans/` 路径是兼容符号链接，不再维护第二份计划；计划字节、44个任务编号和验收门禁保持不变。计划中的“待执行”是编制时快照，不用于派工。Windows 未启用符号链接时直接使用 `doc/` 路径；不要把链接文本当作 YAML 解析。

## 状态与防重复执行

清单状态仅使用 `to do`、`ongoing`、`done`。子项可以单独验收，但父项必须满足全部子项和原计划依赖才能为 done。父项 ongoing 可以表示“已有部分成果、等待剩余工作”，不代表后台进程正在运行。具体领取状态看叶子项和负责人。

当前44个原任务中：39个 to do，5个 ongoing，0个 done。拆分后52个叶子事项中：47个 to do、5个 done、0个 ongoing。

已完成且不应重复开发的范围：

| 子项 | 完成内容 | 不包含 |
|---|---|---|
| C00.1 | 五个选定源文件Git字节身份、历史SiLU日志字节核对 | 全工作区/filelist/工具/SRAM资源验收 |
| C01.1 | 模型入口显式校验，修复 python -O 绕过、未知family误接受 | 官方forward/固定权重重新核验 |
| C03.1 | hidden/Q/KV/GDN独立宽度与容量预算合同 | 实际Chisel shape和payload改造 |
| P00.1 | 归档Qwen2计数复算、非法回执拒绝、单512-bit通道上界检查器 | 最新HEAD的RTL性能测量 |
| P01.1 | 继承已发布SiLU组件数值/异常结果 | 完整Host+pinned-iDMA双层A/B |

每个 done 子项都有固定设计提交、范围、文件和 SHA256；新完成项还绑定实际选定回归报告。历史组件仅复核字节，不冒称本轮重跑。生产 `OVERLAP_SILU` 默认仍为0，本轮没有改变RTL或浮点配方。

## 本地 agent 操作

先同步、校验，再读取仅属于自己的可执行队列（Python 3.10+、PyYAML）：

```bash
git pull --ff-only origin main
python3 scripts/block_checklist.py validate
python3 scripts/block_checklist.py next --executor local-agent
```

目前本地队列第一项为 C00.2；沙箱队列为 C06.1、C08.1、Q21.1。`done` 和已有负责人领取的 `ongoing` 叶项不会进入队列。不能为了获得空闲任务而直接清空状态。

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

## 可以不等本地输出继续开发

C06.1：长命令容量与live-set专项控制测试（63/64/65/255/256/588边界），不需要官方权重；仍不能称作588条模型命令数值RTL通过。

C08.1：完整tensor/state回执schema与比较器框架，先覆盖缺失、重复、来源与全量覆盖检查；误差公式等待C02正式冻结，不擅改0.002。

Q21.1：通用权重转置、分块、BF16打包与字节回读，可先用合成数据验证；真实checkpoint导出为Q21.2，不互相替代。

## 本轮代码与测试

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
