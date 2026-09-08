# 4096-MAC real16 双层生产流水开发

冻结起点：4499fbe16a14626be25f0bd9b13967b0682b6095。已提交的 weight-burst 数值源 cc2f9424daf2e35ca7dd5940305de7e09bbf623b：42 条 Host 命令、430 个 descriptor、38 个 owner、1,409,024 个 FP32 输出无差异、82,001,446 个周期。只认可报告与原始输出，不把规格峰值当成测量。

本轮范围：继续同一 Host/Matrix/iDMA 链，Chisel 为硬件源，不修改保留或生成 RTL。保持两层不同确定性权重、真实 hidden1536/FFN8960、16 tokens、实际 DDR producer→consumer，禁止 BlockLaunch、Host 中间复制及参考输出注入。暂不扩大 token 数或模型。

1. 将已验证的有限权重 burst 扩展为有界、带 tag/last 的流式读取；同一套 pinned iDMA 服务 metadata、读、写；失败必须排空且不发布数据。
2. Matrix 服务允许五个独立输出 context 的在途流水，保留每个输出递增 K 的 BF16×BF16/FP32 累加顺序。所有实际算术仍来自八个原 512-MAC 分片，禁止多实例旁路和改变归约顺序。
3. 将占主要 SFU 周期的 SiLU(gate)×up 从单 lane 顺序 exp/div 扩为向量并行实现，沿用同一冻结数值配方、舍入和异常合同。
4. 组件数值/回压/错误/复位通过后，在同一 real16 双层原 Host 命令图验证所有实际输出，并与冻结 512 和 4096-burst 两套实际输出比较。

验收：完整仿真与校验退出码 0；42 次 completion；1,409,024 个值全比较；单 logical Matrix/4096 physical MAC/单 iDMA；按 useful MAC/(4096×完整请求周期)报告 wall 利用率，并分别报告 executed、padding、分段周期、DDR字节。毫秒和 GMAC/s 只按 800MHz 目标换算，DC 签核仍独立。

本文件是开发范围，非完成证明。本地执行 agent 仅复核固定版本并执行固定入口，不承担代码修改。所有旧工件保留，新测试使用新目录。
