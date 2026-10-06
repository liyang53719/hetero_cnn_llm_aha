# C03.3：合成 shape/layout 向量与宽地址 oracle

## 验收范围

此交付仅为 synthetic E0 软件合同。它不接入生产编译器、不改变现有
Command128/descriptor wire 字节、不改变 QwenBlockShape/HostBlockCommands。
C03.2、官方 checkpoint/forward、真实 Host→RTL 和旧 Q2 数值回归仍是独立门禁。

- Python 使用任意精度整数计算后检查位宽，不允许 bool/float、隐式截断或回绕。
- JSON 向量含 62 个固定合成案例及所参照 Scala 源文件 SHA256；全部整数用十进制字符串，禁止先转浮点数。
- C++ 消费者以 unsigned __int128 独立计算宽地址和当前 typed-reader 算术子集。
- ScalaTest 消费者提供了实际 QwenBlockShape/Layout 的安全 legacy 子集回归入口；沙箱没有 sbt/Scala 工具链，因此该消费者未运行。提供源代码不等于 Chisel 通过。

## 合同边界不可混同

1. `shape` 是解耦候选。hidden、Q/K/V/context 宽度分别描述，maxRow 覆盖全部显式逻辑行宽，包括可选 extra_rows。query_tokens 与 kv_tokens 分离；默认 query 容量 1024、KV 容量 65535，各有独立检查。16 位正整数是编码边界，不代表当前 backend 的对齐、8 位 head 计数器或 SRAM 本地索引能够执行。
2. 新 chunk 的 Q/K/V 投影都是 query_tokens 行；完整 K/V cache 视图是 kv_tokens 行。score/probability 为 [q_heads, query_tokens, kv_tokens]，明确为虚拟张量，不增加平方 DDR 分配。value_dim 独立是合成候选，不能视为当前 Qwen2 数值路径支持。
3. `legacy_layout` 保持当前 QwenBlockLayout 的 30 个 region、FP32 容器、64 字节对齐、15 个 writable region 及原顺序。包含 tiny、尾块、Q2 默认几何和乘积跨 signed-Int/4GiB 的安全布局算术。它不修复当前 Scala constructor 的弱校验，不宣称大几何可运行硬件。
4. `tensor_v2` 对应当前 TypedTensorReader 的算术边界：SHAPE4 为 18 位，正连续 ELEMENT strides 为 signed24 可表示范围，元素总数最多 2^32−1，BF16/FP32 字节宽度为 2/4，base 对齐 64，padding 后 exclusive end 可等于 2^56。region 输入采用 HostBlockCommands 启动时的 56 位 aperture 安全子集；单独 reader 本身可以接受更大的外层 region。它不验证链、权限位或 DMA 行为。owner_dimensions_fit_u16 只表示维度位宽是否能放入 owner，不表示作业合法。
5. `wide_address` 是通用正向 C-order BYTE stride/span 压力 oracle，不能编码成现有 STRIDE3。地址、stride、未 padding 的 span/payload/offset 位宽独立；padding 后的 end 另按地址 aperture 检查，不能视为 padded-span 寄存器宽度检查；允许行间 padding，拒绝重叠 stride。包括大于 2^53 的 base、跨 4GiB 元素偏移、stride 字段溢出、乘法/加法/span/总 payload 溢出、索引越界、padding 越界和 exclusive 2^64 endpoint。

## 格式和消费方式

主向量：`tests/fixtures/block_contracts/shape_layout_vectors.json`。
`schema=heteronpu.shape-layout-vectors.v1`；每条有 id、operation、scope、inputs、expected。
expected 为 accepted/result 或 accepted=false/error。所有 inputs/result 整数均为十进制字符串。
消费者必须按整数解析；Scala 用 BigInt(string)，C++ 用受检查十进制解析，禁止 JSON number→Double→Long。

额外 legacy TSV：`tests/fixtures/block_contracts/legacy_layout_vectors.tsv`。
每行依次为 id、hidden、ffn、heads、kv_heads、head_dim、max_tokens、max_row、kv_width、writable_start、total、region 列表。
region 格式 name:offset:words:external，顺序完整保留；external 用 0/1。

独立 C++ 程序：`cpp/shape_layout_oracle.cpp`。完整 stdin/stdout TSV 协议在文件头说明。
Python 测试把同一 JSON fixture 转为 TSV，逐个比较结果和拒绝理由；另有固定种子 1200 例 differential 和 malformed stream 检查。
独立常数断言覆盖 shape、全部 legacy tail offsets、Q2 arena、跨 4GiB 乘积及极限地址，避免只做生成器自比较。80 个小型 strided case 以穷举每个元素地址独立校验 span。

## 复现

```sh
export PYTHONPATH=src
python3 scripts/generate_shape_layout_vectors.py --check
python3 -m pytest -q tests/test_shape_layout_contract.py tests/test_abi_integer_contract.py tests/test_model_geometry.py tests/test_descriptor_chain.py tests/test_gemmini_descriptor_v2.py tests/test_block_checklist.py
python3 -O -m pytest -q tests/test_shape_layout_contract.py
```

若 g++ 不存在，C++ 用例会明确 skip，不能声称跨语言消费者已通过。
GitHub 的 `shape-layout-contract` CI 安装 Python 依赖并要求 g++，执行上述 focused regressions 和优化解释器测试。

真实 legacy Scala 消费需在已配置 HardFloat/Chisel 的环境运行：

```sh
cd chisel/continuous_prefill
sbt -batch 'testOnly heteronpu.continuous.QwenBlockLayoutVectorsSpec'
```

该命令仍未在本次沙箱执行。新 decoupled candidate、独立 KV 长度和当前 reader/owner 的 DMA 前拒绝行为，须在 C03.2 接入后另作 RTL 验证；本交付不绕过这些门禁。
