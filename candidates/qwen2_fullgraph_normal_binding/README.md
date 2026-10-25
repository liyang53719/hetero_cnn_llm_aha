# 完整 fullgraph 正常 source binding：PASS，数值仍 TEMP

**有效终态：唯一 r2 cold 正常加载15个 runtime roles，完成9个真实服务方法严格代码绑定，exit 0、无超时且进程组已清理。仅正常加载/绑定 PASS；未构造任务服务、未运行 Matrix/完整 block 数值。**

父提交：`5e703311d62ab05ae7679d17d7ba101c1e201525`，精确复用其中37文件的冻结源码身份。

本片只修复上一准备片的正常 import 闭包，不执行完整 block、Attention 或原生 Matrix 任务。旧 fullgraph-entry 的 v2/v3 FAIL、源代码与账本均不修改；控制测试 PASS 也不被改写成数值 PASS。

## 最小变化

复用现有 PyYAML 6.0.3 的完整 17 Python 源和一个 CPython 3.12 扩展 ELF，逐项核安装 RECORD 与复制后 SHA。只建立 yaml 包自己的独立依赖目录，不放行整个 site-packages，不删 cyaml，不预加载 yaml，不强制纯 Python 替代路径。

新的适配器复用冻结 fullgraph-entry 的正常 source loader、任务禁门、模块/映射审计与九方法 binder。显式证明 PyYAML 正常初始化实际加载 yaml._yaml，防止静默 pure-Python fallback 被误认作完整闭包。

正常依赖初始化可能加载 NumPy/BLAS/PyYAML 扩展，也保留其原初始化自检；这不是“完全没有 native 库加载”。禁止的是 custom Matrix ELF、任务服务/owner/Observation 构造、reset/job/任务算术、用户 tensor 读取，以及编译或 RTL。

## 范围与剩余资格

完整 fixture 的静态 transitive 闭包涉及 18 个项目源码文件，第三方依赖仅 NumPy 与 PyYAML。原样保留精确 source/code、namespace、每个实际 module 和映射的身份审计，完整库存先落盘，再验收。

运行结果另见 validation。即使正常加载与九方法绑定成功，也只升级这一层资格，不证明 pc12 实际执行、observer 无干扰、全程 ACK/abort、完整 M16 oracle、完整29节点或数值结果。4096 MAC 分母不变，legacy PV 完整 block 上界仍为 63.57%，无 80%/90% 或 RTL/时序证明。

本片不附输入张量、ELF、私有 raw maps 或本机绝对路径配置。跨环境复现须重新核同源依赖、生成精确配置并独审，不能改旧 pins 放行。

## 首次补片 FAIL 与独立 r2 后像

第一次已真实加载 15 个 runtime roles 并完成九方法绑定，但 adapter 的存证代码把 Cython metatype 的 getset_descriptor 当作字符串处理，导致新 raw inventory 与最终 adapter receipt 未生成；整体保持 FAIL，原 source/config/日志不变。

r2 同时审查全部同类字段：不求值 C type、函数的名字/module/globals descriptor，不对未知对象调用 str/repr/getattr。先完整记录原 module 字典成员名、object/type IDs 与已知 builtin 类别，再做资格检查，失败也保留记录。

新资格仍检查精确 extension event/loader/map、当前 canonical 模块，以及实际 extension 字典导出对象到共享 cyfunction type/metatype 的身份关系；不再声称观察函数内部 globals 指针或 C 内部创建调用。这是明确限定的依赖初始化来源关联，不是放宽任意 no-file 模块。

## 实际验收口径

新 adapter 结论为 `PASS_NORMAL_FULLGRAPH_BINDING_ONLY`。原冻结 wrapper 的 `FAIL_NORMAL_BINDING` 文件原样保留，其中最终仅剩两项预期的 Cython 无独立文件模块身份差额；本片以明确限定的对象/扩展来源关联给出独立资格结论，不把旧审计文件改成 PASS，也不忽略其他错误。

68项纯测试在 normal、-O、-I、-I-O 四模式通过。实际 r2 cold 只执行一次，原预算1CPU/256MiB/20CPU秒/25wall秒；实测5.131606597977225秒。依赖初始化确实加载了扩展库，custom Matrix ELF 未加载。完整module/maps/safe对象库存、原始报告、父子身份与退出记录均保留在本地，公开仅相对身份与脱敏摘要。

## 复现前置与边界

纯测试 `test_dependency.py`、`test_initialization.py`、`test_safe_metadata.py` 可在独立Python子进程中运行，不导入PyYAML或DUT。`test_preparation.py --config <exact-local-config>` 另需精确的316-source闭包、旧审计helper、已有依赖与本机路径配置。

`dependency.copy_existing` 只从已存在且匹配RECORD的安装复制精确18文件到新目录，不下载/安装。正常cold的 `launch.py` 仅接受已独审精确配置SHA；该唯一attempt已消费。迁移或复现实验须新配置与独审，不可改旧pins或把本片当额外数值启动授权。公开projection不包含本机绝对路径配置，因此不声称任意干净checkout可直接运行同一cold。
