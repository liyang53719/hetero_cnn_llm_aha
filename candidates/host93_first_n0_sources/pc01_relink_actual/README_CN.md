# PC01 驱动重编译与链接实际限定资格

本次仅编译新的连续 PC0→ACK0→PC1→ACK1 驱动，并与首 N0 已成功验证的原 Host archive 和三个 runtime 对象链接。没有重建 backend、重新生成 RTL，也没有调用新 PC01 可执行文件。

- 外层自然退出 0，墙钟 5.451080440 秒；编译与链接原 native 墙钟分别 3.459783 和 0.144490 秒，均自然退出 0、未超时且清理确认。
- 新 ELF 为 13,537,744 字节，SHA256 cb64b5cf1d5e9c226b9768fb3fdcbb3305bee894b6d904cb4cf29633d10fe5b1。原 archive 为 17,631,506 字节，SHA256 dafcc125c4a4463b9ff454fda6b7a4031bfa17fd98cde1e8386ff058ce245b2f。
- 独审核对完整 80 项工作树、47 个 source/cache 文件、39 个固定系统文件、49 个别名以及 .d 依赖与 ELF 静态身份；两阶段原日志为空。-MMD 的 .d 不包括系统头，不能当作全部文件打开的系统调用追踪。
- 收据中的 337732 KiB max RSS 是累计子进程记账，不是分别新测得的每阶段峰值。此次只有重链墙钟，没有仿真周期。

正式独审结论 ACCEPT_ACTUAL_PC01_DRIVER_COMPILE_LINK_ONLY；MANIFEST 1256 字节 / 9fc63304848d842ec22d617fc05d5b2bba1413a15c80fd1b2ed797a887d50de1；SUMMARY 5665 字节 / 768474add541e8c033126d02a8f0efbb4bd913fcf6ccaa412bd7f727b9b49195。原证据 MANIFEST 为 882 字节 / 50e3fdc555dc211e71a2638e18fffa006322fb13ad5f3467f598b996551c01d3。

后继可固定此 ELF 与真实重链收据作为单次 fresh PC01 capture/compare 输入，仍需对应源码审查和现场资源准入。两个实际窗口上限为 180 秒与 10620 秒；其间准备等待不计作仿真时间。PC01 实际、数值及完整 block 资格均尚未成立。全部数组、二进制和原始日志私有保留，此批只发布安全汇总与文档，不触发新的 Host/RTL/native 作业；普通 push 的轻量 guard 另记。
