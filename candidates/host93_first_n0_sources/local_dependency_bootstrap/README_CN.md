# 固定五包本地 dependency bootstrap：未绑定 SOURCE v2

这是对现有八份固定源码的有限组合，不是可实际启动的本地任务。生产仓库未修改；没有下载、读取真实包 body、安装、执行工具、构建 Verilator 或运行 Host。

当前状态：独立 SOURCE 审已闭合，仅授固定组合的 SOURCE 资格：`SOURCE_GO_LOCAL_DEPENDENCY_BOOTSTRAP_FIXED_COMPOSITION_ONLY`。v1 的 F01（固定文件加号）与 F02（receipt 验后另读）正式 HOLD 原件保留；v2 只修这两项，没有实际执行许可。

最终独审 MANIFEST 1887 B / `1be3fceced5a6743c146f6d91f89d49b5a332d9088d6984f11eab60624f3ba01`；SUMMARY 3700 B / `97056a036e0f4d33f782d79b39a5f4bcb2bb508eee81e695966a11c014562652`。独立原反例普通/-O 闭合，搬迁冷测普通/-O 各25组通过；入口6×2保留作者记录，独审未重跑该入口组。

COLD_RESULT.json 原字节保留作者冻结时的 PENDING_FINAL_INDEPENDENT_REVIEW 标签及112组记录；上段是其后的最终独审身份，不改写历史测试结果。绑定模板的 work_root、system_programs、native_profile 三项仍为 null；schema 为固定字符串。审身份仅用于来源说明，不是执行时依赖。

## 接口与边界

- source_entry.py --repo /absolute/verified/repo：只在 same-buffer size/SHA 校验后加载 bootstrap.py，返回 SOURCE 检查。无 --execute、executor 或 native API。
- source_check(repo)：核八份原源码及固定五包/67 members 契约，无输出目录创建。
- binding(raw, pin, repo)：只接受精确绑定 buffer。发布模板的 work_root、system_programs、native_profile 都是 null；未绑定即拒绝，不把历史 actual receipt 当作新许可。
- acquisition_argv(sources, binding, started, work_stop)：仅构造 argv；嵌入原 acquire_dependencies.py、published_acquire.py 与固定 PLAN，同样使用原 absolute_deadline / namespace / acquire。没有调用 subprocess、socket 或 urllib。
- verify_acquisition(...)：要求本次 local_dependencies_acquire 的原 exit0/cleanup、原 postflight 的单锚 same-buffer 投影精确 inventory、固定五包原始 bytes/SHA，receipt 保持非 terminal、未执行/安装。
- stage_data(...)：预期在调用方原 60 s/40 s CPU/512 MiB AS 的受监督 Python 阶段中调用。复用原 validate_package、relocate_cfg、FreshWriter；先验证所有五包，再输出67份0600原data、1份四行relocation cfg、1份非terminal report。没有安装或工具调用。
- prepare_tools(...)：先核69份 stage 输入、绑定、源码与 cfg；native_profile=null 在任何 executable copy 前拒绝。静态 profile 通过才复制68份数据，只有五个工具副本0700；返回真实私有 invocation keys。仍不调用工具，不声明 native qualification。

调用方必须在任何真实 argv 启动前另审绑定、用 system_identities 核当前系统 Python/其他程序，并提供既有 WNOWAIT/four-observer、单CPU、共享绝对deadline、各阶段限制、退出和cleanup证据。这里只导出接口和固定限制，不能把返回的 argv、stage report、mode0700 或函数调用当作执行授权。没有新增调度器、进程启动器或完整 Host 协调器。

## 原件复用

SOURCE_PINS.json 固定八份 repo-relative 原件。bootstrap 内仍有同一份精确 pin 表；源码读取用描述符逐级 NOFOLLOW、精确size/SHA和同buffer compile。

- 原官方五包 acquisition 逻辑原样复用。postflight 从同一已 pin 原件中只投影单函数，仅将 receipt=json.loads(receipt_path.read_bytes()) 替换为 receipt=json.loads(VERIFIED_RECEIPT_RAW)；单锚计数、逆替换和两份函数 identity 记录于 PROJECTION。私有 namespace 绑定已验 bytes，全部原 inventory/scope/五行/来源/size/SHA/total 谓词保持原样；结束再核 receipt 的原 pin。没有新 receipt parser。
- private work/repo root 保留原严格 make-safe 词法。仅固定目录表或现场已绑定系统身份的文件 leaf 通过显式 fixed_leaf 参数支持 +；parent 仍严格，leaf 必须精确匹配，size/SHA/NOFOLLOW 不放宽。
- 原67-member archive/member parser 原样复用，没有新写 deb/tar/xz parser。
- 原 autom4te.cfg 第118/145/159/171行 relocation 原样复用，只对新模块实例绑定 OUTPUT_ROOT / CFG_NEW / 路径依赖derived identity；原cfg hash、四行计数、逆替换证明保留。
- 原filesystem copy/inventory函数复用。
- 原micro runner 的 elf_dependencies 单函数按原字节 AST 投影，没有新ELF parser。它做 ELF64/x86-64、固定interpreter、DT_NEEDED、无RPATH/RUNPATH和有限闭包检查；不证明symbol-version ABI或完整compiler/Perl helper闭包。

## 必须未来现场绑定

- 私有绝对work_root，以及其 packages/stage/tools/home/tmp 子路径；目录0700、数据0600、原源独立副本。
- /usr/bin/{gcc,g++,make,ar,perl,python3} 和 /bin/sh 的实际resolution、bytes/SHA/mode。bootstrap使用的Python与historical N0 reference Python是不同角色。
- 固定 m4/flex/bison 的实际ELF metadata；autoconf/autom4te 的确切shebang与系统解释器。
- 本机loader和每个已审soname的invoked/resolved path、root-owned非可写状态、bytes/SHA/mode、DT_NEEDED/interpreter。没有自动拓展包源、lib搜索、LD_LIBRARY_PATH修复或安装。
- 原工具版本/五个有限生成probe仍待未来独立执行与验收；这里没有把静态metadata包装成原生兼容性PASS。

原473树、seqnum唯一补丁、make -j1、8 GiB Host准入、3 GiB磁盘门、4/6 GiB AS与6600 s原共享预算均未修改。新增bootstrap必须消耗原预算，不能重置或加时。

## 冷测

- 主SOURCE/mock：原目录普通与-O各25组，通过
- 主SOURCE/mock：搬迁目录普通与-O各25组，通过
- same-buffer入口：普通与-O各6项，通过
- 112组执行总数；保留原20组并新增5组，含八个固定加号路径、g++、libstdc++静态mock、原postflight正控、同长A→B拒绝与ABA同buffer、投影逆验和原receipt谓词负例
- stage/copy合成 fixture 使用固定五包文件名与两份 c++ skeleton member 路径，原 archive parser 没有替换为新的实现；其完整固定包解析能力仍仅继承已发布原件测试，本次没有真实包输入
- 全部由audit hook禁止网络/native子进程；只有合成微小package/ELF/data fixture
- 包括未绑定、size/hash、重复JSON、路径、source flag、exit/cleanup、stage scope、四行cfg、真实invocation keys、ELF/RPATH/soname负例

这些是有限source组合测试，不能证明本地真实包、原生兼容性、backend或Host运行。完整stdout/stderr与搬迁测试副本保留本地；Git只需源码、模板、pins、此README、PROJECTION和COLD汇总，不需要提交测试日志。
