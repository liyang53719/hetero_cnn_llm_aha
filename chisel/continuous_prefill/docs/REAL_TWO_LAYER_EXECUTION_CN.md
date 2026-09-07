# 真实尺寸 Qwen2 双层：固定执行与验收入口

本文件定义执行方法和门槛，不用脚本存在、CI 启动或控制测试通过代替数值完成。

## 固定范围

- hidden=1536、FFN=8960、12 Q heads、2 KV heads、head_dim=128。
- 16 tokens、两个不同确定性权重的 layer，一个 Host launch。
- 42 条原 Command128、430 个 typed descriptor、38 个实际 owner 作业。
- 原 512-MAC Matrix endpoint 和 pinned iDMA 各一套；不回到 BlockLaunch。
- 第二层 X descriptor 直接等于第一层实际 Y 的 DDR 地址，不允许 Host 复制或参考中间数据注入。
- 完整比较 1,409,024 个 FP32 值；每层都包含 KV 两个输出 view。

这不是官方权重质量、28 层模型、q1024、持久/分页 KV 或 DC 的验收。800 MHz 的物理时序仍须单独签核，不能由仿真周期推定。

## 本地 agent：只执行，不改代码

保持运行中的旧目录不变，选择新的绝对路径，设置既有锁定 iDMA 导出目录：

```bash
export IDMA_EXPORT=/absolute/path/to/verified/idma_export
bash chisel/continuous_prefill/scripts/run_real_two_layer_gate.sh \
  /absolute/new/qwen2_real16_two_layer
```

有完整离线工具时可以同时设置 OFFLINE_TOOLS 和 HARDFLOAT_SOURCE；未设置时入口使用已有 sbt/Verilator 环境。禁止直接修改生成 RTL、参考计算、容差或已有结果。

成功必须同时满足：命令退出码 0、gate.exit=0、simulation.exit=0，以及 REAL2_ACCEPTANCE.json 的状态为：

```text
PASS_REAL16_TWO_LAYER_HOST_NUMERICAL
```

只复核已有结果、不重新运行电路：

```bash
python3 chisel/continuous_prefill/scripts/verify_real_two_layer.py \
  --repo "$PWD" --evidence /absolute/existing/qwen2_real16_two_layer
```

复核所用源码必须与该结果的 sources.sha256.json 匹配。main 后续发生代码修改时，应使用该证据 source_base_commit.txt 对应的独立冻结 checkout；不要放宽哈希检查或编辑旧证据。缺工具或依赖属于环境阻塞；数值、协议或验收异常保留目录和首次错误，返回开发侧，不要求执行 agent 编码。

## 控制与数值分开

```bash
bash chisel/continuous_prefill/scripts/run_real_layers_frontend_gate.sh \
  /absolute/new/real16_l2_frontend
```

这个独立入口执行 9 项真实 Chisel decoder DUT 测试，但 metadata 和 owner completion 是测试服务，不执行 Matrix/iDMA 算术。它的 CONTROL_ONLY 状态不能替代前面的双层数值状态。

## 连续性、错误和证据要求

数值入口复用现有 AXI-only memory TB。启动前中间区填毒；reference 仅用于比较；仅成功写响应使 DDR 数据可见；每条成功 completion 必须晚于完整写回。第二层不复位，不重新装载 hidden。两层 WQ/WG/WD 的实际只读权重指纹必须不同，七个矩阵权重区域必须相互独立；最终第二层 Y 必须不同于第一层 Y。

独立 verifier 重新读取所有 actual/reference 二进制、全部 CSV、公共 ABI 命令和 descriptor，检查层间 Y→X 地址、shape、stride、PC/event 顺序、MAC 和 iDMA 守恒、源文件身份；不只读取 PASS 标签。

CI workflow `qwen2-real-two-layer-20260907.yml` 在真实完整请求成功及独立校验之后，才把原始字节发布到 `reports/execution/REAL16_TWO_LAYER_<tested-source>/`。发布使用独立 Git index 和 fast-forward，不改写被测 DUT、不覆盖不同的旧证据、不 force-push。

## 下一门槛

本固定双层门槛成功后，继续同一 Host/Matrix/iDMA 路径推进真实尺寸 32/33-token 及更长序列。当前 64-command frontend 只容纳最多三层 63 条命令；扩到完整 28 层前仍需开发侧处理命令容量、tensor 生命周期和权重输入，不转交本地 agent 修改代码。
