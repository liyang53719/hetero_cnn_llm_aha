# 新93源组装单进程最窄限额入口

仅SOURCE候选。作者只跑8项普通/-O纯mock冷测，没有真实组装、Java、网络或native子进程。实际执行由父唯一进行，且必须先两组实际依赖独审通过。

入口只载入已发布assembler固定15,592B/SHA256 75a2145eea0de83ad1bbe3a7a64e1a5f14f20f9f1381f65e619fb5bd3d427641的同一raw buffer，直接compile/exec定义后调用原main。没有项目pyc加载。原assembler和其helper字节不改。

唯一函数护栏是原write_tree的前置检查：最终输出scala目录的数据必须93项、sum(len(data))≤32MiB，然后调用原write_tree；这一步发生在原assembler已核完整expected93哈希映射之后、任何最终source写入之前。其它临时replay树不改变语义。最终再核实际source93项、无symlink和总量≤32MiB。32MiB是最终93源内容界；OS FSIZE32MiB为单文件界，不声称整个临时工作目录硬总量界。

专用Python进程设置CPU affinity1、AS512MiB、CPU60s、单文件FSIZE32MiB、core0，入口绝对60s SIGALRM直到解释器退出；拒绝继承blocked SIGALRM或活动timer，不改继承屏蔽策略。不创建子进程，不引入生命周期框架，不恢复/放宽该专用进程限额。强制信号/进程退出时临时文件或未完成输出可残留，父保留现场，不把残留SOURCE_RECEIPT当通过。

原main stdout被暂存，只有末后验和原stop检查完成才打印非PASS SOURCE_EVIDENCE_PENDING_OUTER_EXIT0。父须独立保存真实退出0、实际全程≤60s、输入来源/新93完整identity/diff/closure核验；孤立SOURCE_RECEIPT或stdout不授予成功。没有class/IR/SV资格。

冷测：

    python -I -S -B test_source_wrapper_cold.py
    python -I -S -O -B test_source_wrapper_cold.py

父审后唯一实际调用（各绝对路径显式给出，output必须全新）：

    python -I -S -B run_source_assembly.py --repo ABSOLUTE_REPOSITORY --hardfloat-scala ABSOLUTE_HARDFLOAT_ATTEMPT/artifacts/hardfloat/src/main/scala --output ABSOLUTE_FRESH_SOURCE_OUTPUT --execute-reviewed-source

依赖：已发布111输入及当前assembler、新emitter与SOURCE_REPLAY_PLAN；固定HardFloat20且flat目录精确无额外文件；Python标准库。组装不需要87 JAR、firtool、Verilator、iDMA或Java。
