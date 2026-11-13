# 20:33 L3 双参考完成最终输出与真实恢复包离线准入（INCOMPLETE）

基线 main 7fe62ecce5dcf34580c9404ed89741a76ad80290，CI43494631939 success，仅 Git payload guard。现场未回退、工作树clean，磁盘余54GB。临时清单已检查，清理0，保留运行引用、输入及唯一证据。

L3独立Python双参考完成SiLU→up乘法→down→最终残差。每分支down M128×K3584×N1024，469762048有序FMA，10752个Fraction完整dot节点交叉核验；SiLU保持FP32 sigmoid×gate后BF16，再与up相乘后BF16。最终M128×1024中347个BF16不同，首处token39/channel0：项目升序0xbde2，pair候选0xbde0；最大绝对差0.00390625，RMS差4.82738e-5。这是两个项目算术契约之间的差异，不是对官方PyTorch的精度结论，更不是硬件通过。冻结升序参考未被替换。

已核模型revision 2fc06364715b967f1860aea9cf38778875588b17、模型源码revision 14e738b5d0cc69aa27a95dde272aea41fde44f2f；配置标记Transformers4.57.0.dev0不等于当前已执行框架版本。历史lock中的torch2.10.0+cpu本轮未执行。本轮Python3.12.14/NumPy2.3.5，以Fraction和TwoSum精确域顺序实现，不执行torch/BLAS matmul。不能把升序称唯一官方归约顺序。

真实20块checkpoint离线validator接入1933 controller.validate：核runtime/输入pins、Host低相及大小、cycle/control/runstate与245760B真实ACK参考；4组测试、9个语义拒绝案例通过。未创建native句柄、未反序列化native或运行Host。原29364仍Unknown且缺终态receipt，不据本地ps空或心跳旧而重启；最新完整包仍cycle468445，40/128首RMS行0差异，不能冒完整RMS通过。

五块完整原Chisel M128仍0/5。Qwen2首RMS部分；0.8B L3独立参考已到最终输出、硬件未完成；0.8B L0原underflow FAIL保留；35B L0/L3缺真实权重。完整RTL数值及完整block有效MAC利用率未测。4096硬件不缩减，候选隔离、不复用旧checkpoint身份。源码/生成数据仅本地；本提交仅允许摘要。

补充实测：原fromOwner映射小模块实际Chisel→SV→Verilator，1536向量（Q8/Q16×256 policy×3 kind）通过；完整8位order/地址/tag/shape保留，坏值并非在mapper拒绝，不能冒Commands→lease→router真实准入全链。完整链仍需真实前序ACK provenance，未注入伪造记录。此测试发射RTL，仅局部映射资格，不是原模型五块数值PASS。

完整分阶段L3双参考已重hash56个阶段文件并核串联；我复跑audit及4组真实包validator均通过。初始RMS采用双NumPy原序遍历与Fraction sqrt/div，其余逐阶段Fraction/TwoSum范围保留，不称全链全Fraction。最终旧输出SHA32f887de458dd8c7ac2dfdc6060dd4d39764c87be3fa9e4c7b05e2b57667f8ff，pair候选2e78c98a9ade02fd4a62adc2af9c7a2be75c1fbc97e278664a253c69f930e39a。
