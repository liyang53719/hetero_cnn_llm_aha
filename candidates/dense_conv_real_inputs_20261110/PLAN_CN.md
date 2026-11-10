# Profile1真实权重绑定原完整Host程序：TEMP

## done
- 复用已恢复原emit_cold128_programs.common(1)，不改DUT、不新建缩Dense wrapper。17操作为input_norm→qkv/z/ab→conv→rawprep→chunk→gated_norm→o→residual1→post_norm→gate/up→silu→down→residual2→fence。
- 全部14个L0训练参数实体重新核尺寸/SHA。6个独立矩阵及AB组合为原Dense要求的[K,N]，不是直接将checkpoint[N,K]误装入内存。AB先16个A输出再16个B输出。Conv按原6144×4布局，norm与A_log保留既定BF16/F32。
- 16个readonly分配实际物化，共44,470,880字节。输入hidden由外部文件传入，本次smoke明确为合成BF16 M128×1024；cold history/state为零。没有input_norm/QKV/Z/AB/Conv/prepared/chunk等中间预载入。
- 原HostBlockCommandsV4的rdLive需要真实input norm ACK；rcLive需要真实QKV/Z/AB ACK；prepLive需要Conv/AB确切sameAllocation。故这些真实生产者约束仍在原Host内，不由脚本虚构receipt。
- 4项单测normal及-O通过：矩阵可逆转置、AB排序、producer边连及readonly排除、错误shape拒绝。真实payload绑定exit0，仅字节/metadata资格。

## ongoing/todo
- 同一HostV4共享4096定义运行profileId1，需要真实bench接本目录commands/descriptors及BINDING的64位稀疏地址；不能使用Qwen2旧稠密vector直接分配0x1000000000地址空间。
- 尚未实际编译或执行此profile的Host bench，也未与独立完整参考数值对比。不能把source-derived metadata当Host解码/数值PASS。
- 完整五块128仍0/5，未测完整block利用率；没有更改原n16 fatal underflow、MoE契约或新vector设计。
- 数据留本地profile1_real_host_payload；源码包只脚本/pin/摘要。未push、未启动长RTL、未清理。
