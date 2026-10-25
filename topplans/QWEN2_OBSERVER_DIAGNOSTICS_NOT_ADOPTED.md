# 观察器诊断负结果，不采纳到 DUT

buffer减少write次数但单样本无可靠CPU收益，骤退负例丢1214B accepted证据；selective LINE减少callback/frame却在作者和独立两轮fixture计时更慢。两片保持default-off，不接DUT，不改原预算，也不把失败longrun重新标PASS。

精确source/hash、脱敏诊断统计、历史失败归因和外部输入配置复现边界见 [候选README](../candidates/qwen2_observer_negative_diagnostics/README_ZH.md)。原测试身份与交叠executions分别计账；public path-only adapter未运行，不伪称原测量执行过该后像。

本批不上传trace/二进制/privatepath/运行地址，不重跑target或native。生产fullblock分母、固定4096MAC与legacyPV63.57%上界不变，没有80/90%、cycle或RTL资格。
