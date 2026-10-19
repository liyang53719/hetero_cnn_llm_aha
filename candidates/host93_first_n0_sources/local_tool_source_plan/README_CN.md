# 本地固定 Verilator 续接：有限 SOURCE 计划

状态为 TEMP_SOURCE 计划；尚未实现或执行本地工具绑定入口。本次保存固定来源、必要差分和已有 mock 记录，不授予下载、安装、构建、Host 或数值执行资格。

## 固定来源与最小变更

- 可复用 `candidates/host93_ci_recovery/toolchain/ci_toolchain.py::run` 的既有源语义。保持官方 revision `4e194cc3ec8e27b18e17f80d7f99c15f984bbdae`、473 文件/11,747,893 B、唯一 seqnum 初始化 +13 B、全新独立 inode 源树、make -j1 opt、固定 FlexLexer.h 和 tiny 链。
- 五个固定 Debian 包共 2,466,616 B，选择 67 个原始 data 文件共 3,598,623 B；版本为 autoconf/autom4te 2.72、m4 1.4.19、flex 2.6.4、bison 3.8.2。libfl-dev 仅选 FlexLexer.h。包 URL、size、SHA 沿原表不变。
- 未来本地绑定须给私有 roots、新 receipt、四行 autom4te.cfg relocation 及真实 invocation 路径。原 staging 的 actual review/config pin 尚未绑定；不可复用旧收据或把不存在的系统路径记作实际工具。
- 固定五包并未提供全部本地 ELF/Perl/编译器传递依赖资格。系统解释器、库、脚本数据路径及 same-job backend/runtime 身份仍待有限绑定与真实前验。
- 为最小行为差分，计划保留原 header 获取/编译 lane；这会再有一次固定 85,600 B 包获取。去重需另审确切 source/receipt 差分。
- 原 8 GiB 内存准入、3 GiB 磁盘准入、单核、Host AS 6 GiB、阶段上限及共享 6600 秒不变；任何 bootstrap 均消耗该共享预算。资源快照只属已公开的时间点观察，实际准入必须重新核实。迁移或删除 runtime/wheels 尚未进行。

## 已有测试记录的准确边界

作者保存的五套既有 SOURCE/mock 结果为 toolchain 118、header 26、transport 7、五包获取 21、五包 staging 33，共 205 项。独立审查核了来源 pin 与保存输出；没有独立重跑这些 205 项。初次临时夹具位置被拒后，作者仅调整隔离夹具位置重跑，原测试源未变。

本次不发布本地记录 harness、机器库存、原 stdout/stderr 或临时夹具。该 harness 存在本机 sibling 路径和 runpy 再读，不能称为已审可搬迁的 same-buffer 冷入口。205 项是已有源语义与合成失败路径的记录，不证明新 adapter、真实 ABI、工具构建、Host 或 full-block N0。

## 文件及有限审身份

- PLAN.json、SOURCE_PINS.json 原字节保留；路径仅为仓库相对来源、固定系统路径或占位符。LOCAL_BINDINGS_REQUIRED.json 是不含现场路径的有限摘要，完整本地记录不发布。
- COLD_RESULT.json 是精简的记录摘要，明确作者记录、独审未重跑和未授执行资格。
- SOURCE 有限审：`ACCEPT_LOCAL_FIXED_VERILATOR_SOURCE_PLAN_AND_RECORDED_COLD_ONLY`。MANIFEST 168 B / `4069ef8f2229492de1763becf3f3e92f96188437cf32dec5cb4aac3caec18e46`；SUMMARY 2363 B / `75a9d15cf4177849cdaf81ebd84831f388a55df8b30c9feda0641467531034a0`。审身份仅为来源说明，不是运行时依赖。

本批不修改 workflow，不启动新的 Host/native 作业。历史 original-reference 精确成功仅属于参考资格，不能替代工具、资源或 DUT 门。
