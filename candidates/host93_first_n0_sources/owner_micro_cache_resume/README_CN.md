# TEMP Owner 固定 header 修复与生成缓存续接（SOURCE）

原一次实际 generation 已自然退出0并完成cleanup，零warning/error；父后验读取4630258字节root header时，外层16MiB参数进入仍只允许4MiB的旧small_read，故原outer失败。原失败、全部日志和生成树保留，未编译/运行。本片准备读取修复和 fresh目录 build→run 续接，不重新生成或重建backend。

## 精确 header 门

header_gate.py 仅允许固定文件名、mode600、4630258字节与SHA256 a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf。直接调用原bootstrap.checked，显式16MiB绝对上限，消费该函数返回的同一已验buffer再ASCII解码。没有扩大或改写95字段parser，也没有把所有≤16MiB文件泛授为有效header。

真实header只读回放已通过全部95项；15项×普通/-O/搬迁=45次，通过固定身份、4MiB±和16MiB±元数据拒绝、同buffer与读取中漂移等反例。原header的SHA/mode/mtime/ctime未改。额外完整生成后验只读回放通过196端口、原cluster seed/seqnum初始化和库图，census与原receipt逐项一致、零warning/error；这只闭合源后验，不授编译或RTL行为资格。

## 完整缓存与真实编译路径

原固定库存536项、528文件、80670440字节，包含原fixture、完整生成obj、phase证据和失败RESULT，实际独审身份绑定后每阶段前后重验。将516个obj源、80273076字节用原checked同buffer读取并写入fresh目录；7个fresh fixture逐原driver manifest写入。无symlink/hardlink复用，无.o/.a/.gch/.so输入。所有原生成文件逐byte保持，编译后新对象/PCH/archive/ELF单独验收。

生成makefile保留旧fixture的绝对.cpp和-I路径。因此编译器读取的driver/include可以来自已经固定并逐阶段复核的旧只读fixture，不能声称全部来自fresh fixture。模型生成C++、目标.o/PCH/archive/ELF在fresh obj下；原完整树前后核确保无旧树漂移。新driver实例仍从fresh reset开始，没有恢复历史Host或owner进程状态。

固定make路线仅以原top .mk的显式VQwenOwnerKernel可执行目标运行，保留-j1、原-O0、固定CXX/AR/SHELL/MAKE与空OBJCACHE：

- 三个-o仅标记top.mk、child.mk、child wrapper.sv生成target，不标记任何对象、PCH、archive或ELF。
- 不使用hier_build。-o不经MAKEFLAGS继承；显式top executable仅递归child archive。该固定child.mk只include自身classes和原verilated.mk，没有hier.mk、递归make或Verilator生成配方，因此不存在漏传-o的下游生成门。
- 固定单argv `VM_HIER_VERILATOR=/bin/sh -c 'exit 97'` 作为command-line变量继承，意外触及生成配方就失败。其后-f和argsfile只是内层sh的位置参数，不执行Verilator或把argsfile当shell代码。
- 另固定VM_HIER_RUN_DIR=fresh work。原makefile和argsfile字节不改；旧绝对路径仅保留为受核只读来源，不进行无证重定位。
- 原clean env不携带外界MAKEFLAGS/MAKEFILES/MAKEOVERRIDES注入。未执行make dry-run；当前依据固定实际make图、源审和纯mock，实际编译仍待监督与独审。

## 同一960秒与原首错

最早父T0包含private命令、解释器、源hash、缓存复验/复制与全部后验。build600秒（work/CPU585）、run300秒（work/CPU285）、尾证据60秒；全部AS6GiB、单CPU，原MemAvailable≥8GiB/磁盘≥3GiB准入。每阶段开始前及前验后必须剩完整该阶段窗口+60尾，否则INCOMPLETE首停。父950TERM+5KILL+5落证包住同一960上限；不承诺未知编译/运行性能一定到达目标。

原监督不改；本片二阶段sequence仅去除generate并收紧总预算。任何native、cleanup、资源、源码/ELF后验失败即停止。保原first exception/code/traceback，完整native.log只作固定大小/SHA观察，secondary日志/落证/恢复错误不得覆盖原错误。不靠RESULT某个完成字段或opaque日志布尔授予actual成功。原generation只记EXISTING_GENERATION_REVALIDATED_READ_ONLY，绝不计作本轮native阶段。

cache 22项×普通/-O/搬迁=66次通过，含固定库存/receipt、禁止对象复用、三个-o、同buffer复制/readback漂移、两阶段时窗和首错。与header合计111次，无失败/错误/skip；每测试进程AS512MiB、CPU30秒、单CPU。没有复制真实80MB树、执行make/编译/RTL或生产run/main。完整真实树只读后验是另一个受限检查，非native重放。

full job/full block=false；历史Host故障重现、official/application accuracy、typed-to-RTL均null。私有binding/profile/精确COMMAND/outer/实际机器路径和日志仅本地，公开BINDING_TEMPLATE不可直接运行。父在SOURCE及精确命令独审、当前准入通过后执行唯一续接。
