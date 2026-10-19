# PC1 两参考模型的三阶段监督入口

状态：SOURCE_ONLY；native 编译、micro 和 full_models 尚未执行。独立核心 SOURCE 已获 ACCEPT_PC1_TWO_REFERENCE_MODELS_SOURCE_ONLY，本批仅增加执行资格、固定依赖与原监督器接线。官方原入口 qraw PASS、应用精度 PASS、RTL bit-exact 均仍为 null。

## 固定入口与私有接线

`launch.py` 要求 Python `-I -S -B`，校验并执行同一 buffer 的 `run_reference.py`。后者只接受一个固定身份的私有配置；CLI 为 `--private-config <private-binding> --execute-reviewed-models`。机器路径、先前私有收据、实际输入与未来 work 路径只在 private 文件中，不进入公开源码。所有源加载按固定 size/SHA；原 bootstrap、mount observer、support 以及核心 prepare 均零修改。

依赖清单固定 36 项共 58,139,729 字节，包含既有绑定的 g++、cc1plus、collect2、as、ld，固定启动/静态链接对象，以及 16 个有限 ELF soname 的闭合映射。每次调用前后复核原 user namespace、只读 nosuid/nodev mount、祖先不可写、fd 快照与 size/SHA。它是这次固定命令的最窄清单，不是通用系统闭包。编译输入系统头文件所在只读映射沿既有 mount profile；本清单不声称逐个列举所有头文件。

原 ELF reader 只做两个数值边界投影：文件 32 MiB 改 64 MiB，DT_STRSZ 1 MiB 改 2 MiB。实际固定 cc1plus 为 36,389,344 字节，DT_STRSZ 为 1,489,147 字节。函数 AST 唯一定位、两锚唯一匹配、逆替换逐字节还原；其余 interpreter、segment、RPATH、soname 检查不变。有限 soname 表用于这次静态依赖资格。

编译 argv 相对核心合同唯一增加 `-B <fresh-private-search>/`。该目录只含四个固定工具 symlink；PATH 仅该目录。g++ 使用原已绑定 realpath，LD_LIBRARY_PATH 仅固定库目录。原核心编译 flags 不变，禁用 fast-math/隐式 contraction，单线程/单 CPU。编译产物必须是固定默认 PIE ELF，依赖闭合、完整 size/SHA 固定后才可执行；micro 与 full 前后重复检查。

## 三阶段与收尾

复用原 ci_support_v3.fixed_support/run_phase；原 owner、shared_stop、natural exit、WNOWAIT/reap/group cleanup 与首错处理不改。总墙时 210 秒从前置开始，保留 25 秒最终校验/收据空间；每阶段必须完整容纳其 total window，失败或不足即 INCOMPLETE，不续后阶段。

| 阶段 | total | work | CPU |
|---|---:|---:|---:|
| compile | 45 s | 30 s | 30 s |
| micro | 20 s | 5 s | 3 s |
| full_models | 120 s | 105 s | 100 s |

父进程硬限额为 AS 512 MiB、CPU 210 秒、单文件 16 MiB；每个 child AS 512 MiB、单文件 16 MiB、日志 64 KiB，CPU 分阶段。父继承 hard 低于所需限额则拒绝，不提高已有 hard。RSS 384 MiB 是原监督器累计已回收 children maxrss 的阶段后门；它不是瞬时逐后代 RSS 硬限额。真正内存硬限额为每进程 RLIMIT_AS 512 MiB。原监督器保留其采样与清理机制。

原先 N0 成功收据/ACK0/B retire/196608/hash-exact 资格先核；独立 historical N0 与本次已接受同 RAM N0 全字节相同，后者只作身份门。核心 prepare 只把独立 N0 与固定 wq 复制到新工作目录。native 再对完整输入做 hash/有限 BF16 验证，full 后复核三份完整输出与原输入。不会重生 N0、恢复旧 RAM、采用 typed 模型作新基线或改变阈值。

失败始终保留原异常；即使最终收据写失败也不覆盖首次失败。full 已请求但未成功返回时 extent 为 null；退出零但 stdout/后置资格失败时仍为 INCOMPLETE。只有三阶段自然退出零、cleanup 确认、输出与全部后门通过才写 COMPLETE_SUPERVISED_TWO_REFERENCE_MODELS。

## 冷测

46 个纯合成/mock 测试在普通、`-O`、搬迁普通、搬迁 `-O` 四模式通过。审计钩子禁止 native child、网络、ctypes、Torch、NumPy；未读取完整真实数组。覆盖三阶段顺序/同 owner/同 deadline、预算/尾储备、首错/双错、退出/cleanup/RSS、binary 漂移、前后门、同 buffer/篡改/symlink、固定有限依赖负例、ELF 两 cap 逆投影与产物 PIE/依赖门。

实际调用命令、私有 36 项清单与启动配置均在独立 private 包；需独立审核通过后由父协调器唯一实际执行。SOURCE 测试通过不代表 native 模型或完整数值已执行。

## v2 有限复审修复

保留 v1 冻结件，仅修 E01/E02/E03：timer 与 signal 恢复各自捕获异常并保留原首错；所有前置检查及 binary 检查后，在原 run_phase 调用前再次确认完整阶段窗口；micro 与 full 返回并完成前门后，再核产物 binary identity。新增五个 mock 反例回归。原核心模型、45/20/120 秒阶段预算、25 秒尾储备与原监督器不变。启动私有路径仅换到 v2 包及新的空 work 名称，36 个依赖字节与静态观察不变。外层唯一实际调用必须同样绑定 210 秒总界。

## 独立 SOURCE 审核身份

ACCEPT_PC1_REFERENCE_THREE_STAGE_EXECUTION_SOURCE_ONLY。审核 manifest 887 B / 1e8361e6974bc6d19b169806bf891b62e2e8801b94af1433c4bf19d74c6a50dc；summary 3480 B / fdf44a67eded8289a8e074ff802ab4c21dc7b2b301dbee13ec8526a2f30c5a2e。独立普通/-O 各 46 例与原三反例复核闭合；实际 native/full 仍为 NOT_EXECUTED。父唯一执行须另外绑定包含 launcher 启动及有界收尾的 ≤210 秒外层总界。
