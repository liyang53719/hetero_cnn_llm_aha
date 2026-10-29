# TEMP：固定4096/32、前端优先、标准runner试验候选

本包只做原Chisel模型的仿真后端准备，不执行模型数值回归或最终RTL回放。没有本包CI实测PASS。未经root独立审核不得发布/dispatch。

## 唯一调度入口
`.github/workflows/hetero-fresh-fixed-frontend.yml`仅main分支唯一`ci_launch/fixed_frontend_20261029_once.json`路径push触发。先发布source/workflow（不触发），root另批仅新增launch manifest的一次提交，manifest.source_sha必须是直接父提交。checkout launch fetch-depth2，git核唯一父/唯一A文件、event.before/after、attempt1，再checkout精确sourceSHA。不能依赖Actions payload缺失的added/removed/modified字段。修改或重复manifest只产生便宜拒绝，不启动昂贵任务。`hetero-exclusive-numeric-bootstrap`且cancel=false，ubuntu-24.04单job350分钟。运行前仍检查原身份active/queued jobs。

launch JSON精确4字段：`schema=FRONTEND_ONE_SHOT_V1`、`source_sha=已审第一提交SHA`、`profile=FIXED4096_VECTOR32_FRONTEND_ONLY`、`nonce=fixed_frontend_20261029_once`。本source包不含launch文件，避免误激活或SHA循环。

`bootstrap_frontend.py --repo REPO --pipeline REPO/candidates/ci_frontend_pipeline_20261029 --work RUNNER_TEMP/hetero-frontend --reviewed-repo-sha REVIEWED_SHA --execute-reviewed-once`

具体顺序：官方预装JDK21.0.13+9新身份实查 → 106JAR+plugin原锁获取（不执行restore_inputs打印的旧155命令）→ 原Verilator5.032 deb逐操作文件验收 → 原iDMA artifact身份/到期/927member验收 → repo纯源重建13 Matrix provider → 锁定R2的155源码binding → fresh编译和originalhigh → canonical micro/full → 新JDK transform输出与已审原transform AST基线比较 → Host发射 → source-info目录限定SV比较 → FMA发射/重复HardFloat字节校验 → R7 MAKEFLAGS=-n原生plan → scanner完整退出 → lane、endpoint、Down、Host各按原生args独立串行codegen。

不会执行C++ make、权重获取、reference生产、DUT仿真或旧RTL数值；numerics始终INCOMPLETE。不使用本地残留classes/wrapper/SV；原artifact只提供可验证第三方source。

## 身份与边界
- R2 overlay f8cb8f64…，主矩阵4096 MAC/shared Vector32，不降硬件，不按profile重elaboration。
- 已审fixed high canonical manifest90464ff4…；Core/FIFO变换结果0a41c578…来自独立执行原变换的本地证据，不从fresh runner自学习。
- 已审c7 SV的限定比较基线252117aa…。仅正规Chisel `// @[...scala line:col]`目录前缀归一化；basename、line:col、其它所有注释含工具pragma及全部其它字节不变。任意其它差异失败停止。
- 新JDK采用JAVA_HOME_21_X64，实际vendor/version/amd64和image20261026.354.1检查；版本或image漂移停止重审。新toolchain不继承旧PASS。官方runner清单：https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2404-Readme.md
- Verilator文档/man的发行版外部symlink不属于操作closure；固定deb完整hash及usr/bin、usr/share/verilator所有操作文件验收，无sudo/安装脚本。
- GH_TOKEN只传原artifact只读获取阶段；DUT和compiler环境不含token。只上传≤32KiB严格字段白名单frontend-only-summary.json；不上传目录、日志、SV、C++、weights或参考bins。

## 资源，不冒充可完成证明
bootstrap共享1800s；总job预算21000s减去实际bootstrap耗时。canonical及新transform≤3GiB；plan≤7GiB/180s，原scanner退出后每native阶段≤12GiB/1800s，MemAvailable必须≥13GiB，不以16GB标签替代实测准入。

NEW multi-root supervisor持续统计W+repo及所有写入依赖目录；去嵌套/硬链接重复，单stage output cap和aggregate12,081,306,272B均生效，实时保留1.5GB free。计划总13,581,306,272B≤14,000,000,000B，未证明实际峰值或时限足够。不得降低硬件迁就不足资源。每段native0/errors空且原group完整cleanup后才下一段；限制是原group/观测身份，不冒称拦截所有escaped sessions。

全五profile输入/runtime准备独立另包；其原8GiB空闲获取门槛/总磁盘顺序尚需另审，不能由此前端结果继承数值PASS。
