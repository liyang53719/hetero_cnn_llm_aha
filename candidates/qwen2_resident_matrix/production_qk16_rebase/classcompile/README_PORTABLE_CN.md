# 生产 QK16 源码闭包与 classcompile 安全投影

根目录原 10 个 source recipe 文件逐字保持原冻结身份。这里只增加可移植输入适配与白名单结果摘要。原本机 driver 的实际 92 源→550 classes、74.776 秒 classcompile 已成功且独审；本目录显式路径 driver 只完成冷测试及 preflight，没有再启动 Java。classcompile 不是 elaboration、RTL、协议或数值通过，也不证明供数或性能。

## 消费者输入

调用者提供已验证的生产源码根 PROD、原 QK16 donor 根 QK、HardFloat 的 src/main/scala 目录 HF、现有 87 jar 缓存 CACHE 和 JDK21 java 文件 JAVA。均为显式参数，不绑定生成机器的绝对路径，不自动下载。生产和 donor 可按已有已发布 source recipe 重建；SOURCE_PINS.json 校验 7 个关键输入，PLANNED_SOURCE_PINS.json 再校验完整最终 92 个文件。HF 的 20 源包含在 92 pins 中；仅有 donor 的孤立 patch 不能代替完整输入根。所有不匹配拒绝执行，不回退未知版本。

从 candidate 根目录运行（变量由消费者赋值）：

```sh
python -B classcompile/reproduce_sources.py --production-source "$PROD" --qk16-source "$QK" --hardfloat-scala "$HF" --output "$NEW_SOURCE"
python -B classcompile/compile_only.py --preflight-only --source-root "$NEW_SOURCE" --dependency-cache "$CACHE" --java "$JAVA" --output "$NEW_ATTEMPT"
python -B classcompile/test_portable.py --production-source "$PROD" --qk16-source "$QK" --hardfloat-scala "$HF" -v
python -B classcompile/test_runner.py -v
```

preflight 不创建输出目录、不启动 JVM。实际执行须另获批准，把 --preflight-only 换为 --execute-approved-once；始终使用全新输出，不引用旧 classes，不自动重试。包内没有 classes、jars、原始机器进程身份证据。Linux /proc、POSIX signals、进程 affinity 为 supervisor 平台要求，并非跨操作系统承诺。

## 约束与证据范围

入口绝对预算120秒，work至108秒、cleanup至116秒、postflight至120秒，前后校验源码/JDK/jars。单CPU affinity；Xmx1GiB仅堆上限，不是整树内存硬限，未设 RLIMIT_AS。日志父进程2MiB硬限；class树64MiB采样软限，单文件48MiB RLIMIT_FSIZE是独立约束。清理仅作用于原已锚定组和观察到的身份；不能泛称杀尽全机 Java。

SAFE_COMPILE_RESULT.json 仅投影实际一次编译的统计、边界、cleanup顺序及 patch身份；删除 PID/PPID/启动时刻/组号/scan fingerprint/机器路径。原始receipt与独审保留在原审计环境；安全投影不能独立重建那些进程证据。RUNNER_PINS.json 是本便携适配身份，不冒充实际已执行本机 runner 身份。数值、RTL、物理资源和端到端性能仍待各自验证。

## 上游 source-only 入口

生产输入使用仓库 candidates/qwen2_resident_matrix/production_qkv_reduction/replay.py，显式 --source-root CHECKOUT --out NEW_WORK；PROD 指其 source 子目录。QK 输入使用同仓库 candidates.qwen2_resident_matrix.attention_qk16_owner_route.prepare.compose(NEW_QK)（从仓库根导入），其内部逐级调用已有 attention_qk_owner_route recipe，验证 pins 并应用零 fuzz patch；本包只需要其中两个 donor 文件，完整原 QK 编译树不是必要输入。不要用后续 BF16 materialize postimage 替换本 donor，生产 policy 已保留单份舍入位置。HF 输入目录单独提供，92-source pins 验证其20文件。
