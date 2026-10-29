# TEMP / INCOMPLETE：首次 JDK 失败后的独立只读诊断

原 frontend run 40814080857 attempt1 在 JDK inventory 子进程 exit1 后停止，20.5618秒，RSS47,480,832B。原子程序stderr没有保存到上传摘要，因此准确根因仍 UNKNOWN。这个新诊断不是原任务重跑，不编译、不下载JAR/工具/权重、不运行EDA/DUT，不改变已发布138f226源码，也不继承任何数值PASS。

## 受限观察
只读取标准ubuntu-24.04预装 JAVA_HOME_21_X64 的release四字段（JAVA_VERSION/JAVA_RUNTIME_VERSION/IMPLEMENTOR/OS_ARCH）、ImageVersion/ImageOS、架构及JDK文件树计数。原样Java参数 `-XshowSettings:properties -version` 在4GiB AS、单CPU、20秒、无Java选项环境变量下执行；stdout/stderr各用受64KiB RLIMIT_FSIZE限制的临时文件，最终只保留各64KiB。原probe失败才执行附加有界heap/metadata/code-cache/ActiveProcessorCount参数的第二探针。HOME/TMPDIR隔离，明确不称原runner环境逐字节复现。

JDK树检查最多60秒/600,000,000B，记录外链计数及异常时已完成的部分计数；异常仅class/errno，不输出任意异常文本、全环境或凭据。单个JDK_DIAGNOSTIC.json最多300,000B，workflow仅上传该文件，不上传probe_home或目录。探针exit0/采集完成不等于JDK资格通过，更不等于Chisel/RTL数值通过。

## 单次调度边界
先发布本源码/workflow，不包含launch manifest，故不启动任务。另经root批准只新增 `ci_launch/jdk_diagnostic_20261029_once.json`，四字段为schema=JDK_DIAGNOSTIC_ONE_SHOT_V1、source_sha=第一源码提交SHA、profile=JDK_PREFLIGHT_DIAGNOSTIC_ONLY、nonce=jdk_diagnostic_20261029_once。必须直接父提交、event.before/after、实际git diff单A、attempt1全部匹配，再checkout精确源码提交。

独立workflow使用标准ubuntu-24.04、5分钟总上限、hetero-exclusive-numeric-bootstrap组且不取消运行中任务。不使用付费大runner，不自动重试；任何后续前端试验需再审。完整五块M128 Chisel及最终RTL数值仍0/5。
