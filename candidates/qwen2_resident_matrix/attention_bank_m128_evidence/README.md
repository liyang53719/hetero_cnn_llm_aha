# 真实 M128 银行存储 Attention 数值通过

## 中文状态
- 已完成：一次真实M128作业的原始owner Fraction参考，再一次同形状候选作业；196,608个output word与99,072个score全部逐位一致。
- 已完成：M32同源前置检查，执行前后85文件SHA身份一致；全部Matrix/scalar/raw-bank请求、返回与ACK守恒。
- 已完成：独立核验原始receipt、85项源身份、真实M32前置与计数；2+2原始文件证据测试通过，零跳过。
- 待办：Q/K/V输入与最终输出物理放置；寄存器租约/mux、真实控制器与RTL端口时序；完整block性能和数值验收。

执行源 pins c7aaf3c5d0dbc2923846059e0661bba0434c20ee2f4351f7044a19b170e6b24c 保持不变。该源README记录准备时状态，此独立文件记录后续真实执行。M32前置receipt f6d229f74ad780eb2a0e260ab58a1b1e07aa9989cbec6dac428f4ad9032b35a3；M128receipt 086fd8c81788c08edacdba4c5ec7d0a6338e0fc4ee78a609ffe25d796daa6da3。

## 实测软件执行
参考521.405108s，候选311.048688s；receipt总wall832.675519s，CLI832.898593s；CPU832.569864s，峰值RSS73,120KiB。内部1200s、外部1210s，一次执行正常退出0，没有重试/native替代/并行数学进程。

Matrix71,808步骤、7,168分组及结果ACK；selected FMA25,362,432。scalar183,808包与ACK，scheduled FP32节点3,667,200。scratch488,448读、205,056写，共693,504个64B事务及ACK；物理bank读976,896/写410,112，计数边沿2,080,514。原始owner参考请求1,585,152。

输出SHA b5b861f42b38f3055cb91d82c97a93b603f2a6c8d643be47b7241079c1a974e5；score SHA b336f705690ee94acfd6b97ae65fdaace117431ff2aa839fb3be500c60664f9a。

## 范围
这是现有固定资源对应的Python银行存储Attention候选与原始owner算术的数值证据。score/prob经同一实际Banks；QK按16-key分块、结果保持到score clean ACK，softmax/PV顺序保留。host Q/K/V fixture仍未证明硬件供数，真实接线仍待实现。

3,426,818 hypothetical_ticks是显式假设时序下的模型计数，不是测量硬件周期；不能由Pythonwall、MAC请求下降或容量匹配推导80/90%利用率。完整block有效MAC分母仍为6,014,828,544，scalar/SiLU/端口成本必须保留。

安全证据仅散列、计数、运行身份和耗时，无输出tensor或权重。验证原始文件：

    BANK_TILED_RECEIPTS=/path/to/receipts python3 -S -B -m unittest candidates.qwen2_resident_matrix.attention_bank_m128_evidence.test_evidence -q
