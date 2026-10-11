# FP32 resident seed 真实 bank 读源候选

本增量将已验证的软件 C-prefix 地址映射落实为 Chisel 读源，并给现有
StreamingDense 提供默认关闭的同一读端口补丁。实际 Scala 编译和 CHIRRTL
展开通过；没有生成 SystemVerilog、执行硬件协议或 FPU，也没有启用生产
resident owner。原 M128 官方数值 FAIL 和政策待定状态保持。

`ResidentCSeedReader.scala` 使用 readEnable/bank/address/data 四个实际同步
SRAM 信号：t 拍发出的256-bit读在 t+1 采样，没有虚构可变延时响应、tag 或
第二读口。每个512-bit beat从同bank相邻两word读取，唯一payload寄存器512bit。
FP32有限值原位保留，包括正负零和subnormal；无效行/列显式补正零，完全padding
的beat不读哨兵。局部N48测试沿软件地址合同，未改变生产BF16要求N为32倍数。

`ResidentCSeedFrontend.scala` 将读源接到既有 seed controller，实例化16个
SyncReadMem(1024, UInt(256.W))，每bank只有一次read和一次write声明。它是
512KiB A/C部分的结构组合，256KiB B及真实leaf在范围外。此前SharedL2Fabric
的128-bit bank不是这个接口，不可只按名字互换。

## 实际生产读口补丁与尚缺的接线

`streaming_dense_read_hook.patch` 基于manifest固定的StreamingDense源码，
增加 enableResidentReadHook=false。开启时在原 aBanks.read 调用前选择地址，
复用原pending与operand FIFO；没有另增SRAM端口。默认A1376保留11-bit地址，
旧地址1024–1375不截断；不足1024word的配置明确拒绝启用。

Owner内部grant检查实际pending、operand FIFO、native A高半写、当拍A写和
未完成A DMA。pause阻止新读、新A请求及新job，已接受DMA及Matrix工作继续排空。
目前生产A/B仍为688/80KiB；这份补丁没有实施候选512/256KiB分区、C保存、
prefix/generation/lease表或Matrix leaf写入。不能把外部metadata/grant常置真
视为完整owner接通。

读源按真实owner metadata核验prefixK、ownerN、generation、slot/tile及lease，
绑定后变更shape/metadata/grant/drain会poison并隔离lease。中途失败停止读与
beat，未完成同步读不可复活；孤立reader reset不能代替owner/controller/array
协调reset。最后成功还要求同一ACK握手上的controller.committed，不能只看
ACK.error=false。这里completed只表示seed传输已提交；Matrix结果与Host成功
仍必须等待后续整个Matrix group的成功done。

## 已验证边界、周期与资源

21个软件source/control测试覆盖实际地址1023、上界/别名、有限位图/padding、
两次同步读、背压、早迟重复ACK、begin拒绝、abort、未完成读/reset与失败lease。
它们不执行Chisel。8个runner负测检查精确源集合、ABI、来源位置、每bank端口
与状态声明。实际编译分别使用原Dense和补丁后的Dense，默认大/小配置除源位置
外全量CHIRRTL逐字相同；enabled普通/burst-write配置展开，短bank配置拒绝。

第一次比较因3条自动assert诊断内源行号变化失败，差异已保全。修正只允许原/
候选中唯一、完全相同assert源码行所对应的行号映射，完整消息/条件/操作数仍
比较；复用原编译产物复核，不把原失败改写成第一次通过。

声明资源为reader720bit（512payload＋208控制）、读mux5bit、既有controller
138bit、组合前端legacyPending1bit，共864bit。实际hook复用原pending。
Decoder、bank选择mux、owner表、leaf控制、布线面积和时序尚未测；固定4096
MAC/拍分母不变。

局部无停顿模型：完整16×256传输256beats/512reads共1030拍；M3/N48为64beats/
18reads共152拍；额外40个offer停顿使完整case变1070拍，读数和payload不变。
实际源FSM为readLow→captureLow→captureHigh→offer，每个有效beat占4拍。
已封存M128的1,277,952次restore beat因此仅这一路径就需5,111,808拍，未计
acquire、leaf ACK、保存、计算、DMA或停顿；不是全层预测或RTL利用率。

此成本使下一步必须先比较固定资源下的转置/驻留布局，再选择生产实现。
不能将旧29.70%宽松上界称为该读源的可行性能，也不能承诺达到80%。

复现入口：

```sh
python -m unittest discover -s candidates/qwen2_resident_matrix -p 'test_*.py' -v
python -m unittest discover -s tests -p test_resident_seed_frontend.py -v
python scripts/check_resident_seed_frontend.py --repo . --out work/resident-source-frontend --cache work/matrix-interface-jars
```

[精确身份、声明和小门计数](../../reports/execution/QWEN2_RESIDENT_SEED_FRONTEND_20261011/SUMMARY.json)
不包含权重、原始激活或编译产物。最终RTL只在模型和接线闭环后用冻结激励回放。
