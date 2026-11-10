# L3真实M128完整值路径候选（TEMP）

复用已按摘要hash核验的RMS/QKV/C2 QKnorm中间值，不重跑前段；所有真实权重和冻结Torch210 trig输入重核SHA。原session62097单次timeout600s、CPU590s、RLIMIT_AS2GiB，exit0，2.436s。完整M128/8queryheads/2KVheads/HD256，至最终残差输出，非循环单token硬件，也不执行Chisel/RTL。

RoPE按原V12六节点，每乘/加后单独BF16物化，最后192维复制。QK逐K256 FMA、BF16，然后1/16缩放并BF16；causal每row key<=row加+0、future加最小finiteBF16，再BF16与全key subtract；exp仍原degree7、逐节点FP32，不调用np.exp；softmax分母按key0..127 FP32累加，Div后BF16。PV逐K128含masked零项，不调用matmul。Sigmoid先BF16，再乘context并BF16。O→BF16残差→原32lane分组RMS→gate/up→SiLU BF16→乘up BF16→down→末残差。

实测最终输出SHA见RESULT，所有中间摘要在PROGRESS，数组只在local不上传。独立Fraction选验2个QK完整K256、2个PV完整K128、2个真实gate/context sigmoid整数参考，0差异。不代表全量精确资格。

限制：仍是CANDIDATE_FULL_L3_M128_VALUE_PATH_EXECUTED。Dense/PV/QK使用已单独交叉检验的FP64中间逐K FMA候选，不是全域证明；NumPy FP32 add/mul/div/sqrt及BF16舍入未全量异常标志资格，flags NOT_QUALIFIED。exp系数math.log后FP32，与既有冻结参考配方一致但不是库函数正确舍入证明。未原Chisel/RTL对照、没有周期与4096利用率测量；完整硬件五块仍0/5。原underflow FAIL不变。没有向硬件预装参考中间值。

## 修正记录
初次mask快捷跳过被审计判INVALID（并非完整契约候选通过）；原源码/摘要保留invalid_mask_shortcut，不沿用其资格。新版实际执行mask Add最小finiteBF16或+0→BF16→全key subtract；逐key校验只有masked delta精确0xff7f0000可以exp0，再全key sum/div。session88162新运行exit0。输出hash与旧值相同不代表旧流程有效。
原Bf16CausalGqaRuntimeOwnerV14:98–113与330–335、510–544明确QK升序K256并终端BF16、scale再BF16、mask Add/BF16、e/sum直接Div；不是Qwen2的16lanefold。GdnRuntimeElementwiseOwnerV15:49–55明确attention sigmoid BF16、SiLU先乘gate再BF16并乘up，不BF16 sigmoid。PartialRopeRuntimeOwnerV12:153–167、255–261明确四乘/两加每步BF16。新增精确样本2个RoPE坐标、2个完整softmax128key行（含首行127masked sentinel），分别逐节点Fraction/integer exp+sum/div，对实际中间数组位值全符。仍非全量flags/硬件资格。
