# hetero 16:33：编译 IR 前端与容量审计（INCOMPLETE）

## 实际工作与分层结果
- 远端基线 main 25889f2；原模型预算作业69954已终态超时，无重复慢跑。
- 实际 v2 原 Chisel 模型重新输出现代 CHIRRTL，17 native 声明与原始定义相同。固定4096 Matrix MAC未改变，未按profile重新生成硬件。
- 直接把旧 Scala low FIRRTL 交给现firtool被validif语法拒绝；未手工删除validif。改用原现代CHIRRTL入口后，完整 firtool --ir-hw 44.53秒 exit0，输出40,139,292字节HW IR。这只是前端编译证据，没有生成Verilog、没有Arc执行、没有数值PASS。
- 实际HW IR中保留107 sv.fatal、107 sv.error、1 sv.assert；独立小例也确认断言处于sv.always/ifdef结构。已读官方Arc StripSV实现存在删除相关结构的风险，跨版本兼容未证实，不能把该路线直接作为保留strict fatal的合格模型。
- 17 native 接入仍需显式保持独立实例状态、低电平求值、重复高电平、边沿与非零错误传播；官方clocked DPI示例不等价于现有分离drive/eval/clock/read ABI。

## 阻塞与下一步
- 当前缺匹配 arcilator/LLVM/runtime。官方firtool-1.163.0 full-shared Linux x64包143,163,743字节及digest已核；当前没有获准二进制取得路径，未通过代理/重包装绕行。需要正常授权传输官方包或已有匹配工具环境；包内Arc组件和运行库仍须验。
- 下一步先验证编译后端对真实fatal/clock/memory/native的等价性，再接原Host和真实输入；不先做长RTL调数值，不重复900秒解释器慢跑。
- 五块M128完整数值仍0/5：Qwen2原FP32 Norm已进入但未完成；0.8B L0保留原fatal失败，L3完整路径未通过；35B L0/L3真实权重取得和MoE契约仍有阻塞。旧16-lane结果不迁移至新32-lane方向。
- 没有完整block周期分母或RTL利用率实测，80%/90%目标未验证。

## 发布及清理边界
仅发布本摘要及哈希，不上传候选源码、原日志、权重或生成IR；不绕先前审查拒绝。本轮临时目录已清点，保留运行依赖和唯一证据，未清理。
