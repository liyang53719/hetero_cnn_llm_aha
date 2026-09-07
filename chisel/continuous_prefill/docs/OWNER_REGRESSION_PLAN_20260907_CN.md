# Host owner 连续执行：跨 tile / 重定位 / 生命周期 / 多层

基线：ad4ad0a655f8d18e94e06b6dba1370baebe40c3e。此文件是本轮开发计划，不是验收完成声明。

开发次序：
1. 在不改动 DUT 的情况下，对原 HostBlockTop 运行 17/32/33 token、重定位及独立 GEMM 顺序调换的连续数值回归；先 tiny，再真实 H=1536/F=8960。
2. 同一个 DUT 不复位提交第二个冷请求，更换输入/epoch，检查累计 DMA 计数的请求间差分、旧 event/输出发布状态不泄漏。
3. 向命令读取、descriptor读取、payload读取、首/末写回注入故障；验证非零唯一 completion、消费者禁止启动、reset-required，以及同一 DUT 复位后合法请求数值恢复。
4. 上述公共基础通过后，连接不同权重的两层原命令图。层间必须把前层实际 DDR 输出地址作为后层输入，不由 Host/参考模型复制或重建中间结果。42 条原命令共用一套 Matrix 与一套 pinned iDMA；不使用 BlockLaunch。

硬件问题只在 Chisel 修复后重新生成。保留 RTL 不修改。测试、fixture打包和证据工具允许相应修改；绝不修改数值阈值以绕过失败。

验收必须包含被测源码身份、生成DUT身份、实际命令/descriptor、全部输出与完整比较日志、退出码、metadata/payload/write-ACK计数及阶段发布检查。软件/硬件测试和已运行/未运行范围分别记录。测试输出使用新目录，不清理任何旧工件。

执行agent只运行固定命令并返回结果，不要求它修改代码。官方checkpoint、多层整网q1024和800MHz DC不由这些回归自动升级为通过。
