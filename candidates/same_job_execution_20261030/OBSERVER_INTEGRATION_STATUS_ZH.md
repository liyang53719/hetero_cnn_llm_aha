# 五块 M128 真实执行链整合：TEMP / INCOMPLETE

本次是源码接入与轻测，不是完整数值结果。五块新统一硬件 M128 完整数值仍0/5，最终冻结同刺激RTL回放0/5，有效MAC利用率未实测。完整4096 MAC保留；32 Vector lane结构不表示全链II=1已实现。

## 已完成源码接入

- 原155源选择精确覆盖8个已审 P0/MoE 观测源；所有profile共用一份硬件/driver/后端定义，未按模型重新elaboration。
- 实际 reference_job 调用的原run_reference路径接入官方forward的只读局部观察器；原PyTorch topk/权重/输入不改。
- numeric_tail → 原provider → connect_owned → consumer_owned → 外层真实cleanup/EOF → numeric result → flow → safe summary 完整接线。consumer不是祖先run_compare，也不再以写死INCOMPLETE替代必要比较项目。
- P0只把实际变化的6项源码/driver身份同步到独立来源合同；原输入/view/程序语义、20→18 DDR观测修正保留。metadata中gate/up仍是UNOBSERVED，只有后续真实SRAM观察receipt能补齐，绝不从source/helper测试继承PASS。
- 实际GCC depfile必须包含两个唯一、同driver目录、SHA精确的观测header，producer与consumer双向验证；不合成receipt。
- 35B runtime先安装，通过原strict cleanup后回调原build一次，再装其余eligible runtime；原caps/预算总期限不变。此顺序只有source/mock测试，未作实际新安装或import验证。

## 条件验收的精确范围

单块必须全128最终输出与完整KV或GDN history/state、P0 gate/up既定物化边界、MoE原路由IDs/权重/logits和实际selector完整观察，且真实终止、身份与外层cleanup/EOF均可验证。缺项INCOMPLETE；精确参考不符FAIL_EXACT_REFERENCE（仍需诊断硬件/参考/输入/顺序归因）；只有全部必要集合真实精确匹配才允许PASS_FULL128_EXACT_REFERENCE。五块全在且同源/硬件/后端身份才允许全五块资格。eligible4不能升为五块通过。

MoE FP32概率对Torch差异保留诊断，不新增容差或要求P7/stride8与Torch逐位相等。实际selector输入/输出同ID位传递一致性属于内部硬合同。NaN/Inf/负有限数阻止通过，-0保留；>1暂INCOMPLETE待既定舍入链归因，不擅设epsilon。原路由不同先保留原参考并诊断，不能注入官方ID或擅选小ID tie政策。

当前仍是BOUNDED_CALIBRATION，原300秒窗口/运输退出码2保持；真实数值资格单独绑定，CI退出码不能替代数值证据。FULL_BLOCK_ACCEPTANCE完整预算和新唯一launch仍待实际校准，不能把300秒诊断当完整任务完成。

## 尚未完成，禁止据此激活昂贵数值作业

1. 新实际HIGH/LOW的canonical descriptor、完整122端口及来源变化审核待完成。旧canonical typed-AST/annotation锁和85端口header合同未删除、未换成“接受任意当前输出”。
2. 新实际SV normalized identity/module fingerprints、真实Verilator header/ABI与共同RTL哈希尚未生成核验。新观测硬件不可继承旧ELF或旧16-lane结果。
3. IR-only descriptor仅提供新来源元数据，不是数值或SV验证。确认新描述符后还需有界的新SV/ABI资格，并据实际产物更新严格gate。
4. 后续上述build相关文件一旦修改，必须重算producer implementation pins、consumer dependency verifier、P0 source chain、connection pins和全SOURCE_PINS，不只改顶层摘要。
5. 本提交不含新activation文件，不启动/重试CI或EDA。源码资格通过后也必须另行唯一source→activation流程。

## 可复现轻测

在仓库根目录运行：

    python -B -m unittest discover -s candidates/same_job_execution_20261030/acceptance_tests -q
    python -O -B -m unittest discover -s candidates/same_job_execution_20261030/acceptance_tests -q
    python -B candidates/same_job_execution_20261030/test_common_observer_integration.py
    python -O -B candidates/same_job_execution_20261030/test_common_observer_integration.py

前者74项（51条验收/完整尺寸mock接线、9条独立safe-summary反例、14条runtime顺序/预算mock），后者8条源码闭包/真实路径/header依赖检查。全部为source/mock，未执行模型或硬件，不能计入五块数值PASS。
