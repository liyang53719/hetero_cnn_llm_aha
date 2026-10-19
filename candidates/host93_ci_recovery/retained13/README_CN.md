# CI retained13：新身份 source-only 候选

来源底座是发布提交 `18e757084e4812fe2496ba8321438a468e17b646`。这是环境回退后重新实现的新候选，不继承任何旧候选的审查、GO 或执行结果。当前仅做默认静态与 tiny cold 验证；未执行真实 production replay、13源组装、native、编译、仿真或下载。

## CI 入口

`python -I -S -B <candidate-dir>/run_retained13.py --repo <source-checkout> --out <existing-parent>/<fresh-output>`

repo/out 可重定位；runner、launcher和SOURCE_PLAN需保持同一目录。缺省不传 `--out` 时只读核验96个固定输入，不执行项目helper或生产patch。`--cold-test` 只运行两行源码的patch/hash例子，不能和 `--out` 同用。本投影只保可重定位入口；真实组装项尚未运行。

入口先检查 -I/-S/-B，使用 `pthread_sigmask(SIG_BLOCK, set())` 只读查询并拒绝blocked SIGALRM，使用getitimer只读拒绝占用ITIMER_REAL。绝不自动解除阻塞或取消继承timer。随后按固定size/SHA256读取并编译同一runner buffer，设置umask077。runner再次前拒异常signal状态，再安装60秒总wall定时器，计时包含launcher阶段。

CPU40秒、单核affinity、AS512MiB、FSIZE4MiB、NOFILE64、CORE0；输入单文件2MiB、输入总8MiB、最终树8MiB、报告512KiB。没有子进程、通用监督器或网络客户端。

## 来源与输出

- 96项相关固定输入，共1,254,160 bytes。SOURCE_PLAN固定每项size/SHA256，发布的原source plan和helper还有独立常量pin。
- production seed为70 Scala+6SV，完整四stage后像库存依次76/76/76/77。在内存用固定helper的patch_sources/verify_map回放；不执行原helper的assemble、preflight、rebase或任何Scala。
- 从完整production结果只选6SV。front_control经固定baseline、BEGIN、RESERVED两次精确forward/reverse投影，到最终SHA256 `588fb2e649265f04373fce72c3e697444c0e39565c3dbae879382f05c0fe83c4`。
- 另6个主树retained SV和iDMA wrapper原样选入，全部13项匹配已发布lint source_order pins；输出顺序按retained12+wrapper。
- 不包括upstream iDMA、tc_clk、HardFloat、Scala或Host生成SV。
- 新输出必须不存在、父目录存在，并与repo及候选目录互不包含。全部stage/postimage和输入复核通过后才创建输出。输出为 `<out>/source/rtl/...` 的13SV和 `<out>/SOURCE_RECEIPT.json`，目录0700、文件0600，并核完整库存、mode、字节与报告读回。
- receipt记录13条来源链、输出完整size/SHA256、输入前后pins和未进行native/仿真等边界。失败不删除部分输出；不能复用失败目录，也不能把部分目录当成功。

## 已有验证及待审边界

VALIDATION_SOURCE_ONLY.json记录7个本次实测：默认静态，tiny cold普通/-O，以及blocked SIGALRM/occupied ITIMER_REAL各普通/-O。signal反例通过audit hook证明拒绝发生在任何生产runner读取/compile/exec之前，并保持原mask/timer状态。tiny cold每次3正例、5拒绝例。所有结果exit0。

真实13源组装尚未执行；其production后像、真实输出mode和receipt必须在新SOURCE审通过后由指定父执行验证。MANIFEST.json是此新候选的完整固定文件清单，不构成执行批准。
