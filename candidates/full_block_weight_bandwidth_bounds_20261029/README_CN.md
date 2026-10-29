# HOLD：M128 原生权重与完整 block 利用率必要界

**未授权发布/未 push；不是 RTL 实测、数值 PASS 或新架构不可行性证明。** 用户固定4096与完整block周期分母、至少80%并争取90%以上的目标不变。

阅读 `REPORT_CN.md`。P3/P4 的226/218 active experts仅对应钉住输入的原始Torch参考，不证明硬件路由相同，也不是所有MoE输入的普适限制。

## 两种复现等级

```sh
python verify_bounds.py
python -m unittest -v test_verify_bounds.py
python -O -m unittest -v test_verify_bounds.py
```

默认仅重算本包提交的70项shape/hash摘要和公式，明确 `SUMMARY_ARITHMETIC_ONLY`；**不读取原始header、权重或路由ID，不重新验证这些payload的真实性。**

```sh
python verify_bounds.py --repo <repo>
python verify_bounds.py --repo <old-sparse-repo> --fixed-commands <fixed-Commands.scala>
```

可选源验证读取repo相对路径中的14份runtime/固定Commands及1份constructor helper，严格检查SHA。旧sparse checkout缺固定Commands时必须显式提供同SHA文件，不回退历史版本。源SHA通过仍不是header验证、编译、cycle预测或DUT实测。脚本仅用标准库，单输入文件上限1MiB；验证/测试可在256MiB地址空间下运行。

## 边界

- 冷启动原生无压缩字节必要界、当前root AXI mandatory读取、外部物理DRAM字节、理想warm驻留与当前单beat FSM界分开列示。
- 100 GB/s + 1 GHz仅为明确假想条件；当前单512-bit同clock read port至多64 B/root-cycle。
- 当前weight `4N−1`与GDN等独立上界不相乘；本包不未经非重叠证明相加。
- P0七个矩阵保持BF16，小参数FP32映射另计；共享门N1原生量与N32padding另计。

`MANIFEST.json` 为冻结白名单，仅所列文件可考虑后续小repo提交；不包含原始权重、route IDs、NPZ、原始downloaded headers、私有绝对路径或任何硬件改动。
