# PC01 失败 capsule：最小 driver 重链 SOURCE 后继

本片只固定 SOURCE 与纯 mock 测试，不编译、不运行 PC01，也不授权重放。原实际失败仍是 natural exit 1 / PC1_022，8 个谓词中的具体失败项和根因 UNKNOWN；数值比较 NOT_RUN，full_block_pass=false。

生产 run_relink.py 只有三行变化：CONFIG_PIN、PRODUCTION_PIN，以及 source count 28→29；逆向投影逐字节恢复原已审入口。launch.py 只改 CALLER_PIN。原监督函数、异常优先级、固定 compiler/dependency gate、argv/env、180 秒总界、95 秒 compile、25 秒 link、30 秒尾储备、TERM 170/KILL 5/尾5不改。

新组装源码恰有29件：24件原桥未变，4件由已发布 capsule 覆盖，新增1件 capsule header。原44来源pin、19件archive/header/runtime object及39系统依赖不变；fresh stage总数为48。新驱动只编译一个 pc01_main.cpp，并链接同一普通 archive；不会调用原Makefile/backend/RTL emitter，重链不执行生成ELF。

## 可搬迁纯冷测

需要一个同时含下列三个公开目录的完整仓库检出：
- candidates/host93_first_n0_sources/pc01_bridge/
- candidates/host93_first_n0_sources/pc01_failure_capsule/
- candidates/host93_first_n0_sources/pc01_capsule_relink/

从仓库根运行：

    python3 -I -S -B candidates/host93_first_n0_sources/pc01_capsule_relink/run_public_cold.py
    python3 -I -S -B -O candidates/host93_first_n0_sources/pc01_capsule_relink/run_public_cold.py

入口若被搬迁，增加 --repo-root /path/to/the/complete/repository；这是显式公开源码根，不是私有运行或cache根。入口先固定核 launch.py 与 PUBLIC_COLD_INPUTS.json 的size/SHA，再复用原checked读取39份公开输入为同一buffer。随后复用原write_exact，在新可写临时夹构建29源及原测试需要的文件，只执行同buffer的原 run_cold.py；不产生native child，不读取archive或真实数组，不运行compiler/模型。原run_cold.py无自定义参数，要求-I -S -B，-O为可选第二模式；原完整101测试不修改。

本片不发布重复assembled_source、私有config/依赖路径清单、缓存、outer命令、日志、数组或二进制。ASSEMBLED_PRODUCTION_MANIFEST.json 是4632 B/SHA256 0e6dcab21cec61004b35d6b657456ace9817f7a6be382077e6c2c80bb433ba4a，只列公开源码相对路径。PUBLIC_COLD_INPUTS.json也仅含固定公开相对路径与身份；runtime实际绑定保留私有，精确180秒入口已有独审；真实调用仍单独依GO执行和落证。

作者最初Python3.12四模式各101通过；固定Python3.13可写搬迁normal/-O各101通过。冻结read-only public直接运行继承测试会因HERE临时夹权限失败，故使用上述可写fixture入口。新增入口是独立纯测试delta，不改原54成员冻结SOURCE。独审/发布结论以STATUS为准；本片不声称实际重链或RTL已经运行。

正式生产SOURCE独审为 ACCEPT_PC01_CAPSULE_DRIVER_RELINK_SOURCE_AND_FIXED_180_SECOND_CONTRACT_ONLY；review MANIFEST867 B/8c277daab23a327e7855836efec358dad77f8b71589ec950ee426fc4e2e6c615，SUMMARY3506 B/e74c8bd61f1f9575fdbfbae4d65fdf8119b3e8d730de135f1b70c5b25c61c4f6。独审固定Python3.13搬迁双模各101通过。公开fixture薄入口作者固定Python3.13四模式各101通过，missing header、同长header漂移、同长manifest漂移、未pin入口四负控在普通/-O均拒绝；该新增test入口的独立delta审查已通过，不扩展生产资格。

公开纯测试入口正式独审 ACCEPT_PC01_CAPSULE_RELINK_PUBLIC_COLD_ENTRY_ONLY；MANIFEST1399 B/357114cbe5d20be524b3fde1f094b45877a5d19f9a5cfc2774059d9b0ee9385c，SUMMARY1858 B/aba3aee700aa3006782c9fc62efd715f9d70b50212feeff6440cc6d048dc4ef2。独立Python3.13搬迁普通101与优化101均通过，4+4负控均在runner/test编译前拒绝；一次优化负控允许stdlib初始化编译，不声称所有compile事件为零。冻结作者delta中的旧待审文字由本STATUS补充真实身份，不热改已审源或test。安全发布内容审查仍独立；未执行真实重链、PC01或数值比较。
