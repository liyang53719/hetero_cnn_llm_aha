# 部分 PASS / 整体 FAIL：FIR 与 SV 身份恢复，Host C++ 生成告警退出

- GitHub Actions 39200026785，attempt 1，提交 b0a7a47d97d43215af708db73712b8131ad6ccfd，job 117890878306。三份安全 JSON 保持实际原字节。
- 同 job 的六阶段前置完成：编译期固定 source-info 根后，实际 CHIRRTL 为 42,417,256 B，SHA256 264f8b3a11c02d0d0917001f1d69452ec1c1294c426c9c81e1e577cdc523385a，精确恢复历史身份。293,837 行、682 module、17 extmodule；254,482 个源位置标签，项目 249,537、库 4,945、other 0，标签 UTF-8 共 22,570,940 B。统计来自新同 job 证据，不把上一失败的静态 57,389,476 B 推算当实际测量。
- 通过精确 FIR 门后继续原工具构建及固定双 handle 微例，再生成 SV。SV 为 76,366,612 B，SHA256 2fcc1ba70ad3406b967292624329593aa38e3fe562e9ff3ac675eec100562f61，与原固定身份一致。toolchain_build、toolchain_tiny、fresh_host_sv 为 true。
- 实际阶段共记录 32 项：前 31 项 native exit 0、清理确认；host93_cpp_generate 在 150.280978 秒自然 exit 2，waitid code/status 1/2，未超时，清理确认。协调器总记录 831.028087 秒。cpp_generated、cpp_compiled、reset_launch、n0_numeric、weights_loaded 仍 false。
- AVAILABLE 且截断的去敏日志尾明确包含 UNOPTFLAT 提示以及“Exiting due to 35 warning(s)”，随后层级生成 make Error 2。此证据支持本轮生成因告警被视作致命而退出；尾部不覆盖全部 35 条，不能据此列全告警类别或断言真实组合环/数值错误。后续须审查具体模块与配置，再决定处理方式。
- 所有生成物身份由同 job 固定代码与严格摘要合同提供；本安全包不包含私有 FIR/SV/二进制，未据此声称独立取回并重哈希。CPU 是阶段累计计数差值，RSS 为协调器累计 child 峰。
- 实际独审身份：PENDING_AT_SUMMARY_CREATION。前六次失败及其未知边界保留。

仅保存公开源码身份、固定去敏诊断与安全摘要，无生成物、权重/张量、完整原日志或机器库存。
