# TEMP / INCOMPLETE：R8 原 provider 闭包恢复及受控错误摘要

## done：已验证范围
- R7 run 40831060687：源码155/helpers/high/canonical/变换/Host发射与6555ede3目录身份实际通过。前三个native前端返回0，其中Down168.172秒；第四HostBlockTop native1/77.752秒，supervisor错误0、EOF/清理完整，完整日志census两条error。现有摘要8MiB前缀没有错误原文，R7精确子进程错误仍UNKNOWN，不能将缺wrapper直接冒充已读取错误。
- 静态确认原CI provider列表294 iDMA+13 matrix/clock漏了Host要求的原idma_backend_rw_axi_flat_wrap。恢复同一已提交rtl/integration/idma_backend_rw_axi_flat_wrap.sv（4625B，SHA a82bc50fac9b29df3f5f68527361f9dfac4792dfea3178b84eb488428d8d12c0），不新增/重写硬件wrapper。308源闭包与三个外部root的exact源码hash及独立ANSI ABI前置轻量gate；非预处理/elaboration或数值通过。
- 新诊断仅在非零native退出后读取既有gzip，完整压缩/raw SHA、字节、行和error计数全部一致才发布首4末4条%Error行；不含源码续行。路径脱敏、敏感字段拒绝、单条320B/总4KiB，损坏/越界只INCOMPLETE。完整扫描限90秒/1GiB raw/150MiB gzip/1MiB行；原运行reader、native选项、wall/RSS/CPU/disk/log限制不改。JSON仍64KiB。

## ongoing / todo
- R8 source仅提交工具与原provider选择恢复，唯一launch需另审；不得自动重跑旧job。R7错误原文仍未恢复，后续新run有自己的身份和证据。
- 保持完整4096 Matrix MAC与32共享Vector候选、相同硬件定义/容量/精度/舍入及6555ede3身份基线。新增provider是补回原外部实现，不以软件替代硬件。
- Python独立参考5/5；五块128-token完整Chisel数值0/5，最终RTL数值0/5。无完整block RTL利用率实测，不宣称90%。MoE同分参考契约仍待用户明确。1024/1224不阻塞128。

- 发布审查曾捕获旧R2拷贝导致JDK alias回退；该未发布候选已撤回。最终materializer严格从当前efd271a重基，只含provider导入/追加/gate/receipt，已批准adoptium公共依赖路径保持不变。
