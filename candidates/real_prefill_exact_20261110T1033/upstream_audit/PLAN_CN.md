# 上游与项目 prefill 路径复核（源码审计，不是运行PASS）

已重新校验仓库保存的官方Transformers源码SHA，revision为14e738b5d0cc69aa27a95dde272aea41fde44f2f；该pin是已有版本，不称当前上游最新。

modeling_qwen3_5.py:290–408提供chunk_gated_delta_rule、chunk_size64、序列padding和完整chunk扫描。615–629仅在已有状态且seq_len==1时选择recurrent，其余选择chunk。所以上游整体并不被M1限制；不能将项目历史入口限制归因上游。

本轮实际162源闭包中的HostBlockCommandsV4（SHA见RESULT）:961明确cold M128/C128安装边界，1885区分legacy recurrent与runtime Chunk false/M16|128。当前阻塞是完整真实数值链和后端资格，不是需要先把上游M1改成prefill。没有用两个M1或逐token硬件循环冒chunk，也没有据此断言上游需大改。

本轮推进分层：Python独立真实输入参考继续精确资格；原Chisel解释/混合后端逐块审绑定；已生成真实RTL的C++编译仅准备，不提前开展长数值回放。完整硬件仍0/5。
