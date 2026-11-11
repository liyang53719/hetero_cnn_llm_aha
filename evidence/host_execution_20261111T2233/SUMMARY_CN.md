# 22:33 活动phase诊断候选与Host接线类型检查

## 实际完成
在未改原status/ready/poison/reset优先级的11bit诊断候选上，重新构建原Guard/候选双实例真实Chisel→HWIR→LLVM→机器码，session14457 exit0。25项活动phase场景原输出每个前后边沿一致：先postnorm退休，再reserve1289，Dense phase tag1实际phaseDone，4种status×5种覆盖条件，加错误allocation/range/tag/context和reserve1288拒绝。三拍背压、消费失效及reset检查通过。authority由合成单测驱动，不是完整Host元数据读取或MoE链资格。首轮driver回复tag仍0导致FAIL，修driver为tag1后通过，原失败证据保留，未改Guard规避。

独立审查11项源码关系：三phase helper要求原Guard具体类型，单换候选构造器不可行。实际在独立源目录保留原Guard类名，加Top三个只读内部WireDefault/dontTouch诊断信号，公共Top IO不变；Guard、Top和三个helper共五源对重新核验的860旧class进行类型编译。session99620 exit0/9.08秒，生成21class。不是全155源重编，不是完整Host elaboration/执行；Arc中dontTouch保留及可读取布局仍待验证。原共享源/Host二进制未改。mask仅采样authority/global/历史poison聚合输入，不是完整根因，不能以此把Protocol7改成Numerical8或放宽安全隔离。

## 输入与五块128状态
Qwen2：新1833绑定13份真实FP32输入187977728B重新匹配，62个tensor前缀及21-op依赖检查通过；独立全21参考70条目307063373B及13项负例重核通过。Host/native/layout哈希与三个项目动态依赖现存；未dlopen执行，非hermetic运行保证，未重算参考或启动完整profile。新程序身份不冒旧刺激。
0.8B L0/L3：14/11原张量、27桥段与命令/descriptor匹配，但原hidden仍缺，L3旧hidden身份缺独立证据。新增28份允许源码无对应生成者，没有猜seed。
35B L0/L3：18/15完整payload仍缺，未重试受限下载。
完整原Chisel数值仍0/5；原L0 head4 underflow FAIL、RMS预期顶层8的FAIL保留。最终同刺激RTL未通过，4096完整block有效MAC80/90%未实测。未改变精度或Matrix资源。局部诊断PASS不迁移成五块PASS。

## TODO / 阻塞
下一步验证独立Host诊断接线的完整elaboration和Arc保留/可见性，然后有限边界对照；仍不替代完整prefill主线。未知旧Qwen2/L3任务终态和并发启动边界待定，不重复启动。0.8B缺原hidden，35B访问限制未解除；不继承遗失PASS、不绕过之前的发布拒绝。

## 身份、CI、清理
开工远端main f32a2c887a86cbba31665c713a56faca45c3b712；CI43105482299 success，仅payload guard。较旧43097456849仍queued，未重复触发。工作树旧54776eab干净，可用内存约9.1GiB/磁盘56GiB。临时清单已核（本轮全cwd枚举，非前轮局部口径，不能以条目差推断新增数据），既有数据清理0。14457与99620均终态，无新完整profile任务。只发布允许摘要/hash，不上传源码、原始日志、权重或中间输出。
