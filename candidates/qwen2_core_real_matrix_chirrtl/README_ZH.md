# 真实 Matrix shell：实际 CHIRRTL 构造与声明 ABI（有限 PASS）

本批复用已公开双 Scala 源与 compile 结果；新增原字节结构 checker、25 项小合成测试、契约和可逆 core 校验片段。原执行由 root 完成，独立实际审查已通过；本包只复核小源、元数据和合成控制，不重复 JVM/EDA/真实 FIR 解析。

## 已发生的结果

- 一次 ChiselMain `--target chirrtl` 子进程 exit 0，确实完成 Chisel 构造与 common-namespace CHIRRTL 序列化。唯一硬件输出 FIR **19,551,779 bytes**，SHA256 `bdfbf223cc8c1c8de8a8d21450272878d1422842bc17a452bcef45e9878573bc`；只发布其 hash，不上传 FIR。
- **375 模块定义（359 普通 + 16 external）、374 instance 声明**。集合可达全部 375 定义，选定 shell 可达 366；这些不是未来 SV 去重后或物理硬件的数量。8 endpoint + 8 ICG external 对应两 provider 家族，endpoint 22 端口 / ICG 4 端口，无新 seed 参数。13 provider 源只绑定 hash，未在本轮 lint 或执行。
- 头部 1,546,274 bytes；9,330 annotations = 8,955 DontTouch + **375 DedupGroup（包含 external）**。四 FMA RawModule 声明与 common namespace 唯一性通过，但不是选定 shell 已执行的 FMA。collection 不是未来仿真 top；未来 top 名为 `OrderedQkRealMatrixCore`。
- 独立审查还核了 emitted-text 的 13 项直连接线、8 个反向 lease gate、9 个前向 mux、两个 client 的各 4,096-word result 广播及 8 条 ICG→endpoint clock 连接。它们不是运行中的 backpressure、保持性、全 tile 非零数值或时序验证。
- 557 staged classes 共 9,695,031 bytes，原路径/hash/0444 未变；1,398 pins / 5 inventories 前后及独审 fresh 复核通过。实际总文件 561 / 29,300,912 bytes，独审各 normal / -O **39,792 checks**。本轮不重新编译类。
- 实际 CPU **11.995029048 s**，child elapsed 12.041842219 s，outer wall 12.151900938 s；采样 RSS 高水位 **323,686,400 bytes**，不是连续精确峰值。清理顺序、双扫描、reap 与 authority release 收据通过，未重建 live process handle。

## 警告、外部门与历史边界

保留来自 `Qwen2Block.scala:629` 的 **4 个 W005**。独审只对当前 column-index 表达式的 16 个 stripe 常量 × 16 个 lane 作 256 项静态范围检查，未发现该表达式截断/越界；这不是全局数值通过，不抹除警告。源码准备期“两输出含独立 anno.json”的旧 STOP 也保留：当前分支只有单 FIR、annotation 内联。`HEADER_SIZE_BASIS.json` 是执行前估计，不能替代本次实测头部。

本轮 root 外部门历史文件只保存 **counts/pass/locale**（56 pins、12 absence、passed），不是逐项历史 hash/absence 映射。root 确认原 launcher 按冻结 ROOT_REQUIRED 逐项检查后落这些计数；其 **2,551-byte 原字节脚本在执行后归档，未预先绑定 hash**。原 `python -I -S -B` 无 `-O`、assert 有效，来自 root 工具历史确认而非补造日志；独审另做 fresh endpoint 复核，不能倒推历史逐项记录或 syscall replay。原编译批及更早 Python coverage 缺口不回填。

CHISEL_ARGUMENT_EXTENSIONS=DISABLE 仅为已授权 child-local 环境；并非全局安全设置变更。解析器的文件/行/header/count 上限不是父进程硬 AS/RSS 上限，采样也不是全系统精确峰值。

## 不在 PASS 范围

**未执行 firtool/SV/provider 模型/数值/clocked RTL；未证明完整 FIRRTL lowering 合法性、真实 Matrix 全 FMA、全 tile probe、full128 RTL、full29/full block、物理 DDR、时延/面积或 90% 有效 MAC 周期利用率。** 非零独立参考尚未冻结；issued slots 不是 effective MAC。此前 4/6 GiB 4096 路资源 FAIL、旧 Treadle CPU FAIL/STOP 均保持。已发布 M17 的 scripted endpoint 有限行为 PASS 不转移到真实 Matrix。

## 源码与离线复核

`pins/EXISTING_PUBLIC_REFERENCES.json` 固定 base commit 的 12 个公开引用；不重复 Scala/模型源码或依赖实体。`pins/CHIRRTL_EXECUTION_ROLES.json` 给出可移植角色化 argv、106 JAR 次序引用、资源边界与原私有 supervisor/manifest 的 hash，**不是原运行目录/完整可执行私有配置**。官方依赖及 13 provider 仍须按引用独立取得并核 hash；本包不自动下载/启动。

在已检出的仓库中运行小文件控制（不读真实 FIR）：

```sh
python -I -S -B candidates/qwen2_core_real_matrix_chirrtl/structure/test_check_chirrtl.py
python -I -S -B -O candidates/qwen2_core_real_matrix_chirrtl/structure/test_check_chirrtl.py
python -I -S -B candidates/qwen2_core_real_matrix_chirrtl/rebuild_stage_hashes.py --repo-root . --output stage_hashes.json
```

第三条只从既有公开 hash 元数据重建 557 条类身份，不重建、读取或执行 class；输出必须不存在且父目录已存在，拒绝 symlink/traversal/hash 漂移。`CORE_VALIDATION_DELTA.diff` 只描述旧 checker 内提取的 core gate 片段：根选择改为 nested core，reset 从 UInt1 改为 Reset；不是整个 checker 的补丁。新 wrapper/annotation gate 在完整原字节源中。合成 PASS 只资格化 checker，不替代原实际审查或未来硬件验证。

本包不改 canonical checklist 的 todo/ongoing/done，不将整体主任务置 done，不带未来未执行的 SV 候选。
