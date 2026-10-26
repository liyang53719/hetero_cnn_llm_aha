# 统一共享资源 fabric：实际可生成，但产品 ABI 验收仍 FAIL

本包公开的是实际1020发射所用的旧版本3个新增 Scala 源，以及当时严格的 CHIRRTL/SV 小检查器和合成控制。其余6个增量 Scala 源、92个基线源、106个编译依赖与14个 provider 在 `SOURCE_ROLES.json` 按角色、字节数、SHA-256 绑定；不是完整自带工具链。没有模型权重、大中间张量、FIR/SV/class/tool binary。原 Scala/checkers/控制源码逐字不变；重复展开的1.87 MB SV期望由原小类型声明和原 flattener 加新包装 helper 精确重建，`COPY_IDENTITIES.json`/`PACKAGE_TRANSFORMS.json` 可核。新 helper 只构造声明元数据，不执行目标。

## 必须分层的实际结果

1. 原9源实际 typecheck 成功，得到68个新类568,515 B；与原557类隔离组合为625类。编译不代表硬件执行。此处原compile receipt与后续0955准入审内68类freshhash/SourceFile检查分层绑定，不冒称另有独立compile actual全审（见 COMPILE_EVIDENCE_QUALIFICATION.json）。
2. 原 CHIRRTL JVM发射 exit0，但初版 bulk连接方向检查器误拒 `mulPort`，原 FAIL 保留。后继 typed bulk 检查器只读同一8,865,236 B FIR，得到限定的声明/接口/图 PASS：212模块、211实例、4,616叶直通、46条有类型连接、clock/reset齐全。没有重新运行JVM。
3. 固定官方firtool1.62.1、仅 `disallowPackedArrays,disallowLocalVariables` 两官方lowering选项实际发射exit0，产生22,112,546 B SV。**严格产品ABI门FAIL**：独立 `UnifiedSharedResourceTop` 应有4,599口，实际只有4,597；缺少 `io_completeBlockImplemented`（output1bit）及 `io_result_bits_version`（output8bit），无extra/changed。它们被优化成产品内部和父collection的常量0/1；这不能替代独立产品物理接口。collection的4,618口完整也不能拿来冒充产品PASS。
4. 实际生成还记录了未处理 `DedupGroupAnnotation` 警告；不声称warning-free/all-annotations-consumed。资源/ROM/状态的诊断事实见 `ACTUAL_FACTS.json`，均不撤销上述ABI FAIL。

完整哈希和独审角色入口见 `EVIDENCE_ROLE_PINS.json`、`ACTUAL_FACTS.json`。独审全文不在本小包；这些固定哈希不是本摘要的新验收。后续1108 dontTouch修复、1117新compile及1127新CHIRRTL准备不在这套源码里，不能反向更新本FAIL。

## 同一硬件、同一接口的当前边界

产品固定为 `UnifiedSharedResourceTop`，collection仅做共同namespace：4个FMA兄弟是命名配套，不计入产品物理资源。选中产品的固定资源意图为唯一Matrix服务、8×512=4096 provider定义MAC槽、8 ICG、16-lane vector、一个Scalar服务和max32 state owner；不按五个profile复制五套算术阵列。外部provider在CHIRRTL/SV只是已核声明与接线，尚未取得完整provider前端/综合/数值资格。

所有五profile的控制接口/容量固定，profile只能运行时选择；**mode0完整block仍UNSUPPORTED**。当前单global resource lease是串行资源资格化，不能称最终Matrix/vector重叠调度、完整prefill128、五块数值通过或90%利用率。有效MAC利用率unknown。

Matrix错误为undrained+poison/resetRequired，state错误身份贡献ackBytes0/drainedfalse。DDR leaf的userTag32+perjob sequence32仍依exactly-once/no-stale外部传输契约，没有跨job epoch防重放；没有响应watchdog或无响应时有界完成保证。父调度器的真实drain/事务fence不可用host伪造完成替代。

## 仅运行本包小控制

在该目录下，用已选Python运行（这些命令只做小合成/15KB已固定片段验证，不启动JVM/EDA）：

```sh
# 在可写的新源码副本中生成；拒绝覆盖已有文件。
python -I -S -B checks/sv/reconstruct_expectation.py --output checks/sv/STRUCTURE_EXPECTATION.json
python -I -S -B checks/sv/test_reconstruct_expectation.py
python -I -S -B checks/chirrtl/test_check_chirrtl.py
python -I -S -B checks/chirrtl/test_passthrough_r2.py
python -I -S -B checks/sv/test_check_sv.py
```

亦可加`-O`复核。checkers是有界固定导出语法/声明/拓扑检查，不是通用FIRRTL/SV编译器、形式等价、行为仿真或综合工具。公开SV期望仍严格要求产品4,599口，因此原保留SV应继续FAIL，不得删除两口期望来制造通过。

真实重新compile/elaborate/SV/综合/回放必须另选固定工具、输入闭包、新输出根、独立资源门；本包不自动运行任何长工具。

原 CHIRRTL root wrapper 曾在 claim/Popen 前误读 FREEZE schema 而失败，修正后才启动唯一目标；旧记录保留。CHIRRTL/SV root launcher 均不声称预先自身hash绑定；SV 56端点/32缺失项为原source-bound expected+passed收据，无另存observed-hash map。原1052 pins/6 inventories是历史前后验证层，本包装不重哈希实际bulk。详见 ACTUAL_AUDIT_SCOPE.json。
