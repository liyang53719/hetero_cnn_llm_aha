# 独立 GitHub owner 协议路线（仅方案，未发布/触发）

旧 tmpfs fixture 保持原样。完整 workspace 副本已验证，但缺可靠跨 namespace 引用证明，最新门控已停止迁移。不得以本方案提高当前机器的编译 RAM 门。

## 默认：小源码闭包重新生成

发布范围是六个生产Scala修改的独立候选路径、同一已审159选择逻辑的独立 `selected159.py`、owner 发射入口、原8-case driver、端口生成器、有限CI runner/workflow与小清单。旧model_candidate_build共享gate/pack/restore/producer均保持原字节；完整integration.patch延后至专门集成提交。已有 153 个生产源及正确的 banks 源从固定 source commit 读取；不改变既有生产入口，不复制完整仓库，不把 IR/SV/C++/class/ELF 或压缩编码后的中间产物提交 git。预计新增源码与清单小于 1 MiB，实施完成后须按实际发布清单重新核定。

所有 159 源恰一次进入新的 Scala compile，官方 106 个唯一 jar 字节（106 个 classpath 条目，plugin 是其中一个重复角色）保持原 pin。完整新 class 输出仅用于原 `EmitRealDownOwnerChirrtl`，不发射 HostBlockTopV4，不启动 4096 数值 DUT。构建、CHIRRTL、firtool、Verilator、C++、协议运行严格串行，上一进程组退出、EOF 和 cleanup 闭合后才进入下一阶段。

为保留 raw IR/SV 源位置身份，独立 VM 只把白名单源放到原绝对路径布局，不改任何源文本。所需 `/workspace/scratch/f28987e955ed/...` 是新 VM 内新目录，绝不是原机器挂载。若不能建立该布局则停，不能静默删除 sourceinfo 或修改硬件来凑 hash。IR/SV 要与已审 raw SHA 完全相同。Verilator 57 个文件中 56 个要求 raw hash 相同；唯一 `__verFiles.dat` 含 inode/ctime/mtime，保留新 raw hash，并核固定 argv/文件集合，禁止 skip-identical。49 个 cpp、4 个 h、2 个 mk、1 个 d 的内容不能豁免。

官方工具：Scala 2.13.16 / Chisel 6.7.0 / plugin 固定 Maven 字节；firtool 1.62.1 固定 Maven 包与成员字节；Verilator 5.032 固定 Debian 包及官方 manifest。Ubuntu runner 的 JDK21、GCC14.2 是独立宿主工具链，不能冒充本地 Debian 二进制相同：启动记录 image/version、真实可执行文件/loader/shared-library/header hash，前后复核，-MD 完整依赖闭合。若版本或依赖不符先停，不临时 apt 升级或下载不审的新工具。

C++ 沿同 O1/O0 语义，GGC 10/4096、no-fast-math、fp-contract=off；52 TU 串行，PCH 禁用，系统头仅 -MD，不带 -MMD。不借本地失败留下的五个 .o，不调用 Verilator 重新生成来绕过既定输出。最终发布前一次预授权精确 compile_and_protocol8 模式；同一个有界 job 在所有前序检查闭合后运行现有8case，不暂停丢弃VM或再构建。全过程不下载模型权重、原始输入、reference、KV/cache 或原 FULL 材料。

预计远端时间：前端准备/compile/emission/lower/translate 约 12–25 分钟，C++ 首次有限编译约 5–20 分钟（未完成实测，不能保证），协议约 1–3 分钟（未执行）；总预算详见 PLAN.json。已知本地测量：10 批 compile 约 18 分钟（小 heap、重复 JVM），CHIRRTL 13.43s，firtool 240.07s 含校验，translation 236.11s。新远端单次较大 heap compile 的时长只是估计，失败后按原身份诊断。

## 次选：上传已有中间源码至受控 artifact

可避免再生前端约 12–25 分钟；已有 SV 34,294,411B、C++ 57文件 30,293,531B、driver/accessors 约 0.52MiB。只可用可验证的 artifact 上传渠道及 download-id/hash 契约，不能塞入 main 或 base64 变相发布。目前可用 GitHub connector 只发现 artifact 下载，没有可用上传动作；不把未实现的 artifact 路线当已可执行。若另有正式受控上传端点，须另核权限、固定输入包及下载身份后选择，且不得与默认路线并发或重复 dispatch。

## 结果边界

这是实际 owner/full banks/credit 的协议验证；外部 Matrix responder 只做握手、标签、数据搬运与确定性 payload，非 MAC 数值替代。无 DMA/TileSumBridge/Matrix4096。N192/N320、M128/K128 仅控制激励；读写接受重叠属于独立 owner 供数压力环境，不是目标单 outstanding iDMA 完整链带宽，也不是五块80/90%利用率或完整128-token prefill PASS。

当前已准备可执行 CI runner/launch validator；尚待独审、精确发布清单及运行授权。独立运行前仍必须 fresh hosted resource gate。没有发布、dispatch、编译或模型运行授权由本文件产生。

官方资料：
- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md

完整Top producer/source-observation合同目前尚未贯通新六源；后续文件与门见 NEXT_FULLTOP_INTEGRATION.zh.md。当前独立owner CI无需、也不会放宽原完整Top证明门。
