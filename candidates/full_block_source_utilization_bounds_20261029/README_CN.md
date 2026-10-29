# TEMP / INCOMPLETE：源码性能界

仅源码静态几何/握手下界与原始Torch参考占用摘要。不是Chisel完整数值PASS，不是RTL实测，也不是90%资格。未包含IR、RTL、class、输入/权重/原始expert IDs。

复现静态计数：`python full_block_bounds.py`，stdout应与FULL_BLOCK_BOUNDS.json逐字节相同。
可选本地参考占用核验：`python verify_occupancy.py --p3-reference <P3参考目录> --p4-reference <P4参考目录>`；需要已固定RESULT.json及gate.0.2二进制，数据不随包发布。没有参考时仍可复现条件静态界，但不能声称重新验证占用来源。

SOURCE_PINS.json为仓库相对源路径和sha256。HostBlockCommands当前修正版与历史审计版仅997行不同，引用1317/1453/1530等算子形状行完全一致；历史pin保留仅供溯源。

全部统计条件/分母/矩形与因果口径见FULL_BLOCK_COUNTS_CN.md，关键控制复核见CRITICAL_RECHECK_CN.md。
