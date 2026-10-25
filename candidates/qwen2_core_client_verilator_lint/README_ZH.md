# 官方 Verilator 恢复与实际 lint-only 验收（限定范围）

**PASS 仅指固定原始 SV 通过官方 Debian Verilator 5.032-1+b2 的实际 lint-only 调用。** 不是 C++ codegen、编译、可执行模型、M1 行为、数值、full128 RTL、full29 或 90% MAC 利用率通过。本包不含后继 codegen/harness 候选，也不更改 canonical 的 todo/ongoing/done 或任何旧 FAIL/STOP。

## 已发生的事实

- 官方 deb：7,565,144 B，SHA256 `238ab4ca84cddd371f113cd549f16f2d65c43e7b4962a763bea1d259158dd3b2`。首次下载成功但提取因文档链接目标不在包内而 FAIL；保留原记录。r2 不重下载，只在全新私有树提取同一 archive，允许 22 个不越出提取树的缺失文档链接；173 regular files / 33,804,795 B。不系统安装、不运行 maintainer scripts。
- 输入是已公开哈希绑定的原始 `OrderedQkBehaviorCore` SV，26,251,369 B，SHA256 `77f61549b4aebd109362d30164f95422b9192d0a8b2b1599942a9360852f9225`。不是 NoCSE 类集重新生成的 SV，也没有修改原 PackedClient。
- 实际 Perl frontend、supervisor/root 返回 0，已清理回收；间接 backend 返回值没有单独序列化。自动前后各核 3,662 pins（3,660 manifest roles + manifest/supervisor 2 条）、12 inventories、24 缺失槽、13 aliases；清理 helper 是另行前后 pin，**不能计入自动 3,662**。这是端点/冻结身份闭环，不是全机连续隔离或动态 import/dlopen 全追踪。
- 最终 aggregate CPU **17.708661163 s**，root wall **17.92034880304709 s**，采样 RSS 高水位 **435,056,640 B**（不是连续峰值）。资源限额和精确 role argv/environment 见 pins；无自动重跑或阶段串联。
- 实际目录只有 **3 个元数据/日志文件，12,692 B；4 个空输出目录**。没有可用 C++/header/model/build 落盘，没有编译、链接、仿真。

## 不把日志内部计数当新产物

日志所称 30 C++ / 22.763 MB 是 lint 内部 emitter 仍检查并向 `/dev/null` 写入的计数；版本匹配官方源码和实际目录盘点共同限定含义。MB 标签按 1024² 换算；不能据此推下一次 codegen 的准确产物集或资源一定够用。8.618 MB / 26 internal modules 也不能替代真实输入字节和既有 25 个 SV module declarations。打印 CPU 0.000 不是实际零 CPU；原因未诊断，使用监督 CPU。打印 1 threads 是配置 jobs 上界计算，不是 OS 线程普查；alloced 和 rounded phase timers 不是采样 RSS 或完整阶段 CPU 归因。

无 `-Wno`，但也没有 `-Wall`，所以“没有报告 warning/error”不等于覆盖所有 warning 类别。`--no-timing` 不证明时序/存储语义等价。此前 R3 仅声明/ABI/实例/存储结构 PASS；原 native 外层 FAIL、离线 r1 FAIL、r2 STOP 和 Treadle CPU600/150 FAIL 均原样保留。

## 最小复现材料与限制

`source/restore_package.py` 与 `source/extract_verified_package_r2.py` 是实际恢复的原字节脚本；放入独立、全新且可信的工作目录，先读固定 URL/大小/SHA。首脚本会保留原提取失败；二脚本只复用锁定 archive。它们不安装或执行包内容。**本包验证只用合成内存 ar/tar，小测试不下载 deb、不读真实 SV、不运行 Perl/Verilator。** 不应把固定包脚本推广成任意不可信 archive 的通用安全解包器。

`pins` 提供官方 URL/关键工具摘要、私有监督/恢复相关脚本 hash、role 化 argv/environment、运行清单 hash/计数、版本匹配上游源码定位和已有公开证据引用。未上传整个 Perl/ELF 运行时或私有配置；不是私有运行环境的完整可移植快照，新环境仍需重新构建并审核完整 pins、搜索候选边界、外置 helper 前后检查和有界监督。仅描述复现条件，不自带下一次执行授权。

合成验证：`python3 -B test_restore_synthetic.py` 与 `python3 -B -O test_restore_synthetic.py`。它们只覆盖脚本归档解析/提取的明确小输入条件，不是真实工具、SV 或硬件验收。
