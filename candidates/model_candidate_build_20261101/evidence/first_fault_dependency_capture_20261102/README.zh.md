# First-fault 依赖捕获至七件出口：有界夹具验证

本目录仅发布运行源码与有限摘要，不包含 SV、ELF、原始日志、依赖清单正文或合成产物。

## 实测范围

真实执行当前 Python producer.run → prepare/pins → candidate capture → pack → 完整 dependency proof → exporter CLI → 七件校验。实际 GCC 仅预处理真实驱动（-E -MMD），产生 16 个依赖词、15 个唯一依赖；同一 VHostBlockTopV4.h 词重复两次。原始 .d 文本/hash 保留，全部唯一依赖继续逐文件绑定。**五个编译阶段的归档、ELF、收据及其他构建收据均为合成夹具**，没有执行这些 ELF，没有真实完整 C++ 编译、DUT 或数值验收。

一次正常模式完整链 strict native 0，13.987 秒、采样 RSS 87,285,760 B；实际出口 GITHUB_OUTPUT 指向目录并通过原七件验证器，七件均为普通非空文件、全 hash 通过，228,182,180 B。仅复制一次已持有的固定 SV（224,341,716 B）。这不是原远端运行的产物，也没有观察到远端 41441028806 的实际 .d，不能据此断言其失败词。

12 个反例真实拒绝：额外未 pin 依赖、漏唯一 pin、不同词归一化同路径、4097 原始词、错误 policy、缺 root header、缺 readonly helper、错误固定 SV、缺 config、错误合同、legacy 混用新 policy、capture 缺非角色依赖 pin。未 mock prepare/capture/proof/export 门。

R1 的合成 VM_USER_DIR 布局错误与 R2 的夹具传递头遗漏均保留原失败收据；每次修复仅针对夹具，不修改产品规则。摘要给出这些原证据的 SHA，不上传日志。第三次执行才是上述正例。

## 手动复现（不是自动单元测试）

需已持有对应 source snapshot（原 879 文件 catalog）、只读七件 payload、原 source fallback，以及已固定 Verilator include 工具树；不自动下载。源码使用五个显式路径参数：

```sh
python run_fixture.py --source-root SOURCE --payload PAYLOAD --old-source ORIGINAL_SOURCE --verilator-root VERILATOR_ROOT --output NEW_EMPTY_OUTPUT
```

必须由外层监督执行：RSS 1 GiB、AS 8 GiB、CPU 60 秒、wall 90 秒、cleanup 30 秒；file 256 MiB、阶段输出 512 MiB、所有读写 roots 合计 1 GiB、100000 entries；内存准入 7 GiB、磁盘 8 GiB 加 256 MiB 初始拷贝余量。将上述输入 roots 和新输出全部纳 watch；系统工具逐 SHA 固定，不泛扫 /usr。不应直接作为无监督自动大文件测试运行。一次只写新的输出目录，保留失败现场，不覆盖原证据。

仅完整链正常模式实测；-O 只检查 CLI --help/语法，未重复大文件链，不能宣称优化模式完整实测。脚本所有验收使用显式 need，不依赖 assert。

Builder 保持未审状态，数值/最终 RTL PASS 均为 false；原有完整 block M128 与最终 RTL 验收范围不增加。
