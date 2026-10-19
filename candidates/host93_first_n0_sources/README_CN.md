# 首个 M128 N0 前门：TEMP_SOURCE，实际未执行

本批仅持久化两个有限源码组件：原官方 Qwen2RMSNorm 冻结 N0 参考恢复入口，以及当前固定 raw13 获取收据到原 provider14 转换的来源绑定。无 workflow 修改；本次不触发新的 Host/native 作业，普通文档/源码 guard 可运行。未取得新权重/张量，未安装或导入数值运行时，未运行 RTL。

参考保持原 [1,128,1536] 全部 196608 值、原 BF16 与 FP32LE 两个 SHA、原 Torch/NumPy 五 native 文件和官方类源码，四线程/单 interop 与 AVX512 准入不降级。参考只允许一次官方类调用；其通过不授予 RTL 数值资格。参考 SOURCE 审 review_frozen_n0_reference_source_20261019T1036：MANIFEST 1227 B / 6ea5150332941dbacc9ec5304887c2ac2e0ffa3e4706ac5f1202f95f39a0b4fd；SUMMARY 4492 B / 91e8dbf66951f56916fac12b48ea9bf9f9e6c77498b776155620e294e12797ad。收据 SOURCE 审 review_n0_receipt_binding_independent_20261019T1036：MANIFEST 1013 B / 02e7a4e205b8ae11eecef952fd7bb1c37a67bb70eb4174befe7a0fb183d15933；SUMMARY 4598 B / b27b3431547e14ae991a7b03c492fb00032553b05c1483c9541bd3114525e23a。独立参考24+24、收据14+14通过；均仅SOURCE，实际NOT_EXECUTED。

输入片仅修复已证的来源组合前拒：当前 acquirer 的 plan 为 7af00f7b…，旧 converter 仍消费历史 b8635eaf… 收据。当前成功收据的确定性期望为 4335 B / 0b319b9dc84a4c3942f3068b397e01f0e3493515b542ddf726d7d0677e01b6fa；这是 SOURCE 推导，不是实际获取证据。13 raw 和 14 provider 的所有旧负载 hash、顺序与变换函数保持。

后续同 job 方案已获有限预算授权：固定11官方 wheel 共215906086压缩字节，runtime取得/安装300秒；22个固定Range共94382080字节/raw900秒；provider120秒；reference120秒，前门总1440秒。Python设置也扣同一个6600秒总墙，最后120秒留安全落证。安装树1.5GiB和总私有树1.75GiB是观察/验收上限；RSS1.5GiB是采样软限，不宣称OS硬限。参考AS8GiB/CPU90/4intra1interop，Host原单核AS6GiB保持。

实际单 RTL/单 RAM N0桥与协调器尚在 SOURCE 开发，未包含于本批。计划真实B退休→ACK0后读回196608值，精确bit/hash与既存容差分列；8,000,000周期是探索帽，2,428,928只是已核计算下界，其余5,571,072为预算余量而非完成上界；运行wall3600/CPU3540且受共享剩余截止裁剪。超时/周期耗尽均INCOMPLETE，不能计作数值不匹配。输入搬运/写回/控制计数须由真实驱动记录。

新桥将使用当前 seed=1 cluster 的同job真实DPI/链接身份、单model/root及真实字段准入；不会继承旧8endpoint ABI。现有root header语法未知、256 handles未获资格；首N0仅SFU路径，不能推广矩阵算术、AXI全协议、后续block或全模型。权重、张量、二进制、完整日志与机器库存均不进入Git或artifact。
