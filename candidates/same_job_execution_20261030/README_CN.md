# 唯一同 job 五块 M128 短窗口标定：源码提案，尚未启动

仅摘要上传。真正执行链：首次步骤时钟/唯一launch身份→实际CPU/Python/image/磁盘/内存前置→原共同4096/32 backend一次构建→原锁53 archives→70完整tensor单份→原三安装/new fresh owner→五个原M128参考→原provider→同一ELF五M128诊断。构建先行避免旧512MiB watched-file门拒绝1GiB专家权重。失败沿本身份停止，不重新安装/重建/重触旧workflow。

首次工作流步骤开始累计350分钟；实际预算19500秒，剩1500覆盖checkout600/外部余量900。构建7200、archives600、weights3600、三安装各180、owner120、五参考各180（CPU1200上限不扩）、七provider各180、元数据11×120、cleanup1530、parent600、五DUT各300秒。只是有限停止界，**不保证执行完成**；完整M128/max_cycles/4096资源不缩。driver每2^20 active cycles才打印running，300秒可能尚无可用速率。

前置必须观测：x86_64/Python3.12/AVX512；原ImageVersion20261026.354.1及原JDK身份gate；MemAvailable≥13GiB；初始free≥20,671,240,864B。标准runner标称14GB不保证磁盘门通过，资源不足明确NO GO，禁止静默降cap/删旧材料/换硬件。原阶段锁内门继续执行，aggregate12,081,306,272B与free8GiB不变。此方案不包含瘦身删除。

controller、runtime、numeric生产接线分别来自已审R2/freshR2/R7，四件原P0 producer不改；包内数字路径元数据转换为repo-relative，测试采用显式repo参数。SOURCE_PINS包含原acdb495件纯文本及本包生产源码；不包含JAR/权重/NPZ/ELF/SV大产物。历史本地receipt不充当新CI identity。原已发布supervisor未改、被拒disk-worker脚本不包含。原采样盲区仍INCOMPLETE。

同一源码发射IR/SV仿真backend属于Chisel测试后端，不是原生解释器；标定结果始终INCOMPLETE，不是完整数值PASS，也不是模型通过冻结后的最终RTL回放。MoE仍原TorchTopK，小ID同分契约待定。无新硬件/算术改变。

本提案无ci_launch启动文件；必须独立源码/绑定/预算/工具审查后另行授权唯一激活。当前无安装、参考、DUT或CI执行。脚本`prepare_and_run.py --repo ... --identity ... --job-start ... --work ...`只在新实际job中生成binding。没有预制可冒充真实job的binding或API下载证据。

轻测入口：`python -B test_entry.py`、`python -B test_samejob_launch.py`；controller全链mock需`python -B controller/test_flow_mock.py --repo REVIEWED_REPO`。所有mock仅验证控制流和拒绝条件，不是实际资源或数值证据。
