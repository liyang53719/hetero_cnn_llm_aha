# INCOMPLETE：独立 Python LegacyV0 21-op 参考

实现：完整21条原Host顺序的符号buffer调度；纯Python Fraction二进制精确值及单次RNE，逐K BF16入口FMA Dense、独立FP32 bias/residual加法、分半RoPE的分离乘加、KV拷贝。无C++/libm oracle、无numpy matmul、无Torch归约。numpy只用于uint32存储和shape，不参与算术。

复用原 `prefill_rounding_1934/rational_oracle.py` 的 round_fraction，原文件未改。其GDN exact_recurrence未调用。补充IEEE finite解析、signed-zero和操作预算。原 generate_bf16_fma_vectors.py使用libm fmaf，因此没有把它包装成独立Python验收。

原源码顺序依据：Qwen2Block.scala:62 Legacy materialize为恒等；295–301 Matrix入口BF16RNE；554–566 RMS独立平方/顺序累加/mean/epsilon/sqrt/div；694–705 RoPE分离产品加法；StreamingDense.scala:130–148各context逐K。状态失配、下溢FAIL不被数学参考覆盖：当前Fraction原语给IEEE渐进下溢数学值，不声称原RTL允许这些值。NaN/Inf/overflow未映射硬件状态，明确抛IncompleteReference。

缺失：RMS完整sqrt/div及硬件status契约、QK16 lane归约/scale、原exp近似softmax、PV和ScheduledSiluOwner契约。`run()`在任何tensor执行前显式抛错，列出缺失项，不产生full forward结果。未来实现前继续审对应实际owner，不能只看软件bench。RoPE必须提供已核FP32 cos/sin表，生成策略尚未批准。

测试：9项unit正常/-O全部PASS，仅实现的有限原语、顺序、形状及fail-closed。256 MAC真实embedding/wq切片数学smoke已执行并留hash；它不是norm后Q投影，更不是模型阶段或硬件数值验证。未执行完整M128，五块0/5不变。

性能：纯Fraction实现为有界可信基线，完整约6e9 MAC不可直接按当前速度放跑；默认100000操作预算、Dense预先拒绝超预算。之后可在精确基线上资格验证加速实现，但不能用BLAS改变K顺序。
