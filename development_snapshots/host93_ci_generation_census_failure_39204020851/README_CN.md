# 部分 PASS / 整体 FAIL：完整有界告警类别普查，尚无 Host 运行资格

- Actions 39204020851，attempt 1，提交 5995323145b17f4059d2bdc5562111a4d1725c92，job 117902825035。三份安全 JSON 原字节保存。
- 本轮保留 warning-fatal，模式仅到生成诊断，禁止 C++ 编译/运行。31 个阶段 native exit 0 后，host93_cpp_generate 自然 exit 2，耗时 166.252153 秒；未超时、清理确认。总记录 830.576913 秒。工具构建、固定微例、FIR/SV 固定身份门再次通过；cpp_generated/compiled、reset_launch、n0_numeric、weights_loaded 仍 false。
- 全部 77,661 B 原生成日志在既有上限内扫描；摘要记录其 SHA256 f24df3e59080059c2fffab36a88379e6f9249a16ff9523dd2af0a52ddaef0763。scan_complete=true，提取 35 条 WARNING:UNOPTFLAT、2 条 ERROR:NONE、1 条 fatal 摘要；未解析 header 0、记录省略 0。35 个 warning 坐标中 32 个属于固定 HostBlockCollection.sv，3 个属于固定 iDMA write:103、read:87、write:92。
- 一条 fatal 摘要给出 35 warning，与全 stage header 数量相等；process_attribution=NOT_AVAILABLE，不能据此保证所有 header 属于同一进程。2 条 ERROR:NONE 仅是已提取的无规则错误头，不把计数直接解释为设计错误。
- Example 路径总计 358 条，只保留 16 条，省略 342 条；example_cap/partial=true。因此类别/坐标普查完整不等于组合环路径证明完整，不能称全部 35 条均误报或真实环。
- 实际生成 wrapper 摘要可用：固定公开模块别名 qwen2_matrix_command_endpoint，22 个 combo 输入、21 个输出、6 个 DPI import、2 个 always_comb（249/375 行）；有限 handshake 方向及绑定已记录。specialization=UNKNOWN，dependency_conclusion=NOT_ESTABLISHED。没有上传 wrapper 原文或赋予其运行资格。
- 私有日志、生成源码、FIR/SV 与二进制未上传；这些身份和统计来自同 job 已审源码及严格安全摘要合同。CPU 为阶段累计计数差值，RSS 为协调器累计 child 峰。
- 实际独审身份：PENDING_AT_SUMMARY_CREATION。前七次失败和原未知边界均保留。

下一步只读比对同 hash SV、固定 iDMA 与 wrapper 有限摘要，按准确路径审查调度过聚合候选；本批未关闭警告、未修改架构或算术。
