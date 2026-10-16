# A-hold 的有界实际算术资格

本目录单独记录 `dense_a_hold_candidate` 的默认开/关 C++ host Matrix 对比。
此前 `COLD_RESULT.json` 保持原样，其 opaque result fixture 不被升级为数值证据。
本次每个被接受的 bank-fed Matrix packet 都调用原 `td_step`，真实执行全部
4096 个 FP32 `std::fma`，再由 owner 的实际 result、seed ACK、MatrixDone、
DDR write ACK 和 terminal 事件逐个退休。

复用已有 `official_bf16_matrix_silu.so`，SHA256
`a44f4cd7861d1207698bb3dfc89820ded30a44db1cf1c8b9f951019d1edce1fa`。
原编译回执 SHA256
`f036483fcc7ddb66fddce088e8eb346945225e4eca162eb43174a53171c2f5eb`。
回执、严格编译 flags、4 个原编译源文件及 ELF 全部核验。没有新编译，也没有改动
运行中的私有 source/assets。执行在独立 Python 进程加载只读库，C++ 静态状态
属于该进程。`sf_reset` 检查 IEEE FP32、RNE 和未开启 FTZ/DAZ，`td_reset`
建立每个新 job 的状态。没有调用 SiLU 算术。

## 范围与结果

| M | K | N | 输入 | 每次模式实际 FMA | 输出 FP32 words | A gather 关→开 |
|---:|---:|---:|---|---:|---:|---:|
|16|32|32|BF16|131,072|512|32→32|
|16|32|96|FP32，含 BF16 RNE 边界位|393,216|1,536|96→32|
|16|32|256|BF16，5+3 尾组|1,048,576|4,096|256→64|
|128|32|160|BF16|655,360|20,480|160→32|
|16|256|32|BF16，两个 K128 chunk/prefix restore|1,048,576|512|256→256|

五组各运行开、关两次，总计 counter 实际记录 6,553,600 次 FP32 FMA。
全部逻辑 FP32 输出逐位一致；每个返回的完整 16×256 物理结果，以及 accepted
packet、DMA descriptor stream 的 SHA256 也一致。最后一例实际恢复前一 chunk
的全部4096个 FP32 accumulator cell。每个模式最多两个 joined payload slot、
既有五个 accumulator context；开启 A-hold 的 reserved operand 不超过三槽。

所有输入是确定性的有限值合成数据，不是 checkpoint 权重。M128 只有 K32/N160。
本项验证 A-hold 调度与既有 C++ 算术的一致性，未与独立框架参考比较；完整业务
block、RTL、1 GHz、面积与80%/90%利用率验收均为 false。C++ FMA counter 只
记录实际主机算术次数，不是硬件 wall cycles 或硬件利用率。

## 复现

冷检查不加载 native library：

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_numeric
/workspace/shared/hetero-contracts-venv/bin/python -O -m pytest -q candidates/qwen2_resident_matrix/dense_a_hold_numeric
```

有界 native 检查显式提供已核验回执和不存在的新输出路径：

```sh
/workspace/shared/hetero-contracts-venv/bin/python -m candidates.qwen2_resident_matrix.dense_a_hold_numeric.check_numeric /workspace/scratch/f28987e955ed/public-recipe-cloud-be00-20261016/private/assets/library/official_bf16_compile.json /tmp/a_hold_numeric_recheck.json
```

源码与 library 在运行前后均核验。数值回执另外固定执行器本身和 pins 文件的 hash。
输出文件已存在会拒绝覆盖；无需新增模型权重、额外编译或修改 Public admission。
`NUMERIC_RESULT.json` 可用同一已有库重建，差异应为零。
