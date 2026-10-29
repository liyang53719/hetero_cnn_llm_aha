# Same-job 原物料链→V3：冻结版独立只读复审

**结论：在观察门、原物料接线及startup ABI调用接线范围，未发现剩余新的具体绕过。当前P0真实producer仍BLOCKED；startup ABI仅启动期身份范围，不能升级为DUT/全block/最终RTL数值通过。**

## 最终冻结身份

候选：`same_job_materialization_candidate_20261029T1231/`

- manifest：`c7d97d4fbf5e64065f9ba90f56f51095becc05f19788c9efcae113d08c64ee72`
- prepare：`b168d9fb931e9572c645ccccab32da264f10aec9e04de8c5a9bc2f72b56bea1f`
- connect：`d911f8bf7da9c3ed725951555816fb4fd080d8396042124da360d08d024b4bcf`
- consumer：`a98b10fa086da81929a64aeae51c1fb61a1e799d4d2d0180bbf54ed5e4135b50`
- ABI模块：`f6826a38f3d479b18a45f8bd2d80ff20a7eb2c77ba1783f77a5abf612308632c`

最终manifest全部条目及CONNECTION_SOURCE_PINS核验，详见EVIDENCE。此前未冻结快照审查在 `same_job_materialization_review_20261029T1242/`，manifest `d72aa7a29cd10e0164189f17fb9eeaf2bfc64441336ddd63557d049834c6faac`；它的ABI占位状态仅属历史，不覆盖最终模块。

## 已核逻辑

1. **原物料无偷换。** prepare全部非main函数AST与原0403 materializer完全相同；main `:109–115`仅加preflight和connect。原reference/provider/program/权重获取和Torch路由baseline不改。P1–P4深复制V1升V3，原profile pins/limits/V1文件保留，不使用P0观察豁免（connector`:14–19,44–49,91`）。
2. **实际前置拒绝。** connector`:70–100`在runtime/权重准备前核common5/tool pins、原driver、build receipt关系、layer/MoE/4096/32、owning-job身份、ABI。P1–P4错误P0参数及同长度SV/driver/source漂移的早期拒绝已独立重现；缺P0mapping在prep前拒绝。preflight不宣称完整P0 R3来源准入。
3. **P0观察门仍强制。** connector`:30–43`实际调用固定corrector.apply及原attach，`:50–56`完整consumer.load_binding过后才no-clobber发布V3。锁定R3仍核12锚、原20→18唯一delta、实际来源receipt/header合同；gate/up保持required=true、UNOBSERVED、INCOMPLETE、numeric_pass=false。无零填、reference填充、借别处DDR或官方ID注入。
4. **local proof不冒认证。** local_build_proof `:1–3,13–31`明确一致性范围；独立expected SHA/run/source/launch应来自真实owning workflow。核同输出树returned manifest、七文件及大小，再沿原common/build receipt pins。不使用假GitHub API/下载凭证，不从历史公共summary恢复binary。它不能认证任意自填本地文件，外层真实producer信任不能省略。
5. **startup ABI真正接线。** consumer`:218–232`先核固定ABI源码SHA，传共同binary/tool pins和独立ABI receipt/hash给verify。若有V3 bundle，里面复制receipt path/hash必须与CLI一致；connector`:46–49`只复制已核receipt不重写内容。
   - consumer`:250–252`在validate-only返回前调用；`:296–305`在每次execute前后重验。
   - execute`:115`只新增`env=runtime_abi_module().clean_env()`；其余原execute AST不变，原timeouts/resources/group cleanup保留。
   - ABI `clean_env :14`给固定最小环境，不继承LD_*或GLIBC_TUNABLES。物料接线只调用`verify`，**不会调用ABI prepare/_list或启动loader**。
   - ABI `:71,77,83`保持`later_dlopen=NOT_QUALIFIED`及`PASS_STARTUP_ABI_IDENTITY_ONLY`；不是所有运行时动态加载完备证明。
6. **结果不升格。** consumer`:291–305,325–330`保留顶层INCOMPLETE、独立coverage_policy及原严格bitwise诊断；没有新增容差/浮点次序/FMA变换/数值PASS。

## 独立证据

本目录正常/`python -O`各 **41 test methods** 通过：
- `TEST_ALL_NORMAL.log` / `TEST_ALL_OPTIMIZED.log`：候选33项（14连接 + 6原物料 + 13 ABI parser/mock-receipt）。
- `TEST_P0_NORMAL.log` / `TEST_P0_OPTIMIZED.log`：额外3项完整P0 metadata-only连接。真实锁定小源码/TSV/程序，加明确mock producer/process/reference/ABI。正例完整load_binding后依然18观察+两门INCOMPLETE；split-header和错program不得发布最终V3，原V1不变。
- `TEST_ABI_WIRING_NORMAL.log` / `TEST_ABI_WIRING_OPTIMIZED.log`：额外5项独立ABI调用接线。真实consumer.verify_runtime_abi，**仅ABI verify函数体替身**；核参数传递、bundle换receipt/漏receipt拒绝、ABI失败传播，以及validate-only前/进程前后和clean_env AST。
- `PHASE_NORMAL.log` / `PHASE_OPTIMIZED.log`：4组独立前置拒绝重现（P1误带P0字段、SV/driver/source同长度漂移），均preflight拒绝、无最终V3。

所有测试均无真实loader/DUT/编译/Torch/下载/网络。ABI测试的_list或Popen均显式mock；ELF parser只读小型合成fixture。物料测试真实子进程替身，不读取大型权重或参考tensor。≤256MiB AS，无bytecode写入候选。

## 保持阻断及最小后续

- **P0 actual shared source/program mapping、retained compile/constructor证据仍未具备；真实split-driver/header布局不满足R3 same-directory合同。** 不得以本测试正例豁免，不只跑P1–4冒全五通过。
- preflight只核P0mapping存在；完整程序/role/header/delta门在connect。分目录header可在prep后被R3拒绝，但不能到DUT或最终准入V3。未来可优化可前置检查，不得补造证据或改变验收。
- 真正startup ABI receipt须由同一已核owning producer和已pin系统loader产生。本次没有生成真实receipt/运行loader，也不证明未来环境或later dlopen。
- 同job原生build后的一次受控runtime/reference/provider/DUT端到端还未执行；保持原20000s/profile等limits，外层严格supervisor/预算与剩余时间admission另行负责。
- 隐藏gate数值覆盖、原Torch FP32/超越函数等价、MoE tie、全block Chisel/最终RTL验收均未新增。

本次不修改候选、已激活CI、原冻结runtime/config、硬件、reference/comparer/tolerance；只读复审与NEW局部metadata测试。所有旧冻结包及原2330输入重核保持不变。
