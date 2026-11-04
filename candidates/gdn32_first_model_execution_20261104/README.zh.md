# FIRST P1：一次完整模型构建与连续有限尝试

这是独立版本的原完整模型执行链。仅 P1（Qwen3.5-0.8B L0）作为首次执行对象；硬件仍统一注册五个 M128 block，162 Scala、4096 MAC、单32路 Bank、122 ports 不变。新 producer namespace 产生独立模型身份，旧153文件及旧执行路径不改。

材料、runtime、权重和原官方 reference 先完成，随后最多一次完整 Top 构建。若 reference 失败或剩余生命周期不足，不构建。没有已测新 SV rate 前置要求。此前92m17s历史成本只用于最低5537s构建窗口政策，不是新硬件预测。

原工作流第一步 monotonic clock 总限21000s。build cap=min(7200,floor(21000−elapsed−10470−3000−30−60))，不足5537拒绝；因此材料阶段最大elapsed为1903s。30s是构建前 census，60s是冻结后控制工作，不能互借或缩减10470尾。

构建成功后，单次冻结 W=min(7200,floor(21000−elapsed−10470−60))，不足3000拒绝DUT。控制工作必须在60s内到达numeric入口。W冻结后不扩时、不重新计算、不重启；consumer前以独占start文件领取一次执行。材料、原root、build admission、实际build result、derived controller的pins沿真实调用链传递，拒绝现场换hash自证。

完整尾10470s=四项host9000（1800后处理、1800证据、3600摘要、1800RSS）+ABI/init/provider/connect540+真实五次监督额外330+parent600。原资源门保持：初始13GiB memory和20,671,240,864B disk；后续各阶段原门及1.5GB监督运行floor保持，不将前置8GiB磁盘门说成全程8GiB保留。

一个连续DUT进程执行完整17commands/M128，保持原1e9cycle上限。pc6及进展仅表示进入chunk；pc>=7、completions>=7且未观察到reset才标 TARGET_REACHED_NOT_FULL。必要下界21,516,288cycles不是墙时预测。未命中目标为TARGET_NOT_REACHED；wall到期且未完整数值验收为INCOMPLETE/TIMEOUT。正常exit和目标命中均不代表FULL PASS。FULL仍须原所有输出/reference比较与cleanup/证据验证。跨五profile最终结论仍须全部真实结果和同实际SV hash。

本源码和纯回放不证明 native 编译、Top展开、DUT、数值、性能或最终RTL验收。生成仿真SV仅为模型测试后端；无DUT/SV/cache/artifact上传。唯一launch需父级发布、独审通过及真实资源门满足后执行。
