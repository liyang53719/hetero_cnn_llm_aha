# Qwen2 真实 M128 接入原 Host21 路径（TEMP）

## done
- 审计原 QwenBlockShape / QwenBlockLayout / HostBlockTopV4 / HostRuntimeLaunchV4：原 LegacyV0 存储FP32，矩阵在入口取BF16；Host V4需要 version=1/profileId=0。不能把旧Host launch的隐含零当有效版本。
- 原检查点投影权重为[N,K]，原Host Dense读[K,N]。新增 prepare_host_inputs.py，先核验全部13个真实FP32输入的SHA和大小，再按位转置7个矩阵、原样载入norm/bias/128个embedding行。实际运行已完成，所有矩阵转置可逆，187,977,728字节仅本地。
- 复用原 pack_owner_block_fixture.py 生成M128/21个Host操作的命令和descriptor，不新增ISA，不初始化n0/QKV或其它运算中间值。
- 新增 bind_real_bench.py，基于已有AXI内存bench替换synthetic初始化。只服务外部内存，不替硬件做运算。绑定VHostBlockTopV4、version1/profile0，并静态拒绝非4096MAC或BF16权重存储。保持原RoPE表生成及原LegacyV0算术，不引入新的FMA/近似/归约。
- 三项适配单测普通及-O通过：位转置/逆转置、错误字节拒绝、真实加载及4096/FP32硬约束检查。

## ongoing / INCOMPLETE
- 尚未对 host_real_inputs.cpp 完成当前V4生成RTL接口编译，也未启动完整Chisel/RTL数值。owner_shape_expected.h只是原几何输入，不是硬件发射证据。
- 继承bench的C++参考只作诊断，输出标签已更名；用户要求的独立Python完整参考尚未接入，不能当完整数值通过。
- 原top的实际固定配置/同五profile资源实例必须由父任务冻结，再将本输入绑定到那一个实例。此工作不按模型另行elaboration，不声称达成五块统一硬件。

## 下一步与预算
1. 用已冻结原HostBlockTopV4源和共用4096MAC配置编译本bench，保留当前LegacyV0。其它四profile不能借此通过。
2. 完成匹配实际顺序的独立Python完整参考与阶段输出比较，再运行完整原Chisel M128；未经前序模型验证不启动长RTL调数值。
3. 完整block有效MAC工作量为6,014,828,544；理想4096MAC供数下界1,468,464周期，仅架构下界。原bench保守watchdog为14,499,514,624周期，绝非预测或实测。必须校准短期吞吐再给完整作业墙钟预算，不沿用8M子链预算。

五块128仍0/5，无完整RTL或80%/90%利用率证据。未修改原n16下溢契约，无push。生成payload和命令二进制留本地，不入源码包。历史source recovery用于复用输入编码/bench；pin记录准确版本，不把其旧PASS继承为当前结果。
