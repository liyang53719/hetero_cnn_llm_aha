# 15:33 真实活跃联合恢复与 L3 后续数值（INCOMPLETE）

现场未回退；远端基线 6c4a8591，CI 43445562098 success，仅仓库 payload guard。工作树干净，旧 84795 状态仍不确定，未重启。清单已核，清理 0，保留唯一证据与运行依赖。

同一真实 shared17 的 8 Matrix（共4096 MAC）、8 ICG、1 DMA 活跃状态恢复通过：Matrix 各持非零结果，DMA 已接受 AR、R 未返回，保存完整模型/context/wrapper/registry 及外部 AXI 账本。fresh-process 不重发命令/描述符，34拍17路全部 pending 输入与输出逐byte一致，DMA 64B 数据/strobe/完成背压一致。无重新编译；仅联合叶子恢复，不冒 Host 或完整block。

完整 Host + shared17 + driver/AXI/control 状态容器已接入。真实 held-result 未消费时 cycle5 保存，fresh-process 不 reset/relaunch，12拍完整 Host/native 状态、输出、收敛次数和提交序号一致。scratch为空，无真实写回资格。真实 Qwen2 首RMS输入 cycle439（已读4×64B）安全切点全状态保存，fresh-process不reset/relaunch/重算前缀，后续120拍全部轨迹相同；没有首RMS输出/写回或完成。

独立 Python 已推进 L3 M128 Q/K normalization 与 partial RoPE：Q [128,8,256]、K [128,2,256]，Q+gate 交错布局只取Q，原FP32顺序及RoPE每乘法BF16物化不变；全部1280组sqrt/div与573440次BF16转换已检查，未出现fatal。1610752个Add/Mul节点核对，缓存miss323866，不冒同数量独立Fraction调用。不是 Chisel/RTL 完整通过，不预装中间参考。

五块 M128 完整原Chisel数值仍 0/5，完整RTL和有效MAC利用率未测。35B真实权重缺失，原L0 underflow FAIL 保持。源码、完整日志和数据本地保留；远端只允许摘要。
