# Fixed93 PV16 归一化复用：核心 TEMP 补丁

仅供独立小提交/复核。当前包不含 observer 补丁，也不是完整 block 准入；旧调度 observer 不能直接接入。所有路径由复现者显式提供，没有工作区私有路径或隐式默认源。未包含基线副本、class、日志、权重或旧运行数据。

## 精确改动

- Scala 仅已有 enableProductionPackedQk16 路径：col=0 保留原 ScalarOp.Mul 与错误检查，成功后将原始 FP32 归一化值覆盖原 probs[key]，后七组复用。其他 profile 原分支不变。
- exp 与 normalize 两种互斥写状态使用唯一 probs.write 调用；唯一 probs.read 不变，不新增 SRAM 容量、寄存器声明、FMA/SFU/native profile。组合控制已变，不能声称零面积或物理端口已签核。
- Python col=0 乘法成功后原位更新 probabilities[key]，后七组直接读；report 明确 normalize=1/use=8/reuse=7、Scalar schedule changed。
- 不改每 key PV FMA 顺序、BF16 入口、finite 检查、Matrix/DDR 事务顺序或末次 ACK。事务等价条件是相同输入/按事务 identity 注入相同故障，不是绝对周期时序或完整 Scalar 调度等价。

## 检查单与证据边界

- [x] 核心 20 项 synthetic/source/FSM 检查 PASS，包含实际 Python owner/shared clients 的完整 synthetic M1/M2/M16、12 heads；数值服务是显式 exact-rational RNE 替身，不是 native 数值验收。
- [x] 旧/新所有 8 次实际 FP32/BF16 入口、每 key 中间 PV、输出、非 normalize Scalar 与 Matrix/DDR 事务序列等位。
- [x] 归一化次数 M1:96→12；M2:288→36；M16:13056→1632。软件 Scalar 周期被折叠，旧/新 ticks 相同不代表硬件结果。
- [x] 首列 Mul/V 读/写响应/nonfinite PV 故障，ACK/请求/结果背压，跨 head/query/job；独立 SRAM 模型含 token0/15/16/127、dirty future、不同 inverse、±0/subnormal/舍入边界。没有 M128 owner 执行。
- [x] 真实单文件增量 scalac PASS：19.63 秒，312324 KiB 峰值 RSS，16 class，87 jar/562依赖class逐项哈希核验；其他92份源码未重编译。
- [ ] 没有 elaboration、CHIRRTL/SV/RTL、物理 SRAM、EDA、真实 native、完整 M128/fullblock、有效 MAC 实测。
- [ ] 新 observer 必须以当前可运行的严格33-symbol helper基底重做身份闭包，不能覆盖成旧 _FuncPtr 故障版本；本包有意不收录旧 observer delta。
- [ ] 新 trace schema/event-v2、offline verifier、codec budget、constructor/dispatcher/identity 及新完整 source/native closure 尚未准入。

M128仅公式：normalize792576→99072，省693504次；无停顿源码模型每次少4状态拍，共2774016预测拍，不是硬件净周期。固定4096 MAC/cycle及完整block分母原则不变，不声称达到80%/90%。当前选中 fixed93 源码的供数/发射互斥下界 T>=5529600，逻辑有效 MAC=6014828544，因此条件上界仅26.5564236111%；这是保守源码界而非RTL实测，流水中已有工作可重叠，但新step与该Attention读写req/rsp不重叠。本复用不改变此约束，只删除冗余Scalar。独审结论摘要SHA：ace9361b80ddb5764fc5f5480242233d0bab44b494ad817f52a7cf0dc990d02e。

## 文件与复现

CORE_DELTA.patch 是两份核心文件的最小 unified diff；CORE_PINS.json 固定两份基线、六个只读 Python 依赖及两份输出 SHA。脚本先验 pins，然后仅在新的空工作目录临时物化两份小源并应用补丁，最终再验输出 pins。

    python -I -S -B tests/run_tests.py \
      --source-root <含candidates目录的原Python源码根> \
      --scala-baseline <选中旧Qwen2Block.scala文件> \
      --work-dir <新的空测试目录>

输出在指定工作目录 reports/test_result.json。CDLL加载被禁止，不导入torch/numpy、不下载/复制权重、不启动大DUT。缺输入/哈希不符/工作目录非空则失败，不寻私有备用路径。拒绝-O/-OO与未钉住的namespace初始化代码；依赖只从已验证源码字节载入，不读未钉住pyc，也不把外部源码根插入sys.path。

可选单文件编译复现（只在依赖齐备且获准时）：

    python -I -S -B compile/run_compile.py \
      --java <已匹配launcher> --jars-root <已匹配依赖jar树> \
      --classes-root <已匹配562个class树> \
      --candidate-source <测试目录内delta对应Qwen2Block.scala> \
      --work-dir <另一个新的空编译目录>

编译单CPU、768MiB heap、4GiB地址空间、90秒CPU/120秒wall封顶；不下载、不执行emitter、不扩预算/循环重试。compile/RESULT.json是相同源与相同输入pins的真实编译摘要；可移植编译wrapper只做语法审核，未再次执行，不能冒充第二次编译证据。

CORE_TEST_RESULT.json 和 PACKAGE_CHECKS.json记录从本包运行的实际验证。compile/INPUT_PINS.json只有相对依赖名与哈希，不含任何class或jar。
