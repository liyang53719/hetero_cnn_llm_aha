# U00.2：Attention 宽拼接定位与单 lane 选择候选

日期：2026-10-09 UTC。完整 Attention block 数值验收仍为 **OPEN**。

## 已获得的实际证据

[原 codegen run 37990673233](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/37990673233)
在 21:07:32 UTC 完成，实际生成阶段 302.796 秒，预算 1200 秒。没有执行 C++
编译、模型捕获、参考生成或 DUT。原生产源码固定为
`6959810545203d5f9508075b311dba52f1bee0c9`，诊断源码为
`06e78fd07f18362f13010d2baf34cd79ac6ece12`。

原 SV SHA256 仍严格匹配
`4f061c48397979339ff97bef5a5e9f9dee2bd4a0dec7a5637f8a95b5de2e45f9`。
两个曾被实际采样的 C++ 文件也逐字节复现原 SHA。独立校验通过 48 项，核对
619 个生产、17 个诊断 Git 源码身份，以及 ZIP 和全部保留源码的大小、哈希。
工件 `11645237319` 为 1,370,163 字节，SHA256：
`e2f9501e7b763c43d6354077d3213f10dc6218a648e059dd6c329d60cafd42d0`。

486 个生成 C++ 文件中找到 8192 个 `VL_CONCAT_WWI` 调用。两个主要函数各有
4032 次连续调用，把 Matrix 16×256×32-bit 的整个结果 tile 从 2080 bits
逐次拼至 131072 bits，最后才按 GQA row/beat 选择 1024 bits。它们对应冻结的
`Bf16CausalGqaOwner.scala` 第 293–296 行，确切数学关系为：

`incomingFloats(lane) = value(row)(32 * effectiveBeat + lane)`，其中
`effectiveBeat = 0` 当 `state == resultQk`，其余状态为 `beat`。

这两条链在各自函数体内没有局部 valid/state 条件。每次完整函数调用的源码
要求累计复制 8,384,544 个左输入 word，另有 helper 中的清零；该数值是静态
操作量，不是实际内存流量或每周期次数。原 76.1% CPU 采样只落到 helper
符号，不能由静态调用点反推每个调用者的运行时间占比。scheduler 调用文件
没有保留，外层调度频率仍未验证。

原始 71,661,305 字节 SV 超过选取源码上限而未上传；两个 C++ 调用者、root
声明、runtime header 和小调用者原文均保留。7,080,149 字节源文件低于 12 MiB
上限。`calls.json` 的 30,399,313 字节含元数据、缩进和转义；受限原始文本为
12,761,150 字符，低于 16 MiB 字符上限，没有隐藏截断。64 个 cold 调用的
函数名未被原正则识别，实为 `__stl_sequent__TOP__14`，参数均完整。

## 已拒绝的参数方案

同一实际 Verilator 5.032 ELF（SHA256
`619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703`）
执行了有界的同形小 SV codegen，未执行模型或 C++ 仿真：

- 默认 expand-limit 64：2.273 秒，4032 个宽拼接 helper，复现问题结构。
- expand-limit 4096：2.925 秒，预设 2 GiB 地址空间上限内抛出
  `std::bad_alloc`，退出信号 6，没有生成 C++。这是负结果；不据此宣称系统
  OOM，不提高预算，也不把它带入完整 top。
- 明确 32-bit lane 选择表达式：0.367 秒，0 个该 helper。这只说明同形表达式
  的 codegen 可行，尚不能替代实际生产 Scala 的等价或数值测试。

每次子进程另有 90 秒 CPU、100 秒 wall 上限。复现脚本为
`tools/attention_profile/concat_microprobe.py`；原运行源、命令、失败日志和
结果摘要均保留于任务工件。新脚本是复现入口，未把另一次运行冒充原测量。

## 本轮候选与验收顺序

候选仅将 GQA 的整 tile 拼接改为每个 32-bit lane 按 row/beat 选择。FP32/BF16
计算、Matrix/SFU/Scalar/iDMA 实例、寄存器、状态机、握手和发布栅栏均不改。
row 为 4 bits，beat 为 3 bits，全部 16×8 编码都合法；没有额外可表示的越界
编码。候选保持 valid/ready 为低时的组合结果，不以握手 gating 掩盖路径。

1. 原冻结 top emit 必须先通过原 SV SHA 门禁。
2. 独立 CI checkout 只应用经过精确基线 hash 核验的单源码变换，另添加小测试。
   基线 map 与派生候选 map 分开记录。当前生产文件尚未替换。
3. 实际 Chisel 同 DUT 比较原表达式、新 helper 与独立 lane 索引，穷举全部选择、
   四组原始位图、QK/PV、valid/ready、持续反压及 row15/beat7。随后运行原 GQA
   owner 六项测试，保留 faults/reset/末 ACK 与实际临时结果收集。该 owner 门的
   Matrix 端点是软件 FMA，不能标成真实 Matrix 阵列或完整 block 数值通过。
4. 候选完整 top 产生新 SV 身份。逐模块原文字节检查仅允许
   `Bf16CausalGqaOwner` 改变，模块集合、其余模块和模块外字节必须完全相同。
   不规范化或放宽旧 SHA 门禁。然后只做 `hier_verilation` 和调用清单。
5. 小门与新结构验真后，再恢复同完整 top 的确定性前缀、真实活跃数据路径和
   完整 block 数值执行。完整数值结果决定生产接入验收，不能以本轮局部 PASS
   关闭整体门禁。

第 3–4 步当前为 **PENDING**。这个新门整体预算 1800 秒，串行构建；不下载
模型、不执行完整 top、不生成完整 top ELF。没有性能提升、物理 QoR 或完整
模型通过结论。此前 GQA hierarchy 变慢的负结果继续有效，方案不采用。

## 原门禁保持

实际完整 GDN 的 cold→carried 两个 M1 已有独立证据，此结论不扩大为 M128。
Attention 的原超时、完整 native producer 失败和跨环境 activation 差异全部
保留，精度阈值不变。C02.2、完整 Attention block、M128、35B 与物理验收仍未
关闭；U00.2 进行中，U01 待办。

机器摘要：`reports/execution/U00_2_HOST_ATTENTION_SELECTOR_06E78FD_20261009/summary.json`。
