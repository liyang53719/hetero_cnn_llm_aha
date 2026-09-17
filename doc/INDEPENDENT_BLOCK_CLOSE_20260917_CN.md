# C06.1 / C08.1 / Q21.1 收口与下一批沙箱事项

基线：`58aa2fb8a1c33b3507e778a983fd0c482891aa98`。修复源码：`55949ec472e31aa00d910cd7fd3f53e90bb056d9`。分支：`main`。

## 本轮结果

这三个软件子项已完成，唯一状态源 `doc/block_checklist.yaml` 已更新，Markdown 视图同步。C06、C08、Q21 父项仍为 ongoing，真实 frontend、官方权重、完整 block 与持久状态的验收没有被升级。

| 子项 | 已验收边界 | 本轮新增修复 |
|---|---|---|
| C06.1 | 63/64/65/255/256/588 各20个随机种子；65535命令上界和65536拒绝；有界live-set、跨窗口存活、ACK/完成/epoch异常 | frozen dataclass 内的字典仍可修改：改为快照化只读映射；运行入口重新计算并拒绝伪造寿命、peak-live或窗口元数据 |
| C08.1 | 全量tensor/state清单、来源、shape/dtype/generation、completion与ACK、逐元素bit-exact、缺失/别名/破坏拒绝 | 重新检查已比较的早期输出、参考、receipt与manifest；检测验收期间的内容变化、同字节重写或inode替换 |
| Q21.1 | FP32/BF16输入、转置、行主序[K,N]存储、分块IO、零padding、有限值RNE及全量独立回读；旧BF16转换器对照 | 打包及回读检查source身份；回读末尾检查manifest与payload身份，拒绝校验中途变化 |

分块IO不等于tile-major设备布局。本次没有修改Command128公共格式、Chisel、生产RTL、官方精度阈值或默认性能开关。

## 实际测试与证据

普通模式 **290 passed / 0 failed / 0 skipped**；`python -O` **290 passed / 0 failed / 0 skipped**，另有pytest关于非测试模块assert失效的预期警告。两种模式是同一组测试重复执行，不是580个不同用例。

组成：原控制145项、回执48项、权重73项、本轮新增破坏/兼容测试24项。新增24项在旧模块上暴露 **21 failed / 3 passed**；原始失败日志压缩保留，没有改写成PASS。

证据目录：`reports/execution/INDEPENDENT_BLOCK_CLOSE_20260917/`。`RESULT.json` 含真实命令、起止时间、退出码、环境、源文件SHA256/Git blob；`normal.log`、`optimized.log` 为原始日志；`baseline_mutations.log.gz` 为完整旧版本失败日志。`ledger_delta.json` 记录增量校验和依赖队列结果。

从源码修复提交复现所选测试：

```bash
python -m pytest -q tests/test_command_window_contract.py tests/test_block_receipt.py tests/test_weight_packing.py tests/test_independent_block_hardening.py
python -O -m pytest -q tests/test_command_window_contract.py tests/test_block_receipt.py tests/test_weight_packing.py tests/test_independent_block_hardening.py
```

执行环境是固定GitHub文件的逐字节重建，不是完整clone；这里不声称全仓库测试、完整历史证据校验或原来的大集合runner已重跑。旧done记录与证据保持不变，本次检查了新增证据哈希、全部44个父任务依赖元数据、父子聚合、状态合法性、无循环和无关记录不变。完整工作区仍可执行既有 `python scripts/block_checklist.py validate` 复核全部历史工件。

文件变化检测是校验前后观测，不是原子文件系统快照或安全隔离机制；生产者自报的零fallback也不构成实际RTL执行证明。C02近似误差公式仍未注册，未知公式继续拒绝。

## 下一批不依赖本地agent输出的任务

以下三个独立子项已登记在唯一checklist中，状态均为 **to do**，没有替其他agent认领。原plan字节及父项完整门禁不变。建议执行顺序为 **C04.1 → C02.1 → C07.1**；默认队列仍按P0及编号排序。

| 优先级 / 子项 | 可先行范围与前置 | 验收门禁 | 仍不能宣称完成的内容 |
|---|---|---|---|
| P0 / C04.1 | 现有Command128/descriptor的严格类型、范围、旧字节回环；前置C03.1、C06.1已done | bool/float/负数/越界和非法枚举在编码前拒绝；合法旧字段、字节与端序不变；56bit地址、链边界与负例覆盖；普通/-O均通过 | 新policy ABI、3bit kind扩展或Host到RTL接入，交给C04.2 |
| P0 / C02.1 | 复用block_receipt与precision_policy，做公式注册、全量统计和缺合同拒绝；前置C08.1已done | 未注册公式和缺来源拒绝；零参考/极端值/NaN/全量覆盖测试；离散路由及bit-exact域不得偷偷采用近似 | 不自行解释或放宽0.002；官方双参考与每producer完整精度冻结在C02.2 |
| P0 / C07.1 | 复用state transaction/commit合同，做合成多状态域事件trace与失败恢复测试；前置C06.1、C08.1已done | 非零旧状态、layer/request/epoch/generation隔离；最后ACK失败不提交；poison后成功ACK仍计物理字节；reset/迟到响应不污染新请求 | 实际state-memory owner、DDR/SRAM账本及RTL续算，交给C07.2 |

C04.1有已复现入口缺陷，不只是抽象建议：当前`Command128(..., flags=True)`编码为1，`flags=1.5`编码为1，`flags=-0.5`编码为0。原因是构造校验和pack使用`int(value)`，不能据此判定原输入是合法整数。该问题本轮仅做探测并登记，没有顺便修改公共编码入口；修复前先保存旧合法字节黄金样本。

## 仍需等待的集成任务

C06.2等待C04；C08.2等待C00和C02；Q21.2等待C01/C02/C08及官方checkpoint和真实输入；C03.2等待C01。不能因为三个软件子项done，就把这些集成任务强行派发或标done。

本地agent当前可以优先处理C00.2完整工作区/工具/资源基线，随后C01.2固定官方revision/forward/index；不要重做本次三个done子项。后续Q20、官方block、长仿真和实际DUT计数仍按原依赖门禁执行。
