# P0 执行前来源证据闭环：直接 producer/consumer 补丁候选

基线：实际已发布 `d4476f8e3fac9a28ea3f475e49f6b68abbac2dbd` Git 对象。`BASELINE_GIT_PINS.json` 为本次读取源码 pins；没有 checkout/改写旧工作树、已运行CI或旧证据。状态 **SOURCE_ONLY / INCOMPLETE，尚未运行新build/DUT**。

## 直接接线，不增加资格外壳
1. `ci_frontend_materialization_r2_20261029/materialize_frontend_binding.py` 将原 P0 `LOCKED_SOURCE_CONTRACT.json` 与实际已发布 `PROGRAM_MANIFEST.json` 纳入原 generation pin 集。原流水线目录中的新增采集源码同样由已有逐文件源pin机制覆盖；one_job明确要求两采集helper在原pins内。
2. `build_producer.run()` 在真实 `host_link` 之前只检查该driver的 `.o/.d` 必须不存在且非symlink，不误拒绝前三子块/host_archive合法生成的其他依赖。原bounded stage、工具、O0、make目标、supervisor不变。只有原native_exit=0/errors空/owned-cleanup完成之后才捕获真实`.d`文本、driver object pin、actual host/global/hierarchy make pins、实际host_link receipt与binary pin。
3. `pack_frozen_artifact.py` 在创建artifact目录前计算**真实 enriched_source 字节数**及原disk budget。只写NEW artifact source_manifest，保留原prebuild source文件/原hash/字段完全不变；继续原七文件白名单和buildreceipt绑定同binary/新source hash。source≤16MiB，driver-dependency metadata≤2MiB，buildreceipt≤64KiB。缺实际depfile/receipt或过大就停止pack，不回填历史run。
4. `p0_source_evidence.py` 保留实际overlay、compile155、original_high原文本/原pins，与上述实际driver编译记录一起嵌入NEW source manifest；不上传/编码weights、tensor、object或binary字节。
5. `connect_bundle.hydrate_p0()` 在原P0 provider完成后自动从共同artifact取原来源元数据，在本profile目录保存小证据文件，并将三项程序路径绑定**本次原provider生成的**manifest/commands/descriptors。不再要求用户手工拼12anchors；旧显式参数方式仍完整校验，不绕过共同source。
6. 原corrector.apply → 原attach → 完整load_binding保留。新consumer用实际GCC dependency selection取代旧same-directory限制；真正split-dir可凭实际编译证据准入。原20→18唯一delta、gate/up **REQUIRED_UNOBSERVED/INCOMPLETE**不改。P1–P4不能用P0例外。

## 实际 include/compile 证明的准确范围
官方Verilator5.032 `verilated.mk` SHA `74121398e5be12bf03721f1f0f5ce75e7c703635ec7e50920d43f9c4e31fcc0c` 提供 **-MMD，不是-MP**。现原host rule使用`-o driverstem.o`，因此捕获该obj目录下`driverstem.d`。
- 只接受ASCII安全路径/普通空白/LF续行、唯一GCC规则、target恰driverstem.o；禁止Unicode分隔、CR/NUL、其他反斜线、make变量/recipe/额外规则、`..`和alias重复。
- RHS必须包含实际driver且恰一个`sparse_write_memory.hpp`，所选路径和hash必须是锁定632…header；所有列出非system依赖均核原generation/derived pins。不是任意找一个正确hash的远端header，不从未列路径推断absence。
- 复核actualhost.mk唯一VM_USER_CLASSES、VK_USER_OBJS→host link目标与`$^`链接链，actualglobalmk精确hash，以及原hosthierarchy。按共同tool_manifest与实际hierarchy**精确重构全部原host_link argv**，拒绝额外VM_USER_OBJS/CXX/flags等覆盖。
- retained native receipt canonical hash必须等新buildreceipt的host_link supervisor hash；binary hash与common相同。
- 原fixed155推导的**同一producer repo路径**下必须具有本次已审build_producer/one_job/pack/enrich/dephelper精确源码pins；无关root的正确hash或旧producer附加新record不能代替。
- 这是“受信owning job实际执行已审采集代码 + 真实原生receipt + 保留依赖文本”的闭环；不是独立远程attestation，单独一张新增JSON不能追溯证明过去absence。旧run40862676969只有summary，不能补成这份新证据。
- -MMD仅覆盖实际非system include dependency。系统头/编译器仍靠原tool inventory；不把它宣传为所有系统依赖或数值资格。

## 12角色、程序与数值契约
7 Scala角色从原fixed155 overlay及compile/constructor真实argv交叉匹配；driver来自实际--exe；sparse来自实际GCC dependency。原PROGRAM_MANIFEST本身是原repo中实际pin过的runtime契约；commands/descriptors的hash与384/3456字节extent从其table_sha256/地址边界导出，明确标记 **RUNTIME_EXPECTATION_NOT_BUILD_INPUT**，绝不称其参与elaboration。原corrector仍读取并校验本次实际完整程序、形状、21commands/215descriptors及原输入views。
同4096 MAC/32lane/M128/同SV和binary，五组模型配置与独立reference不改；FP32/BF16顺序、原Torch routing baseline不改，小ID tie未批准；原Python算术/compare函数未修改。

## 资源、数据与尚未完成
EVIDENCE.json保留原64KiB上限，只存three receipts pins和单独DRIVER_DEPENDENCY.json pin；后者明确≤2MiB metadata，路径必须在本profile OUT。该拆分不是文本编码payload；里面仅make/dep/source/process元数据。原generation/source fullmanifest≤16MiB，上述费用计入pack实际字节。没有放宽8GiB acquisition gate、350min、20000s/profile、硬件规模或native资源。
此候选需要未来真正fresh build产生`.d/.o/receipts`；当前没有新实际编译/数值结果。完整五块DUT执行、时预算/速率/利用率与最终RTL仍待后续。没有启动重复build、DUT、Torch、下载或CI，没有push。所有已运行证据保持原样。

## 轻测与临时文件
`test_driver_dependency.py`使用真实已pin driver/header/globalmk字节但**mock compiler process/.d/object/ELF metadata**，覆盖split-dir正例、stale产品在stage前拒绝、native失败不得capture、metadata漂移、完整argv注入/工具角色、错误/无关root源码pins、make/dependency grammar、原source不变与runtime角色。
原portable连接tests和原完整70tensor/256experts/program/reference-routing metadata tests沿用，数值helper AST不变（coverage_policy只更新被审模块hash）。初次调用测试漏传独立driver fixture导致的FileNotFound日志已保留；重跑显式正确driver路径通过。`__pycache__`不纳入交付。未删除运行文件/用户输入/唯一证据。
