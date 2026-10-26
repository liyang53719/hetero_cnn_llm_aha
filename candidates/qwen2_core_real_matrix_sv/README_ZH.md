# 真实 Matrix common SV：生成、声明与限定接线 PASS

本批绑定已审实际结果，不重复 firtool/JVM/真实 SV 解析。PASS 精确限于官方固定 firtool 的一次 **SV 生成、common namespace、声明 ABI 和选中接线文本**；不是 provider 实现、clocked 行为、数值或 full4096 resource-fit 通过。

## 实际结果

- 原目标 exit 0。SV **48,274,540 bytes**，SHA256 `c117e75ae97fb0a978e7cebe8e942a652bf1fbe927505d66092fa39b87380181`；只提交 hash，绝不提交 SV/FIR/ELF。原输入 FIR 与固定 firtool 分别为 19,551,779 / 25,009,456 bytes，精确身份见 `ARTIFACT_SUMMARY.json`。
- **38 definitions、118 instance declarations、选中 shell 可达 31 个 definitions**。118 是源码声明数，不是层级展开的物理资源。旧 375 CHIRRTL 与新 38 SV 不能直接比较成资源削减。collection 的 5 个子实例为 shell 与四 FMA 兄弟；未来仿真 top 是 `OrderedQkRealMatrixCore`，collection 额外 FMA 不算选中 shell 已连通/已运行资源。
- 声明 ABI 精确为 collection 100、shell 81、core 8,859、FMA Pre 7 / Mul 4 / Post 4 / Round 4。只允许 **2 个已知但未实现的外部 family**：22-port `qwen2_matrix_command_endpoint` 与 4-port `tc_clk_gating`，选中层级各 8 次，named connections 完整非空。13 provider 只保留原源 pins，没有送入 firtool 或编译执行；不能称“无黑盒”。
- 原 SRAM / scores / probs 容量声明保持；另核两份 4,096-word FP32 result storage，共 **8,192 个 32-bit reg 声明**。不是初值、读延迟或动态保留证明。
- 独审实际 emitted-text 核验 77 条 alias、278 条 legacy request、8 个 reverse lease gate、282 个 forward mux 叶与 3 个合法常量折叠、4,096-word service 广播与真实 legacy 回传、8 对 ICG clock。实际 drain 连接不是 scripted `steps==8`；但这些仍是接线文本，不是事务/背压/ACK/done/retention或算术行为验收。
- 终态 **6 files / 92,858,544 bytes**；无额外文件或 annotation 输出。949 pins / 5 inventories 前后与 actual fresh 复核通过；947 declared entries 包含重复路径，不等于 947 unique paths（实际 927）。独审 normal/-O 各 **10,338 checks**，无目标重跑。
- 实际 aggregate CPU **42.287860059 s**，outer wall **42.392034033 s**，采样 RSS 高水位 **728,567,808 bytes**。这些不等于连续精确峰值或下一阶段 provider 展开的成本保证。原 420 CPU / 540 outer 等资源门不变；清理持久证据闭环，不重建 live handles。

## 必须保留的警告和 root 历史

本次日志保留 **1 条 `DedupGroupAnnotation` 未处理 warning**。按 annotation class 去重后的 warning 行数不是残留 annotation 个数；没有 `circt.anno.json` 也不证明注解全部处理。原独审的官方源码分析仅支持可能解释，未跟踪每个实际中间 annotation，**不宣称完全无害、消除或全 warning-free**。此前 CHIRRTL 的 4 个 W005 未因本次日志不重复它而被修复。

原 wrapper 首次把 FREEZE dict 当 list，**在 root/claim/目标 Popen 前**停止；只作 schema 转换，保留前后脚本 hash/差异，不是 firtool 重试或预算重开。本次实际 launcher 在目标 Popen 前由 ROOT_APPROVAL 绑定 hash，与上一批 CHIRRTL 的事后归档不同。外门本次保存 **56 项 expected pins、32 个 absence 槽及执行 ck 后的 pass**；并非另存每项即时计算的 observed-hash 轨迹。工具历史确认原 `python -I -S -B` 无 `-O`、assert 有效；独审 fresh-current 复核是另一层，不倒填过去记录或声称 syscall replay。

## 不升级的范围

旧 full4096 资源 FAIL、Treadle CPU FAIL、旧 checker FAIL/STOP 与 canonical todo/ongoing/done 不变。**未通过 provider Verilator 闭包、23 额外 seed/诊断端口适配、全 tile 外部 probe、非零 M1 数值、全 FMA、full128 RTL、full29/full block、时延面积或 90% 有效 MAC 周期利用率。** `issuedSliceSteps` 不是 completed/useful MAC。本次 48 MB SV 生成成功不等于 8×512 provider 展开后的资源 fit；不继承 M17 scripted endpoint 的行为 PASS。

## 小源码复现与合成控制

`pins/EXISTING_PUBLIC_REFERENCES.json` 固定 12 个公开引用。原 `structure/check_sv.py` / `test_check_sv.py` 字节保持；16,809-byte 旧 streaming lexer/parse prefix 完全相同，后置选择图与严格目录门新改动如实记录。官方保留字/Exporter 源资格复用公开 pins，不声称通用 SV grammar 或官方编译器资格。

`rebuild_expectation.py` 仅执行精确 hash 的既有纯类型 flattener，结合小类型投影与 template，重建 **1,181,883-byte 声明期待 JSON**；这不是权重、信号值或生成 RTL，故不把大重复期待表提交 Git。helper 拒绝引用/hash 漂移、symlink/traversal 与已有输出。例：

```sh
mkdir common_sv_synthetic
cp candidates/qwen2_core_real_matrix_sv/structure/{check_sv,test_check_sv}.py common_sv_synthetic/
cp candidates/qwen2_core_client_sv_structure/derive_ports.py common_sv_synthetic/
python -I -S -B candidates/qwen2_core_real_matrix_sv/rebuild_expectation.py --repository-root . --output common_sv_synthetic/STRUCTURE_EXPECTATION.json
python -I -S -B common_sv_synthetic/test_check_sv.py
python -I -S -B -O common_sv_synthetic/test_check_sv.py
```

40 个原小合成测试与 9 个包装 helper 控制两模式通过；测试使用微小声明 fixture，不读取真实 SV。本次隔离执行只将原测试通用 `/tmp` 根重定向到包装 scratch，原源字节未改。合成 PASS 不替代实际审查。

角色化 argv、caps、原私有 supervisor/manifest 的 hash 见 `SV_EXECUTION_ROLES.json`；是可核的复现契约，**不是完整私有运行目录或新执行授权**。不自动下载依赖、运行下一阶段或纳入尚未执行的 fixture/adapter/probe 候选。
