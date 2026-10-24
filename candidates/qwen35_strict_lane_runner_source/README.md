# 严格 FP32 单 lane 测试驱动源码（TEMP）

状态：仅源码与 Python mock 检查通过，不是 ChiselTest/Treadle 实测通过，不是 prefill 验收，也不是 RTL 回放验收。本目录未提交任何模型、依赖 JAR、私有运行目录或绝对路径计划。

## 内容

- `run_lane.py`：编译两份测试 Scala 源码，然后运行指定 ScalaTest suite 的受限驱动候选。真实执行需要单独审核的私有 `PLAN.json`、`REVIEW_PINS.json`、后端证据以及固定 hash 启动器；本公开目录不包含这些材料，因此不是可直接执行的硬件测试包。
- `test_source.py`：可独立运行的纯 Python mock 检查。临时合成计划，真实 `subprocess.Popen` 被禁止；不会执行 Java、Scala 编译器、Treadle、firtool 或网络访问。
- `PURE_TEST_RESULTS.json`：八项有限的负例/mock 结果；只证明列出的分支，不代表真实进程生命周期已被完整验证。
- `SOURCE_MANIFEST.json`：本目录文件的相对文件名、大小和 SHA-256。
- `BACKEND_SOURCE_INDEX.json`：13 个官方源文件的固定 URL、Git blob ID、SHA-256 与大小，不含上游源文件副本。

运行公开源码检查：`python -B test_source.py`。测试会输出一条故意注入 inventory 错误的 FAILED receipt，随后输出 PASS_PURE_PYTHON；前者正是验证失败时仍保留结果的负例，不是硬件测试失败。

## 准入与边界

执行授权与后端审查两个 gate 默认必须保持 false，缺少任一项均在创建实际输出目录和启动进程前拒绝。计划及驱动源码 hash 必须符合审核固定值；修改配置需要重新审核和固定 hash。

两个 JVM 阶段分别最多 180 秒、1 个 CPU、2 GiB heap；heap 不等于总 RSS 上限。驱动检查运行中及退出后的日志/文件容量，SIGTERM/SIGINT 进入有界清理，分别记录 leader 回收与进程组消失。进程组消失不能证明没有主动脱离该进程组的后代；没有声称强制网络隔离。

R1 的主要缺口是准入字段仅说明、不强制，快速退出可能遗漏容量检查，以及 inventory 异常可能阻断最终 receipt。当前源码修正了这些缺口。独立审查另以五个假进程场景检查 phase 控制流；这仍只是 mock，不是操作系统或 JVM 实测。

后端源代码路径现已核查，状态为 SOURCE_ROUTE_VERIFIED_NOT_RUNTIME_VERIFIED。[官方 TreadleSimulator 固定版本](https://github.com/ucb-bar/chiseltest/blob/d764fdf74652426b57c6eae00d71eac19effd224/src/main/scala/chiseltest/simulator/TreadleSimulator.scala) 及另外 12 个文件的索引见 [BACKEND_SOURCE_INDEX.json](BACKEND_SOURCE_INDEX.json)。13 个 Git blob 身份均经独立审查校验。所选路径为 Chisel Elaborate/Convert → 进程内 Scala firrtl2 low lowering → Treadle JVM 解释器；该路径未调用 firtool、SystemVerilog 生成、原生编译器或下载器，但可能写出 low FIRRTL。这不能证明全部传递依赖的运行行为、二进制兼容或数值正确。

真实测试仍需要取得 25 个缺失 JAR、在实际测试电路上重新检查无 extmodule/intmodule/blackbox、固定唯一 Treadle annotation、禁止意外 VCD，并经过独立执行审核。targetDir 必须是新鲜工作目录内的相对路径，因为上游使用 os.RelPath；不能传绝对 targetDir。当前公开驱动未实现实际电路结构检查，因此保持 TEMP，不得仅因依赖补齐而放开执行。源代码路径已核查不等于运行已验证。驱动列出保留的 `.v`/`.sv` 和 `.fir`/`.mlir`，但不能把“未发现保留文件”扩大为“运行期间从未产生临时 RTL”。如常规 Chisel 测试产生 RTL，必须如实标注。

模型 prefill 通过后冻结输入、参考及源码，再生成 RTL 做同刺激回放的验收顺序保持不变。

后端索引 SHA-256：aae15e25bbcf8de113d08b7ff57439e8e835b20405f47029be663c12ba9d60e3。执行授权和后端执行 gate 未被此次源代码审查自动打开。
