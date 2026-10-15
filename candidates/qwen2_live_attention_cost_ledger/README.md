# M128 live PV32 静态成本账

这是固定 M128 / H1536 / 12Q heads / 2KV heads / HD128 / FFN8960 的整数工作量账。
只读取九个已跟踪源码的固定 SHA256，不导入 runner/owner，不读张量、动态库、历史 work 或私有文件。
它不运行数值、全链、RTL、网络或 CI。旧 FAIL、验收阈值及原实现均不改变。

## 冷运行

```sh
python3 -B candidates/qwen2_live_attention_cost_ledger/ledger.py
python3 -B -m unittest discover -s candidates/qwen2_live_attention_cost_ledger -p 'test_*.py' -v
```

源码缺失或 hash 漂移会拒绝报告。冷树测试只复制九个 pinned 源码与账本，隔离启动 Python；
不执行被 pin 的源码，因此这些源码内部的其他运行依赖不属于本账本依赖。
所有门限由 Fraction 精确比较，JSON 小数仅展示，不参与判定。

## 当前路径工作量

- 实际绑定：`qwen2_live_fullblock_model_m128/runner.py:127–141` 使用 PV32 owner 和原 BF16 SiLU。
- PV32 `pv32_owner.py:40–80`：每个 query/head 缓存 Q128；K逐因果对读取；PV每32列仍读两个64B V包。
  因果对 P=12×128×129/2=99072。Q读786432B、K/V各50724864B、输出写786432B，合103022592B。
  score/prob已驻留，外部字节为0；当前没有全K/V缓存。PV两输出ACK后退休见同文件99–127。
  固定64B读响应由 `ffn_public/prefix_owners.py:155–157,359–362` 的16个FP32 word约束。
- 七Dense形状和FP32容器边界来自 `official_bf16/dense_silu.py:40–45,90–95`。
  唯一BF16权重93585408B。仅此权重加Attention已有196608000B，即3072000个理想64B服务槽。
  用全图有用MAC6014828544作分子，容量上界47.8015625%。这是流量子集下界，不是完整账或测量。
- Dense满4096宽FMA理想issue下界1462272；QK请求792576、PV32请求396288。
  合2651136个共享issue槽，上界约55.3899913%。Dense exact-tree Add/restore、padding、hazard均未计，
  因而不能称完整当前Dense请求数。`QwenOwnerProtocol.scala:81,349–380` 只有一个Matrix实例，
  Dense/Legacy经过mux共享；`BurstProtocol.scala:34–38` 仅一个step通道，
  `MatrixPipeline.scala:25–61` 是该服务。此约束是共享端口条件界，不是软件tick预测。
- Attention Scalar：18P Add、5P Mul，合2278656；ExpNegative调用99072、Div1536。
  来自PV32的16-stripe fold、score scale、softmax diff/sum和四个PV32列组的概率乘法。
  BF16材料化不算Add/Mul；Exp内部展开、延迟及其他阶段Scalar未计。
  当前单在途Scalar控制是后续映射需校准的潜在瓶颈；操作数不能直接转成cycle。
  对应实现线索为 `Qwen2Block.scala:98,284–285` 的scalarReq/scalarRsp互斥状态，
  仅作后续审计定位，不属于上述九个定量账本pins，也不据此产生新的周期数字。
- SiLU：128×8960/16=71680个16-lane包，每包6阶段，共430080个向量阶段调用，
  不是430080个单lane调用或周期。见 `official_bf16/silu_recipe.cpp:23–59`。
  `ffn_fullgroup/check_numeric.py:376–397`每包从TileBank读gate/up、写act：逻辑载荷
  2×64+64=192B，合13762560B。这是片上桥流量，不能加到DDR账；也不是SRAM物理RMW字节。
  后续act DDR drain/down read仍须在完整账中独立计入。

## 完整block必要预算

6014828544/4096=1468464个满阵列等价槽。

| 目标 | 完整block整数槽上限 | 理想共享64B总字节上限 | 扣七Dense唯一权重后的余量 |
|---|---:|---:|---:|
| 80% | 1835580 | 117477120 | 23891712 |
| 90% | 1631626 | 104424064 | 10838656 |

90%的未取整预算为4894880/3；整数槽必须向下取整。
预算是必要容量条件，不能证明调度可行。DMA与issue下界可能重叠，禁止直接相加。
所有RTL/measured/prediction cycles和hardware utilization字段均为null。
旧rectangular-attention的131727360B账已包含另一种K/V驻留路径，不混入此live账，也不重复扣除其收益。
