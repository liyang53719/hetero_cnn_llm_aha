# 完整 FFN 驻留组到 Down 的实值软件模型

本增量把已经提交的 `ffn_group` 协调模型、`ffn_drain` owner/共享 bank、原 Matrix 与 SiLU C++ recipe 接到同一条真实数据依赖上：冻结 n1 + 官方 Gate/Up/Down 权重 → 56 个 N160 窗口 → act DDR 实际 ACK → 同一个 owner 的完整 Down。代码没有修改旧模型或数值政策。

这是 Python 端口/控制模型与严格 FP32 主机算术执行。它不执行 Chisel、公开 descriptor parser、真实 iDMA 或 RTL；模型 tick 不代表硬件周期。完整 block 的输入/后置归一化、Attention、residual 不在这条链中。原 M128 native 和 FP32-final FAIL、数值政策待定保持。

## 数据和生命周期

- M128×K1536 的输入只在第一个 Gate 加载一次。其后 Gate 和全部 Up 在同一低 A bank 区复用；56 窗使用真实 ng 与全 N8960 权重/输出 stride，非重新初始化的独立窗口。
- 每次接受的 Matrix packet 驱动原逐 K BF16×BF16→FP32 FMA，结果经原 finalValue/tile RMW 写入高 A 区。SiLU 的输入从这些实际 bank 返回读取；每个 tile 请求、响应和消费者背压都经过 owner 接口。
- `ResidentCoordinator` 的请求、完成、poison、flush、租约失效在 owner 的每个模型边沿同步推进。成功的 tile completion 不增加虚假 DDR 字节；act 只有匹配的真实写 ACK 才累计完成。
- 内存按物理地址唯一索引。Gate/Up 的公开 span 为虚拟目的地哨兵，始终没有 DDR 写。act 完整覆盖一次，所有 output/weight/workspace span 互斥，64B mask、1KiB burst 边界与 guard 均检查。
- 56 个 act drain 完成后退休 A lease。Down 在同一 owner、bank、Matrix 库状态上读取刚写出的 act。三轮 prefix 只从实际接受的写 ACK 内容回读、seed、seed ACK，再覆盖；无 golden 初始化。物理 4096 cells/context，包括 M16 padding，全部保留检查。
- 全部 Down final ACK 和终态之后才解码保存的 phase10/11/12/13，以及运行独立平面 recipe 比较。任何前序失败禁止比较和成功发布。

## 冻结来源与复现

`precision_pins.json` 固定模型 `Qwen/Qwen2-1.5B-Instruct`、revision `ba1cf1846d7df0a0591d6c00649f57e798519da8`、L0，以及旧 v0 producer 和官方 BF16 权重 SHA。n1 是此前完整 v0 软件图产生的输入，不是官方 PyTorch capture。M16 取冻结 M128 的前16行，不能称独立官方16-token forward；M128 覆盖全部128行。

小门无需权重或生成 RTL：

```sh
PYTHONPATH=src:scripts python -B -m unittest discover \
  -s candidates/qwen2_resident_matrix/ffn_fullgroup -p 'test_*.py' -v
```

实值复现需要在本地按仓库已有模型下载/转换及 v0 fullgraph 流程生成 pins 指定的原始文件，再核对全部 SHA。每次输出使用新目录，HEAD 用实际固定执行提交，禁止覆盖旧 capture：

```sh
PYTHONPATH=src:scripts python -B candidates/qwen2_resident_matrix/ffn_fullgroup/check_numeric.py \
  --rows 128 --wall-budget 900 --expected-head <exact-checkout-commit> --out <new-output-directory>
```

严格 C++ 参数保持 `-O2 -fno-fast-math -ffp-contract=off -frounding-math`；Matrix、SiLU 均来自已经固定的原 recipe。`numerical_receipt.json` 是本轮两个实际 capture 的紧凑哈希、计数与比较结果，原始 source snapshot、输出和 prefix 张量保存在本地，不提交 Git。完整轨迹只保存有界前缀并记录全流 hash，不能把前缀称为完整轨迹。

## 验证范围和剩余接线

小门覆盖 coordinator-only abort、已接受读响应排空、held bank 响应丢弃、末 ACK 背压、完整 write mask、错误地址/alias、协调 reset、多窗口 A 复用与 Down 多 K chunk。SiLU 主机 facade 同步计算；held 响应测试是供给它的 SRAM 响应，不是硬件 SFU 在途延迟模型。

固定契约保持4096 MAC、32个1R1W bank、768 KiB SRAM与唯一16-lane SiLU。新增代码不分配硬件资源；软件数组只表示既有物理存储。主机累计的 useful/physical FMA 由实际接受 `td_step` 后更新，不替代 Chisel `(physicalSteps-physicalBase)*512` 计数。所有模型流量包含实际 payload 读写，尚不包含完整 descriptor/协议耗时；硬件 whole-wall cycles、MAC利用率和预测继续为 null。

下一集成门应把已经 source/frontend 通过的生产 Host profile 与上述算术数据流作对应核验，再覆盖完整所选 prefill 图。真实 Host/parser、shared iDMA 与最终冻结刺激硬件回放仍待验证；本次 FFN 子图不能关闭五个完整 block 的 M128 门。

## 本轮结果

M16为199.869秒，M128为279.681秒主机wall；四阶段均0位差。M128累计3,637,248个FP32比较元素（Gate/Up/act各1,146,880，Down196,608），56个drain实际ACK4,587,520B，Down实际ACK786,432B；一轮retained-A加载和三轮完整prefix版本闭合。

M128 payload模型流量98,041,856B，包括A读786,432、三份权重82,575,360、act写后读各4,587,520、prefix写后读各2,359,296和最终Down写786,432。它不含整block/metadata，也不是实际DDR带宽测量。

M16和M128均执行原128-row物理Matrix映射，M16只16行有效，其余padding仍检查。因此两者主机物理FMA均为5,284,823,040，M16有效660,602,880，M128有效5,284,823,040；主机wall不能按有效M线性外推。M128的算术映射填满率不是whole-wall硬件MAC利用率。

## 后续公开 Host 接口与历史身份

812d858 的两份成功capture及 `numerical_receipt.json` / `precision_pins.json`
保持原来源。后续 `down_driver.py` 仅增加可选 `owner_tick` 回调，让公开 Host 在
同一个真实 owner 边沿推进；默认仍调用原 `owner.tick`，原9个Down小测试通过。
共享Host模型随后加入公开字节读取接口及普通Down未握手成功的poison栅栏。
这些改变没有重绑定旧capture为新源码PASS；需要复现旧入口时使用不可变commit
`812d858f8e33e1e6da0cac354846465e971aa975` 的源码。新公开字节闭包使用
`../ffn_public` 的独立来源pin、执行及验收结果。
