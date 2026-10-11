# FFN 共享 A bank 的 FP32 tile 子门

这是默认关闭的源码增量，叠加 `transposed_host` 已验证的公开 workspace profile。
实际 Down owner、kernel 和原 SiLU owner 增加内部 typed 端口；小 harness 将相同
bank 的 gate/up 读响应直接送到唯一既有 16-lane SiLU，再写回 act。没有第二套 SRAM
或算术阵列，也没有私有 Host Command128、地址或 `bias_index` 编码。

本子门完成物理端口、生命周期、前端和主机实值检查。Matrix 结果直接进入 tile、
生产 Host 的 Gate/Up/Activation 三命令预检与融合仍待接入。现有 Dense 仍读写 DDR，
不能将早前软件整图 131,727,360 B 搬运量或 71.35% 理想上界记为硬件已实现。

## 布局和端口

- 原 A：16×1376×256 bit，704,512 B；原 B：16×160×256 bit，81,920 B。
- A words `[0,768)` 保存 BF16 M128×K1536，393,216 B。
- 三个 FP32 M128×N160 tile 分别占 `[768,928)`、`[928,1088)`、`[1088,1248)`，
  每个 81,920 B；最后 `[1248,1376)` 65,536 B 继续留空。
- 固定列 n 的 16 行构成一拍：bank=m%16，word=768+slot×160+(m/16)×20+n/8，
  FP32 lane=n%8。顺序 index=(m/16)×cols+n；ng 是实际源列，不是 group 编号。
- 每个 bank 仍只有 1R1W。每次 64 B 有效读取实际读取 512 B SRAM；每次 64 B
  写入用一读一写 RMW，实际各 512 B。不能把有效载荷字节当 SRAM 端口流量。

begin/seal/release 均校验非零 identity、32 对齐 ng、M16/M128 和 N32..160。
生产计数在实际 RMW commit 后推进；消费计数在 response.fire 后推进。control.fire
只表示接受命令，bridge 在释放输入后的下一状态重新核对完整标签和排空，再发布
complete。几何不一致、错误顺序、非有限值、非法别名操作均 poison，要求协调 reset。

已接受的 RMW 即使 abort 也退休；受阻响应位保持稳定。bridge 空闲时不会抢走外部
held response。活动 Dense 在 raw abort 同拍锁存错误，随后进入原有 drain，保留 Matrix、DMA、
seed、写 ACK 的退休义务；已保持的 done 位不变，以 resetRequired 阻止发布。
live 高区 tile 可与 K≤1536 的低区 Dense 共存；较大 K 明确 Bounds，其他 owner
明确 Unsupported。新借用事务只在 owner 空闲且所有已接受事务排空后开始。

## 已执行的验证与边界

`model.py` 是实际 bank 地址/端口模型，`bridge_model.py` 是控制状态模型；后者的
SFU 由不透明函数和测试延迟代替，不是算术或硬件周期模拟。负测包含 input 几何错、
非法末 release、retire 边 abort、RMW 排空、外部响应背压、错误算术结果和 reset。

`check_numeric.py` 使用固定 Qwen2-1.5B L0 的既有 v0 软件 producer 导出 gate/up，
经实际 bank 模型读取后才计算原 C++ SiLU recipe，实际写入 slot2 并读取所有输出后
才访问比较值。35,328 个 FP32 值对独立平面索引计算和原 act 导出均逐位一致：
M16×160 是已有 M128 的首16行，M128×160 位于 ng160，M128×96 位于 ng8864。
8960 能被160整除，N96 是人为末列子窗口，不是生产自然尾块。保留输入、空闲区及
所有未写 lane 的哨兵逐位不变。来源不是新的官方 framework capture。

严格编译使用 `-ffp-contract=off -fno-fast-math -frounding-math`；原 exp 范围缩减、
七次多项式和每步 FP32 RNE 顺序不变。legacy Add/Mul/Div 的 inexact underflow
仍报错，精确 subnormal 保留。host fenv 不是 HardFloat 异常位全域等价证明。

最终源码 typecheck 87 个实际 Scala/HardFloat 文件，生成 10 份 CHIRRTL；默认关闭
bank/Down/SiLU owner 的规范化 IR 等于原版。规范化只删除源码位置，保留断言文本
和硬件。完整 Host/kernel 已 typecheck，未展开完整顶层、未生成或执行 RTL。
额外寄存器为 bank 1387 bit、SFU loan 2 bit、bridge 592 bit，共1981 bit；其中三份
有效数据 hold 各512 bit，没有新增4096 bit SRAM响应寄存器。32个1R1W SRAM和唯一
16-lane SiLU 在实际 IR 中核对。地址除余、比较、仲裁和 lane mux 有新增组合逻辑，
尚无面积/时序测量；固定4096 MAC与768 KiB SRAM账不变。

独立审查发现并修复了非法 release 先报成功和 execute→finish 同拍 abort 漏报，
早期前端快照完整保留。最早一次 IR 对照因 assert 诊断文件/行号不同失败，修正
仅位置规范化后重验；没有删除断言或放宽算术。具体身份见 `delivery_manifest.json`。
原完整 M128 native/FP32 final FAIL、数值政策未决、五个完整 block 未验收状态不变。

## 可复跑入口

无需模型权重的轻量门：

```sh
python -m unittest discover -s candidates/qwen2_resident_matrix/ffn_tiles -p 'test_*.py' -v
python candidates/qwen2_resident_matrix/ffn_tiles/check_frontend.py \
  --out work/ffn-tiles-new --cache work/matrix-interface-jars \
  --hardfloat work/upstream/hardfloat_continuous
```

只有已按 `precision_pins.json` 重建并核对本地 producer 后才可执行：

```sh
python candidates/qwen2_resident_matrix/ffn_tiles/check_numeric.py --out work/ffn-numeric-new
```

CI 只运行小模型/host recipe 测试及源码前端，不下载权重、不重新运行实际 producer。
数值捕获冻结源文件并复核前后 hash；原始 tensor、编译产物和 IR 均不进入 Git。
下一步是将 Matrix 实际 FP32 输出按同一标签/顺序接入这些 bank，并落实 Host 命令
预检、生命周期及最终 act 的真实下游消费，然后再核完整模型搬运量和执行周期。
