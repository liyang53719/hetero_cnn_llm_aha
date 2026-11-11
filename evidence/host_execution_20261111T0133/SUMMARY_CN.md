# 01:33 原 Host 真实 Dense 续跑：INCOMPLETE

## 实际代码及验证
本轮在独立副本新增有界安全帧等待：达到目标周期后，仅在原守卫和更窄空 AXI 条件满足时保存，窗口耗尽则失败。不改变 Host、17 native、固定4096 MAC、精度、异常或状态格式。旧21组件/11文件闭包先完整校验，旧状态 pin 保留；新 driver/runner 执行身份单独记录，没有暗改旧 checkpoint。

旧/新driver真实Dense中态264704→264896：576帧输入/输出/完整1624112B core及21终态组件完全相同。真实不安全目标265088等待3周期到265091，与原精确切点control的1161帧和21组件相同；1周期窗口正确拒绝且无manifest。10项非法参数在step前拒绝且状态不变。独立审查通过。以上仅恢复/执行适配资格，不是完整Dense数值。

## 实际续跑
唯一原worker session96954，driver PID7/start8790806，从真实Dense active264896恢复，目标364896、最多额外等待10000周期、600秒外限。没有重算首Norm。原会话已exit0，259.68秒；最终active364899（目标后等3周期）、Matrix issues21760、pc1/completed1。完整21组件事务保存并重新验证，manifest 703183ab895ff411ebcb9f089d955b7ee279cf447b72f2762edb34036ace7e66。没有再开长段。

新增部分Dense数值：依据真实写回validmask，q已写81920个BF16元素与独立M128×4096参考逐位一致，442368未写元素明确不比较；零差异。DDR总写回425984B，本段新增Dense163840B。此为已提交元素的部分数值PASS，不是完整q或Dense算子PASS。

## 五块128 token状态
Qwen2、0.8B L0/L3输入与真实训练权重重新hash通过；新缺失即FAIL脚本8项测试普通/-O各通过。35B L0/L3分别仍缺18/15个完整张量，各64MiB partial拒绝，不把header几何资格冒权重/数值。L0输入保留原synthetic dyadic M128及cold state，原head4 fatal underflow FAIL不解除。

五块完整数值仍0/5。已通过的L3首Norm只有128×1024 BF16；Dense未完成。无最终RTL数值或完整block有效MAC利用率实测，80%/90%目标未通过。

## 身份、CI及清理
开始时main f54fa347与CI42937218858 completed/success已核；CI仅禁止重建数据入库检查，不是数值回归。全round递归临时清单42668项约10.7GB，与先前940项不是相同统计范围；未删除任何数据。旧日志、失败、唯一checkpoint保留。仅发布允许的中文摘要和哈希，不上传候选源码、原日志、checkpoint或权重。

## 后续
原身份核续段终态、完整21组件manifest与闭包；继续从新已验证checkpoint按安全帧有界运行，阶段完成后比较完整输出。按有界安全段继续原完整链，不重复短前缀。

独立复核直接解析driver.bin的sparse validmask、seal和21组件，不依赖首次出现0B的结果JSON；重新持久化证据 SEGMENT_PARTIAL_RESULT.json 已确认非空。参考SHA ea5a74825cdf0e9ddadf48f251ed551bd9508bd0b9bf0620ac67563d32328336，无仅单byte有效的BF16元素。
