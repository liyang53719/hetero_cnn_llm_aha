# Slot 2 物理银行隔离回归

状态：候选真实 Chisel IR 与物理银行存储/协议回归通过，精确范围见证据；完整 block 数值与最终 RTL 仍未通过。

## 范围

从父任务指定的真实 `../source/TransposedDenseBanks.scala` 编译；不拷贝/替换其实现。`Slot2BankFixture` 只继承原模块并输出已有 tile issue/commit 与响应信号，无附加 SRAM。A 为 16×1376×256 bit，B 为 16×160×256 bit，端口/容量不缩减。该隔离测试不实例化 Matrix/MAC、vector 算术、Dense owner 或 full top，不改变它们的 4096 MAC/32 lane 设计。

- `emit`：真实 Chisel→low FIRRTL→SystemVerilog。检查 A/B 存储数量、深度、位宽及每 bank 1R1W 同步延迟；读取真正 low IR 的两个 768 base add，要求 literal 已在加法之前为至少 11 bit。保留实际 IR/SV 与宽度证据。
- `all`：一个 `RawTester`、一个实际 Verilator 构建、同一完整 bank 实例依次完成以下三组。阶段间复位控制；复位不假设 SRAM 被清零。
  1. 所有合法 rows={16,128}、cols={32,64,96,128,160}、slot={0,1,2}，每一个 index、全部 16 bank、全部 8 FP32 lane 的实际 issue/commit 地址及真实写读值；插入响应背压；接受后改变 live input 验证 reserved commit 使用 captured key。另测 slot0/1 的 matrixProducerOrder。
  2. 通过真实 activation RMW 端口写满 A 的激活保留区 [0,767]，验证全部 128×1536 BF16 halfwords（对应 16 bank×768 word×256 bit）；slot0/1 写入并读回后，slot2 写入 FP32 sum-shaped **主机刺激值**，seal→drain→release；无 A clear/reload 地扫描全激活区，再以 ng=160 重复。读取 slot2 自洽不替代 A 保留检查。主机和数学公式只是 scoreboard/刺激，不声称真实 sum/vector/owner lease 通过。
  3. cols=0/16/48/192、非法 rows=32、slot=3，以及 slot2+matrixProducerOrder 的 begin 被拒绝并 poison。每负例之间 reset。
- `address` / `retention` / `negative`：可单独诊断，各自会生成一次 simulator。正常候选只运行 `all`，不重复跑三个独立阶段。
- `baseline retention`：原冻结源码真实模拟，预期 slot2 drain 可读回而 A 保留扫描失败。`baseline emit/address` 应定位十位截断。预期失败必须检查日志具体断言，不能把任何 nonzero 都当成负例成功。

## 资源与执行

只由父任务统一执行，每次一个阶段。没有自动重试、增大预算、清理、网络下载或长 full-top 编译。复用现有 Scala2.13.16、Chisel6.7.0、chiseltest6.0.0、Java21、Verilator 与 bounded supervisor。

各阶段 JVM -Xmx512m / ActiveProcessorCount=1；supervisor aggregate RSS <=1GiB、单文件<=64MiB、该 run 总输出<=256MiB、保留磁盘8GiB、启动要求 MemAvailable>=7GiB。make -j1，-O0。compile/emit 各 wall90s/CPU60s；all/address/retention 各 wall240s/CPU210s；negative wall180s/CPU150s。所有上限取继承原 supervisor cap 与所提上限的较小值。若触顶，先报告，不静默增大。运行将占用真实 bank 容量但不实例化完整 MAC。

相对工作目录为仓库根目录。设置 HETERO_TEST_WORKSPACE 为已按既有固定工具链 recipe 重建的工作区绝对路径；该处应有 p0_resident_fullcompile_recipe_20261030T1609/BINDING.json、固定 jars 和已核 Verilator 工具清单。prepare 会核原工具哈希，不下载或接受任意替代库。新 runner 只把工作区根目录改成显式环境变量，baseline 源来自本仓库保留的原文件；三份 Scala、候选 banks 与编译规则字节不变。

    export HETERO_TEST_WORKSPACE=/absolute/verified/workspace

运行：

    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py prepare --run candidate_r2
    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py compile --run candidate_r2
    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py emit --run candidate_r2
    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py all --run candidate_r2

可选负例需父任务单独安排：

    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py prepare --run baseline_r1 --variant baseline
    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py compile --run baseline_r1
    python candidates/transposed_tile_address_fix_20261103/tests/run_stage.py retention --run baseline_r1

`prepare` 只创建计划并 pin 真实源/tool 字节。每个 output 目录只用一次，run 计划后源码改变则拒绝运行。所有测试阶段要求 compile 严格闭合：native exit0、errors=[]、进程组清理完成、pipe EOF、gzip finalized；通过 marker 与实际文件需一并核验。脚本的 Python AST 检查仅是语法检查，不计为硬件通过。

## 仍需外层验收

这个测试不验证实际 DenseTileSumBridge 与 vector arithmetic、不验证 owner lease metadata、不跑当前 terminal stimulus、不签收综合/PPA/完整 RTL。修复后仍需真实源重新生成正式模型并用原 terminal stimulus 重放，确认非有限输出是否消失。

## 实际验证范围

r1 的真实 IR 发射已证两处首加法至少11位；首次模拟构建因原PCH触及64MiB cap而失败，未进入测试。r2通过官方 VM_DEFAULT_RULES=0 扩展点使用普通对象编译，无PCH生成或空替身，全部cap不变；一次Verilator模型完成64800次地址检查、29280次写/读、全196608个A半字在两窗口slot2 drain后保持及7个非法begin拒绝。上述sum值来自主机刺激，仍不等于原sum/vector/owner或完整block数值通过。
