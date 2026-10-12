# 公开 Command128 字节 → 完整 FFN 子图模型

此默认关闭候选将公开的 Dense20、Dense20、Activation35、Dense20 四条命令，接到既有 Host 控制、驻留协调器、同一 Matrix/共享 bank 模型和真实 act/prefix 写后读。它是独立 FFN4 子程序，从原 v0 完整软件图的 n1 开始；前置 Attention/Norm/residual 不在这四条命令内，不能声称完整 block。

## 输入 ABI 与来源

`fixture.py` 复用仓库 `Command128`、`DescriptorRecord`、tensor/shape/stride、MatrixAux 与 SfuProgram packer，生成4条命令和43条描述符。shape尾部填1；stride使用原公开 ABI 的元素单位。额外 metadata 位于独立只读区域，不复用 bias_index、workspace或私有opcode。fixture检查全部11个物理分配区间互斥，支持合法64-bit重定位，拒绝56-bit越界/溢出。

`model.py` 的 RecordReader 按真实64B地址读取公开128-bit字，检查表范围、tag、背压和错误锁定。typed reader按实际链逐次读取，检查dtype/rank/layout/stride、权限、完整padding跨度和policy。Host按需读取命令并保持原三命令预检、全program primary-root扫描、events/live/virtual状态；未知opcode仍先参与root扫描，在执行到达时由原正常入口拒绝。

launch仅快照config；表内容不被宣称全局immutable，也没有预解码命令表绕过真实读取。已捕获的三条组命令遵循现行生产源码锁存边界。workspace是第4个公开region，来自真实launch快照和epoch+1；身份标记不是跨reset checkpoint证明。

## 同一数值与控制链

`execute_numeric.py` 将实际 Host GroupRequest 对象交给原协调器，所有Gate/Up窗口、SiLU、act drain使用原helper。Down请求由公开第4条命令真实解码，经可选owner-edge回调推进同一个owner/bank；成功计数取自真实接受的终态和物理FMA观察，错误路径不伪造成功计数。

act只有真实写ACK后可由Down读取。三个原组completion在全部56窗口完成之后按顺序退休；Down末ACK和真实owner终态之后才允许第4个completion，最后返回整个FFN4程序result。backpressure期间event、live范围和结果保持。参考数组及phase10–13只在完整公开程序成功终态之后解码比较，不初始化中间结果。

普通Down的raw poison漏洞在实际 `ffn_group/group.patch` 的Host/Top默认关闭profile修复，runner原样传递consumer ready。成功线性化点是 `completion.fire`：未握手成功遇隔离不能发布；已接受成功不能被迟到poison追溯撤销。全局resetRequired没有epoch字段，后续launch隔离仍有效；普通明确error保持原status，已接受工作先排空。

## 证据层级

- 当前小门：公开字节31测试；实际小N160窗口、tiny Down与poison边界12测试；Host控制52、源码组合8测试。完整Host/kernel95个Scala源typecheck、6份有界CHIRRTL通过，default-off两IR与原版相同。
- 完整实值捕获以本目录独立source pins和receipt为准，不能继承812d858旧capture为新执行。
- Python控制模型与严格C++ FP32 FMA/原SiLU recipe是软件实现；不是直接执行Chisel，也没有生成RTL或运行硬件SFU。
- metadata按实际64B读次数计入流量；控制模型串行metadata调用不提供共享iDMA仲裁的硬件延迟。模型ticks/host运行秒数不用于硬件MAC利用率。
- 固定4096 MAC、32个1R1W bank、768 KiB SRAM和唯一16-lane SiLU不变。poison修复寄存器账不变；组合门控面积/时序未综合。
- 原完整M128 native/FP32-final FAIL、数值政策待定均保持。完整五block M128和冻结刺激硬件回放仍待完成。

CI只运行合成小门、来源校验及Chisel前端。权重、raw activations、NPZ、可执行文件、实际输出和生成IR不提交Git；需要的实际capture数据保留在任务工作目录，Git只保存脚本、来源pin及紧凑摘要。

## 两个新实际捕获终态

M16/M128分别304.597/437.927秒host wall，Gate/Up/act/Down全部逐bit等于独立固定算术与保存v0 producer。M128覆盖3,637,248个FP32元素、56窗口、112投影终态、56drain，act/Down分别4,587,520/786,432B全ACK后交付4个公开completion和1个最终result。两个case均实际读取87个64B metadata拍，共5,568B。

M128 payload流量98,041,856B，加入metadata为98,047,424B；仍是FFN子图的实际软件端口流量，不含整个block，不是测得DDR带宽。M128观察有用/物理主机FMA均5,284,823,040，M16有用660,602,880/物理5,284,823,040；硬件whole-wall利用率保持null。新公开Host逐边沿控制增加的是主机模型开销，不能用约305/438秒推断硬件时延。

来源与结果见 `numerical_receipt.json`。两次执行均绑定同48个严格源，原812d858旧capture没有重新绑定。源于prepare-only的venv分类失败及修复记录保留，未将其记为算术失败。
