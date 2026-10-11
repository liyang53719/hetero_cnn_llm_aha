# Qwen2 M128 转置 Dense：既有 Matrix service 的源码接线

此候选把已完成软件全图验证的 M128×N32 映射接入现有
`MatrixPipelineService` 的八个 retained endpoint。生产文件暂未替换，构造参数
`enableTransposedDense` 默认关闭；不是新的算术阵列，也不是完整 owner/Host 验收。

## 数据与生命周期

现有 step 的 `a[0..15]` 携带 N0..15 权重；`b[0..127]` 携带 M0..127 激活，
`b[128..143]` 携带 N16..31 权重。剩余 b 槽在该模式不消费。前四个 slice 沿用
原路由，后四个选择第二组权重和对应激活。每拍全部4096个 FMA 的物理编号和
输出布局不变，K顺序、FP32累加及 BF16 舍入没有修改。

模式随 `group.fire` 锁入既有 group 寄存器，live command 引脚变化不会改变
在途路由。转置模式只接受 Dense opcode 0x20、sliceMask 0xff；非法组合在
进入 command 状态前拒绝。关闭模式仍用原准入规则。既有 FSM reset 回到 idle；
group 寄存器本身未变成 reset 寄存器，下一次接受覆盖后才能发 step。

两种补丁均保留：`transposed_mode.patch` 接在已固定 return-tag 补丁后；
`combined_service.patch` 可直接作用于 manifest 指定的原生产提交。
manifest 核验每个原文件、两次 postimage、补丁、测试、runner、ABI 和 Maven lock，
禁止缺件、多件、路径逃逸及字节漂移。旧候选和旧 PASS 没有重绑定。

## 已执行的检查

在冻结 work runner 上真实 Scala 编译4.897秒、CHIRRTL展开4.330秒；20个生成
文件均保留hash。默认关闭的六组对照与已验原接口前端仅移除来源位置后逐字相同。
tag宽度0/1/16/32、启用/关闭及固定模式构造均已展开。

单module、拒绝未知表达式/重复driver的检查器沿真实 CHIRRTL 操作数连接求值，
比较2,064,384个物理 operand-pair 坐标，含特殊原始位图、两种模式和接受后的
live-mode扰动。Python另覆盖65536个opcode/mask组合、背压、五contexts、
tag、abort/reset等抽象控制；这不是 Chisel 时钟协议仿真或 FPU 算术执行。
发布包装修复临时目录和外部baseline路径后重新做轻量测试/身份验证，并对原
20份IR重新检查；没有用包装后的源码身份冒充原编译执行。

新增资源账：1个被接受的 group 位，源码共享的2304个二选一 bit mux
（不考虑共享时上界3072），以及准入比较逻辑；没有新增操作数buffer。
八endpoint、八clock gate、4096FMA、五contexts、8深度metadata和2深度result
FIFO保持。mux数量是源码结构计数，面积、时序和实际功耗未测。

## 复现与准入范围

先按既有 `scripts/check_matrix_interface_candidate.py` 生成原接口前端证据与
已锁87依赖cache，再调用：

```sh
python -m unittest discover -s candidates/qwen2_resident_matrix/transposed_route -p 'test_*.py' -v
python scripts/check_transposed_matrix_frontend.py --repo . \
  --out work/new-transposed-frontend --cache work/matrix-interface-jars \
  --baseline work/matrix-interface-frontend
```

`--validate-only` 仅核验来源、patch、ABI、cache和旧IR身份，不编译。输出必须是
新目录；失败证据保留。完整命令只编译/展开 Chisel frontend，不执行 firtool、
SystemVerilog、Verilator或 retained arithmetic。CI在同一job先生成baseline，
再复用其精确身份，避免独立重复baseline构建；新精确提交的结果需另验。

## 下一项真实集成

1. 实际 A/B bank 读口和 gather：绑定已选bank公式、同步延迟、read lease、
   ready/valid与abort排空；两个weight组和128激活必须来自实际bank写回。
2. 接 StreamingDense owner 的 M128生命周期、物理输出gather和最终write ACK。
   现行owner的M16布局不会因本补丁自动变为M128。
3. down prefix 的真实DDR→FP32 seed→leaf恢复、FFN保留A/三槽及共享端口仲裁，
   接同一Host入口并验证失败不发布。单Scalar和DDR全周期仍须计入。
4. 模型级cold/carried与官方数值政策闭合后，冻结刺激执行最终完整硬件验收。

原 M128 native/FP32-final FAIL、数值政策待决定保持。软件全图的131727360B、
理想交通上界71.3456%不是本前端门的周期或实测利用率，也未达到80%目标。
完整block、carried prefill及更长序列门均未由此关闭。
