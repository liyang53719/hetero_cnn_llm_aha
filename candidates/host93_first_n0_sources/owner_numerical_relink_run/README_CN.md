# TEMP：Owner v4 Numerical 只读诊断的 driver-only 重链合同

本候选沿已审的 540 秒 driver-only caller，仅更新私有配置 pin 与 driver production manifest pin，entry 同步更新 caller pin。主函数和所有 helper 函数字节保持不变；reuse_gate、supervision、cache_gate、header_gate 四件与前版逐字节相同。PIN_UPDATE_PROJECTION.json 固定这两处主源码字面量替换及一处 entry pin，PROJECTION.json 仍可精确逆投影到原 cache caller。原 SOURCE 的 39×4 helper cold 只作为继承证据，本次增量测试单独记数。

## 固定输入与复用范围

v4 七件 production manifest 为 1020 B / 50ceabdd66b261e14084c2efe0609601b63d2724293ccd7a6f47531d6baebde0；owner_micro.cpp 为 437173 B / 7e6fe0d25ae744a408f1c47a5c43be61efb1069d2f7d75f5f0671ad83b2517af，其余六件与 v3 同字节。196 端口、95 原观察声明及 VLT 不变。新增 Numerical 只读 accessor 内嵌于 driver，精确额外成员/宽度/producer 资格由 v4 独立 SOURCE 审绑定当前 root header；旧 95 字段门并不代表全部 Numerical 闭包已被覆盖。

原 generated root header 固定为 4630258 B / a9371ed20684a6b5635de6203918cd33b910d856bd83618cf4a33c9dda398aaf。caller 继续使用已审同 buffer reader，并在原件、fresh 副本和后验中核验精确内容身份，不增加新 parser 或新的 RTL 生成。

已核的 owner compiled model 来自原 cache build，有限 actual 审 review_owner_cache_actual_20261019T2348：MANIFEST 786 B / 0a832dcb156af5f8df8620b2b43846dd0071bd36afdf42c0b9e3091a7fafbdcd，SUMMARY 9476 B / 14bb3cbebaa5002dad596c235db675cec66904a60e0ec8c8101d735ac853f1b1。原 runtime 失败保持。固定 12 输入共 24151608 B，即 2 generated headers、6 Verilator headers、3 runtime objects、1 普通非 thin owner archive。原 archive 内已含层级 child objects；不重做 generation/backend/model 编译，也不复用旧 driver object 或 executable。

原 608 项 compiled tree、原 generation tree、工具/39 系统依赖/readonly mount profile 及输入门照旧。在 fresh 输出只编译新 driver，再沿固定原顺序链接。新 .d 必须是固定 target 和恰好 12 个有序 fresh user inputs；新 object 的 relocatable ELF、新 executable 的 interpreter/needed libraries 及前后内容身份继续核验。没有 make、模型重生成或额外对象回退。

## 精确预算和失败保全

最早父 t0 起总 540 秒，含所有加载、hash、复制、预检、后验及落证。compile120 + link60 + run300 + tail60，各 native work/CPU 为105/45/285秒。每阶段开始及 preflight 后需保留完整当前窗口和尾限，否则 INCOMPLETE；不重新起总时钟。单 CPU、AS6GiB，原 MemAvailable≥8GiB / disk≥3GiB 每阶段重核。父普通 Python -I -S -B；530秒 TERM +5秒 KILL +5秒 parent receipt，父 outer 不使用 -O。

run 仍只接原强 hash 的 N0/Wq 两输入，500000 次局部循环上限及当前固定目标不变。新增只读扫描的实际耗时未知，300 秒窗口不保证到达目标。完整 bounded JSONL 原样保留，caller 不解释 Numerical candidate set、payload hash 或 status 布尔来授予通过；任何自然非零立即停止，首异常优先于 secondary log/save/restore 错误。

## 验证和资格

COLD_RESULT.json 只记录本次 pin-only 增量冷测，旧39×4不合并计数。READONLY_REUSE_RESULT.json 逐字节继承前版已审只读库存回放，未在本次重新执行；其中95声明与旧 .d 的明确路径投影不是新增 Numerical 覆盖，也不是本次新编译器 .d。实际执行仍由入口重新核验对应固定原件。

当前候选实际未执行。已有 session92317 的 RESET_REQUIRED_SETTLED/Numerical 类别失败与旧 v2 早期失败均完整保留；本后继不预授具体首写、Host 同因、完整 job、全 block 或数值正确性。full_job/full_block=false，official/application/typed-to-RTL/historical-host-reproduction 维持 null。私有绑定、COMMAND、outer、机器路径、数组、对象及完整日志不公开。

## v4 独立 SOURCE 身份

review_owner_micro_core_v4_20261020T0031：MANIFEST.json 2326 B / 0a21394bd641a78cd6e07831873e199669f81bd9c2068115abab04db97f58984；SUMMARY.md 4320 B / 1eee1058e4e64039525f9364b9ea8ed5e158843612b0f32e36057d83c096d50a；GO_OWNER_MICRO_V4_NUMERICAL_CONSUMPTION_OBSERVER_SOURCE_ONLY。该审明确核验69个 scalar、4096个有序 result 别名、16个 tile words、6个 burst ports，共4187叶，对应固定 generated root 与实际消费者；此为额外只读源码资格，不是本后继的实际运行证据。
