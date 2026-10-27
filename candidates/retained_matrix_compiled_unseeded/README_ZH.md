# TEMP：compiled unseeded 8×512 功能模型 service 的有限闭环

这不是五块完整 prefill、seeded service、provider RTL 或硬件利用率验收。五个完整块的数值回归状态仍为 **0/5**；本目录不改 canonical 任务状态。当前主线仍是原始 Chisel 五 profile 并行完整 M128 数值回归，再冻结同一硬件/接口/RTL hash 回放五块。

## 本次真实结果与边界

独立实际审 `fb195675…d2ff60` 绑定：同一有限 unseeded 8×512 Matrix service 功能模型，两组事务、五个 context 加 transpose，**48 个有时钟周期、24,576 个 FP32 值比较及 51 个控制断言，共 24,627 项、7 个 wide step** 完成。八个 endpoint 各 512 lanes 是功能模型构造范围，不是 provider RTL 的实现/物理资源证明。

成功版新增真实初始化前导：clock 保持 0，物理 top reset 先 0 后 1，各执行一次 eval，然后保留原 48 周期主体。因此不能称全部 stimulus 逐字未变，也不是任意 reset 调度的证明。没有默认 software reset、清 RAM、删除 reset_observed 检查或强制打开 ICG。4 周期 held 检查只覆盖 valid/首 word，不是所有 held payload 的逐拍记录。

fixture 内执行的 74 个有限 GMP value/flags、12 个非有限输入拒绝和 1 个状态合同是继承的局部测试，不是本轮重新做 HardFloat/DPI unit 资格，更不是全 IEEE。日志和 ELF 仅给 hash；无原始逐 lane trace。sample CPU 5.72 s、采样 RSS 5,648,384 B、runner wall 5.9304755849 s / outer wall 6.0237107179 s 不能外推 M128、吞吐、面积、频率或 90% MAC 利用率。

## 不覆盖原失败

`FAILURE_HISTORY.json` 保留：0459 emitter final-instance gate FAIL；0552 codegen 的 4,123 WIDTH + 25 UNOPTFLAT 警告 FAIL；0643 native codegen 0 但原 svdpi.h postcheck FAIL，以及独立 0657 窄 postcheck；0704 native compile/link 0 但原 MD 重复同 pin 解析 FAIL，以及独立 0722 窄 postcheck；0724 reset_observed SIGABRT。后继结果不回写这些收据。原 build 的 808 条警告、reset-driver relink 的 42 条警告仍列出，不称 warning-free 或已证明无害。

源码中的历史注释只记录当时状态；以这里分层的真实审件为准。旧 type/emit/source 授权也不等于现在可以直接执行公开配方。

## 小源码与复现入口

本目录九个 `source/` 文件是原字节，共 64,023 B：四个有限 GMP/model/fixture header、两份手写 DPI C++/SV、官方 emitter 适配 Scala、成功 reset 前导 driver、phase observer。小 synthetic 字面是测试 fixture，不是用户权重。小 `.sv` 是手写功能 wrapper，不是数 MB 生成 RTL。

1. 按 `PUBLIC_REFERENCES.json` 的固定 commit/path/blob/hash 取既有公开源。92 源需原 composed/ordered recipe 和固定外部 20 个 HardFloat 源，不能用裸根目录冒充。再分别恢复四 behavior 源和两个 realMatrix 源。
2. `CLASS_SELECTION_DELTA.json` 明确选择：原 550 class hash 记录被 14 个精确 probe 输出覆盖（10 替换、4 新增）成 554，加 3 个 realMatrix 输出成 557，即 **540 + 14 + 3**。不是把 550 和所有 probe 输出相加，也不执行旧 Specs。
3. 按公开九源依赖生成 preserved 68，与 557 不重名并集为 625；既有 backend 11 源生成 39 为 664；本包 observer 只取 2 类、已公开 FIFO lowering 只取 3 类为 669；本包 emitter 单源生成 13 类为 682。排除旧 official bridge/ObservedSpec/错误同名版本。类名/size/hash 是检查 rebuilt 源的身份，不提供 opaque 类作为依赖。
4. 可先仅运行 `python -I -S -B <本目录>/rebuild_selection_metadata.py --repo-root <精确源码根>`，它只读四份已有小 hash JSON 和本包增量，打印 682 条 hash metadata，不读/生成 class、不启动 JVM。必须自行编译、验证新的实际 class 身份；历史 class hash 不是“在任意环境一定逐字重建”的承诺。
5. `REPRODUCTION.json` 给六阶段原 argv 的可逆角色投影及逐 TU/link argv：typecheck → 官方 emit → Verilator codegen → 21 TU build → 单 driver relink → run。`GENERATED_HASHES.json` 只记录 12 个 emitter 和 25 个 codegen 产物身份；不上传这些大产物。生成器还生成实际 `actual_port_bindings.hpp`，不能手写假 ABI 替代。
6. 历史 codegen/build 用旧 9,050 B driver，可从最终 driver 反向应用 `RESET_PREAMBLE.patch` 精确恢复；成功 relink 用本包最终 9,531 B driver 和已资格的另 20 objects。干净重编最终 driver 的全 build 是另一次 rebuild，不是原单 TU 实际记录。其他三个 patch 仅保留历史 getter/有限 width 变化，可正反恢复，不悄改旧失败版本。

106 Maven 依赖的相对路径、顺序和 SHA256 与实际 type 输入逐项一致，原物理两目录与新角色化目录不同。官方 Verilator deb 恢复脚本和 firrtl2 源 archive 固定 pin 已引用；GCC14 官方源码格式依据不保证生成本机 GCC 二进制，GMP/loader/sysroot 等必须另做精确恢复与资格。GMPxx 是显式 link 输入但不是实际 DT_NEEDED，不称已加载。

本包是可恢复源码、选择规则与历史复现配方，**不是自包含 runtime、原私有 supervisor 的完整副本或新执行许可**。新执行仍须独立冻结、资源监督、输入/工具/runtime 资格和明确批准；不得自动串联、重跑或扩成 seeded/fullblock。这里的 packaging 小控制不运行真实模型、JVM、EDA、C++ arithmetic 或原 reference。
