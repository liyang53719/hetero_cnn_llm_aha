# M128 实际 run 准入修复（独立后继）

已定位：冻结 ce0b 版本把 validate_rows 改成128，却漏改 run 内独立的 raw-KV `==16` 门禁。首次完整尝试在该门禁退出，未进入 Public 数值循环。失败源、回执和工作区保留。

本修复仅替换该两行门禁为严格128，继续执行原 snapshot digest、raw mode、真实 verify_snapshot、M16 成功前提、M128 assets 和源身份检查。未修改算术、21事件流程、27门禁或2400/2430预算。独立 repair pins 绑定原 ce0b 和新生成 entry pins，不覆盖原候选。

进行中：冷测、真实 Git/资产 snapshot 下调用实际 run 的准入探针及独立评审。probe 仅在 reduced runtime 第二次调用（真实 verify_snapshot 已返回，数值工作尚未开始）抛出专用哨兵。此结果不是数值运行成功。完整重试仍待批准。

## 实际调用链审计

- reduced.run 的 modes、authorize_run、raw snapshot digest、snapshot_mode、verify_snapshot 和 runtime 保留。唯一遗漏是独立的 `==16` raw guard。
- verify_snapshot → assets.verify → authentic origin + repaired M16 prerequisite + current backend + strict combined ELF 均保留；再进入 official.verify_snapshot，比较 source/rows/input/library/reference。
- reduced.run 自己执行21事件流程，不调用 official.run 或 check_fullgraph_numeric.run。那两个旧入口的 M16 prerequisite/CLI default16 属于未调用的历史路径，不删除。
- lazy suffix 的 execute_attention_owner/execute_public_suffix、PackedM128PublicProfile、实际 Host PrefixJob、tiled schedule 和 live observer 无额外 M16 行数限制。16-word beat、16-key tile 和 lane width 是物理几何，不能替换为128。
- 新生成 reduced 源身份同步写入 tiled observer runtime pins；不改 capture 代码、索引或 gate。
