# 首次真实 Verilator normal_m1：限定时钟行为 PASS

**本次不是只有源码/编译/合成 mock 通过：**冻结的原 Core/PackedClient Verilated RTL 真正运行时钟，单个 `normal_m1` 在脚本化 Matrix / 外部 memory 端点下 PASS。模型 ELF 与先前 build 相同，未重编译/重生成/重试；本包不含 ELF、原始 log/events、模型 C++ bulk、输入或权重。

## 实际证据及层级

- 4939 body rising edges + 3 reset = **4942** 总上升沿。411 完整日志行：READY、408 OBS、CASE_PASS、DONE；12 heads 各16 Scan +16 Fold +1 Scale +1 Retire。独审一次完整解析，12次Retire scoreIndex/data均0；所有观测 token0/selected0/fault0/resultReady=false。
- 四请求口均有实际 payload hold recheck：group1、memory73、pv16、step23，合计113。此和可能跨口重叠且含release边沿，**不是113个唯一stall/idle周期**。
- 精确执行的冻结 harness 断言通过，支持1 owner、12 groups/results/dones、96 QK、96 PV、384 memory收发与6144 acknowledged output bytes；owner status0/resetRequired=false、8步payload持有和3步quiet。**独审未逐包重新播放所有memory/owner原始payload**，不是全部完成字段/中间tensor数值等价。
- 137前后pins、52缺席槽、6aliases与原owner清理闭环；129原build产物fullstat不变。CPU13.755799213s、outer wall13.863346743048169s、采样RSS高水位7,745,536B；RSS非连续峰值，host时间不是模型clock/硬件频率。

## max=-Inf 与占用比不能误读

全部408个pre-edge max诊断为 `0xff800000` (-Infinity)。原源码每head初始化max；harness在上升沿前发OBS，Retire时组合scoreWrite已有效而max寄存器仍是旧值；更新被源码安排到该边沿后，随即离开被记录phase。本次**没有直接观测post-retire max**，不能声称其最终0被测得，也不能把width-only诊断升级为全max/softmax数值验收。源定位及hash见MAX_DIAGNOSTIC_SOURCE。

`408/4939 = 8.2607815347%` 只为被记录ordered-vector控制phase的body占比；含reset为408/4942。其余4531 body edges**不能推成idle**。864 accounting仅接口记账，不是有效MAC数。没有真实4096-MAC分子/完整block周期分母，故90%目标既未证明达到，也不能用8.26%判失败。

## 不扩大通过范围

真实时钟行为PASS仍受原两态初始化（8250输入清零、randReset0、3 reset）及脚本端点限制；不声称与旧Treadle首次未初始化reset/物理上电逐bit相同。未证明完整Matrix FMA、非零/NaN/故障输入全覆盖、M2/M3或j1..7 W005、完整128 RTL/full29、硬件DDR/频率/时延/90%MAC利用率。原CPU600/150 FAIL、SV FAIL/STOP、预启动与reviewer-only纠错记录不变；整体任务和canonical todo/ongoing/done不升级。

## 最小复现材料

原log checker、原20项EventContract合成控制、harness与相关Scala/构建证据均通过精确公开refs复用。`test_frozen_log_contract.py`仅先核原源码hash，再运行原20项log控制及5项新诊断边界小合成；不读取真实日志或执行模型。它们是包装/格式验证，**不替代本次实际时钟行为证据**。

```
python3 -B candidates/qwen2_core_client_m1_actual/test_frozen_log_contract.py --repo-root .
python3 -B -O candidates/qwen2_core_client_m1_actual/test_frozen_log_contract.py --repo-root .
```

原私有监督脚本及完整配置只给hash、role argv/资源/有序pins，不冒充可直接执行的完整runtime。复现需按先前公开源码生成/build并独立核host依赖与runtime后另行准入；静态运行库声明不是dynamic loader/syscall全追踪。任何M2/新harness/后续工程都不在此实际PASS内。
