# 新派生 Host-only 93 源恢复候选

状态：SOURCE 候选。当前文件不构成下载、编译、IR/SV、C++/Host 绑定或完整 block 通过证据。历史95源专用 emitter 与完整身份没有保存，本方案明确建立新身份，不继承历史95的 CLASS、IR、SV、ELF 或库资格。

## 最小分片

1. `acquisition/`：独立的官方固定来源计划与获取/校验候选。87 JAR、20 HardFloat、firtool、Verilator、已有 iDMA artifact 分组审；不取87与106的并集，不安装/执行工具。获取结果保存在项目外，来源计划是复现规格，不是本地工具环境库存。
2. 本目录 `assemble_host93.py`、`SOURCE_REPLAY_PLAN.json`、新 emitter 与冷测：源恢复候选。源组装动作与下载/编译是不同的后续授权阶段。

## 新的93源定义

已发布生产92源 = 72个项目 Scala + 20个固定 HardFloat Scala。对92源应用已发布 SiLU abort 单表达式修复，再应用已发布三个仅增加观察文字的 taps。最后添加 `source/EmitCanonicalHost93.scala`，得到93。没有 Bench/Spec。92中的既有 Emit 对象只是源文件闭包的一部分，不会被本脚本运行。

新 emitter 使用原 `HostBlockCollection`，其 Host 与四个真实 FMA provider 通过一次 CHIRRTL elaboration 共享命名空间。后来执行顶层必须是 `HostBlockTop`，四个 sibling provider 仅用于提供同源定义，不应作为额外执行算术实例计入 Host 子树。禁止另发 FMA IR 再按名称覆盖。

配置逐项来源于已发布 `production_qkv_reduction/qk16_host_structure/source/ProductionQk16HostStructure.scala`：H1536/F8960、12 heads/2 KV heads/headDim128、capacity1024、Matrix256列、16-beat、pipeline/burst、transposed down/resident FFN/public21、official BF16 v2、production packed QK16；commitTailRead/overlapSilu均关闭。M128不是把 elaboration capacity 改为128的理由。

## 默认只检查，不组装

从本候选目录，显式传入只读仓库：

    python -I -S -B test_source_cold.py --repo /absolute/repository
    python -I -S -O -B test_source_cold.py --repo /absolute/repository
    python -I -S -B assemble_host93.py --repo /absolute/repository

新 emitter 从本隔离候选读取，其余已发布输入从显式 repo 读取；源码 hash 逐项固定，不靠所在目录推断仓库。默认 preflight 只读本项目 pin、源、patch、manifest，检验92→修复→tap baseline连接、三tap精确正向与删除反投影、计划93及新 emitter；不加载 rebase helper、不重放完整生产源、不读取外部 HardFloat。冷测仅执行新测试/组装器的纯文本函数和合成小样例，不构建模型、类或RTL。

## 后续源组装入口，当前不执行

仅在源组装获审、20 HardFloat 文件已逐个固定 hash 校验后：

    python -I -S -B assemble_host93.py \
      --repo /absolute/repository --assemble-reviewed-source \
      --hardfloat-scala /absolute/verified-flat-hardfloat20 \
      --output /absolute/fresh-output-outside-repository

输入必须匹配本计划记录的逐字 pin；不根据新 checkout 自动刷新。脚本在内存中用固定行位置、零 fuzz/offset 重放生产与 donor 补丁；每层核对完整 postimage。随后只加载一个已发布、逐字固定的 `production_qk16_rebase/build_source.py` 纯文本 rebase helper。该 helper 及其 `SOURCE_PINS.json` 先冻结到私有临时目录；将执行的同一 raw buffer 再按既有 helper SHA256 核验后直接 `compile/exec`，不经项目 SourceFileLoader/pyc。不导入模型或运行旧 replay/prepare 脚本，也不启动 `patch` 子进程。该一步属于将来明确组装动作，冷测不进入它。

生产92验证后才选择修复与tap文件、添加新emitter。输出使用全新目录，包含 `scala/` 的精确93源及 `SOURCE_RECEIPT.json`。旧92 pin只是已发布源谱系检查点，新的93 manifest和receipt才是当前派生身份。失败不能标作 SOURCE PASS。输出无JAR、工具二进制、class、IR、SV或权重。

## 依赖静态审查边界

87 JAR 精确锁集来自成功生产92闭包。新 emitter 仅引入该闭包已有的 ChiselStage、Java NIO 与原 HostBlockCollection，没有 Bench/Spec 测试依赖；Scala2.13.16、Chisel6.7.0和全版本plugin6.7.0保持一致。106中的 chiseltest/firrtl2/ScalaTest扩展不属于本次计划。87仍包含历史 resolver/coursier/sbt传递库，是精确保守充分集，不是逐个已证明必需的数学最小集。未做 POM/类加载最小化，不擅自删库或混入106的升级版本。

冷测通过只表示固定文本与计划自洽；实际源组装、93编译、共同Host IR/SV、provider/iDMA结构闭包、生成C++ readonly binding及真实单Host运行均需各自的新证据。dontTouch不保证C++ public registry可见。完整block RTL计数仍为0/5。

## v2 最窄加载修正

保留v1隔离副本，仅修正三个项目 Python 载入点：两处冷测待载脚本与组装器的固定 rebase helper，均采用已发布源码恢复测试的同 raw buffer 固定 SHA 核验后 `compile/exec`。获取冷测用 `python -I -S -B acquisition/tests/test_acquire.py -v` 直接入口，优化模式增加 `-O`，不再使用 `-m unittest discover`。`-B` 仅禁止写缓存，不能作为禁止读缓存的证据。普通/-O的有效污染pyc正控都应执行无害属性marker，而新源码载入器不执行它；真实 rebase helper仍未在冷测中加载，其载入函数只用合成源码测试。临时缓存不进入项目身份。五份获取计划、获取器、93源计划、新Scala emitter与旧helper来源hash保持不变。

## v3 有限失败反例修正

保留v1/v2。v3仅进一步修正获取器的成功receipt提交后清理、原始异常与清理异常分离、超时read计数，并同步三条独审反例和获取器的冷加载固定SHA。三加载点pyc修复保持；五份计划、Host组装器、新emitter和93源计划不变。成功提交后的清理问题是独立warning，不再生成FAILED双终态；失败清理问题记录为次级错误，不掩盖原始异常。详见 `DELTA_V3.json` 和获取片说明。
