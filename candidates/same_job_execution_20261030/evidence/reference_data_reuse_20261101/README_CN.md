# 真实只读参考复用纯链（非 DUT 资格）

2026-11-01 两个顺序原监督阶段均 native 0、严格 cleanup/reader EOF。实际 839 源 snapshot 的哈希在 SAFE_EVIDENCE 中；最终发布另加测试/证据不能冒充本次执行 catalog。

- 全五参考：122 个 tensor、44,262,400 B，旧新 device/inode/size/SHA 一致；前后逐文件 hash，RESULT 为独立新文件。
- P0：实际 provider.initialize → 参考 hardlink → 原 P0 数据全转换复验 → 双根 transport → hydrate/corrector/assemble/load_binding/最终 spans；94,916,608 B 输入不复制、不别名，fresh 同根，无共同祖先放宽。
- 监督每阶段 CPU 180 s / wall 210 s、RSS 2 GiB / AS 2.5 GiB，原 8 GiB 磁盘保留与旧 owner 5 GiB；新 aggregate TREE 12,037,043,872 B 是更严格工程 cap，不是已证明峰值。

两 runner 参数均显式，先固定 source catalog/输入 SHA，再由原有界 supervisor 执行；禁止进程派生和网络。参考链接只复用数据，不迁移旧 DUT、ABI 或数值 PASS。hardlink 不是 OS 强制只读隔离：代码禁止写/chmod/truncate，真实前后 hash 是检测而非不可变保证；EXDEV 失败，无 copy fallback。

P0 runner 的历史 ABI 仅用于纯 schema 检查，execution_admitted/live_owner_checked 均 false。未执行任何新 DUT；后续正式 source/review/budget、fresh ABI/import、原磁盘和资源门仍须完整通过。
