# 原 Host unseeded ABI v2 与 Scala/native 实际执行（TEMP / INCOMPLETE）

## done / PASS 精确范围
- 修复多 VerilatedContext 的当前线程选择及销毁恢复，三类 native ABI 不改变任何 RTL 算术、fatal 策略或硬件规模。
- Matrix 直接端口与 ABI 实测 400 半周期、208400 word 一致；ICG 256 点；iDMA 160 半周期 8640 word，未证明 DMA 完整搬运。
- Scala/JNA 八个真实 Matrix 叶子实例交错执行，8×512 输出分别为 1..8，8 次 completion，逐实例 200 正沿/199 反沿。仅单 step 传输及数值验证，不是完整 Host/block。
- 当前原 Host 构造配置保持 QwenBlockShape(retainedMatrix=true,matrixColumns=256)、weightReadBeats=16、pipelined=true；不采用旧 seeded/OfficialBf16/enableChunk32 历史壳。8 Matrix+8 ICG+1 iDMA 清单验证，high 1050 module、low 90 module。

## ongoing / TEMP
- session 20218：原 Host 高/低 IR 后官方 Treadle PrepareAst 与构造，单 CPU、4GiB heap、600s 预算。此快照时未到完整构造与 reset，更未发射 M128。终态以 HOST_RESULT.json 为准，不能把 ACTIVE STARTING 当实时活性证明。
- 首次绝对 TargetDir 不合法、第二次漏官方 PrepareAst 导致 None.get，失败日志和 receipt 保留；仅修测试入口。新入口源码 hash 单独记录，不倒填旧失败源码身份。
- 本路径是实际 Chisel Host/SFU IR 加真实 RTL native 叶子的混合仿真，不称纯 Chisel，也不称最终统一 RTL 回放。

## todo
- 诊断原身份 session 20218 终态；若构造通过，再连接已校验真实权重/独立参考与实际内存事务，不预填中间结果。
- Qwen2 和 0.8B L3 数学参考链更完整不代表硬件过关；L0 后续四头 fatal underflow 保留；35B 两层 CDN 权限阻塞不绕行。
- 五块完整 M128 Chisel / 同一最终 RTL 仍 0/5，有效 MAC 利用率无完整 block 实测；80%/90% 不申报。

## 临时文件
本轮未清理。保留运行引用的源码、classes、原 archive、库、IR 和唯一失败日志；不把库、生成 IR、权重、NPZ 或数据数组放入源码提交。compile.py 先编 ABI/trace；compile_host.py 依赖原已 pin 源码闭包编译结果，只编当前 Host runner；run_host.py 为有预算实际执行。
