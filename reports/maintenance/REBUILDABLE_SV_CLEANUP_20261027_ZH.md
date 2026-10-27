# 2026-10-27：两份可恢复历史生成 SV 的普通清理

## 范围与验收边界

本批仅移除下表两个历史生成 `HostBlockTop.sv` 工作树路径，并加入本中文记录。所有 `RESULT.json`、pin/hash、SCOPE、复现源码、参考输入、失败归因、日志及冻结证据保持原字节；不修改当前 Host/Matrix/Vector 源码、canonical 74 项任务状态，也不删除 Git 历史或运行 git gc。

这是可恢复产物维护，不是新的硬件或数值 PASS。历史 RESULT 的原标签保留，不据此升级当前五块完整 M128 验收；当前仍为 **0/5**。不包含权重、原始参考或新的目标执行。

## 精确删除身份

### A

- 路径：`reports/execution/COALESCED_REAL2_9b09f201842b/tiny/generated/HostBlockTop.sv`
- 大小：55,533,887 B
- Git blob SHA-1：`2b45ed9f5925796ec9d3b9da7f389955e6e80fa2`
- 内容 SHA-256：`fc352f09635897e46518b939e55b2ff17804e23c9d58d31d4cb712f32589580e`
- 保留摘要：`reports/execution/COALESCED_REAL2_9b09f201842b/tiny/RESULT.json`，Git blob `fdec1758c46feffbe1f0d073c60171ece296f839`。

### B

- 路径：`reports/execution/NATIVE_BF16_REAL2_52adab91c893/work/native_real2/generated/HostBlockTop.sv`
- 大小：54,976,533 B
- Git blob SHA-1：`46551d7f86fb81bbfc579062faa31b3bad21590b`
- 内容 SHA-256：`a73631fdfc409d6d1dd33a0c6b138c24864da821793b93f2209a87233898f95c`
- 保留摘要：`reports/execution/NATIVE_BF16_REAL2_52adab91c893/work/native_real2/RESULT.json`，Git blob `a249db096c5225210df653627efa9f9d215930d3`。

## 可恢复性与当前引用核验

独立只读审计已经对固定公开提交 `3f1ec9a8439090ba101bdda775f1f19578b507eb` 的两文件完整流式校验 Git blob、SHA-256 与字节数，并分别核对 4 个本地 checkout 的 8 份未修改工作副本。失败的旧 ref/大文件 connector 获取不计作恢复成功；成功证据来自固定提交的公开 raw 完整流。该审计摘要 SHA-256 为 `a6400d4ba4c2445cba0e5e4d39f21917b719758f8893cc9dbbc1d6d8041ed343`。

本批以已验证新父提交 `4d1f1eacf70d52d5fb45505c6dacece6a8f962aa` 为基线；其完整 Git tree 仍保有上表相同 blob 身份，未再读取约 110 MB 原 SV。五名当前任务负责人分别确认其活动编译/发射/审查/发布任务不依赖这两个路径；这只是当时明确任务范围的确认，不是对全仓永久无引用的断言。

两个文件合计 **110,510,420 B（约 105.39 MiB）/checkout**。后续若独立清理四个已核副本，已观察 allocated 总量约 **421.59 MiB**；本记录不声称本地删除已经执行或空间已经释放。普通删除保留历史 Git blobs，**不会回收 Git 历史占用**。本地清理必须等本远端提交验证成功、再次确认无新引用或修改后，按独立授权执行。

## 恢复与回滚

历史提交和 blobs 保留。需要恢复时，在独立工作树从固定提交还原精确路径，再核对上表 size/SHA-256；不要覆盖未保存的用户修改：

```sh
git restore --source=3f1ec9a8439090ba101bdda775f1f19578b507eb --worktree -- \
  reports/execution/COALESCED_REAL2_9b09f201842b/tiny/generated/HostBlockTop.sv \
  reports/execution/NATIVE_BF16_REAL2_52adab91c893/work/native_real2/generated/HostBlockTop.sv
```

若需撤销整个已发布清理提交，使用普通 `git revert <清理提交SHA>`，经验证后正常非 force 推送；不改写历史。各本地 checkout 的独立还原 HEAD 已由清理审计保留，不将某个旧 checkout 冒充当前 main。

## 本批测试/CI 口径

按父提交的 111 个 exact workflow blobs 静态匹配这两个删除路径及本记录路径，仅触发既有 `reject-rebuildable-git-payloads`。三个 `workflow_run` 下游均不监听该 guard；不触发原生/HDL 或五块数值任务。该预测不是已执行 CI 的替代，发布后仍须核本提交唯一自然 guard 的终态，不手动 dispatch/重试。即使 guard 通过，也仅证明 Git 载荷政策与其小测试，不证明目标硬件通过。
