# First-fault connect 分派：完整函数纯回归

真实新 first-fault artifact 的两处旧分派遗漏已经局部复现：原 `preflight` 和原 `connect` 完整函数对新 schema 均缺先建立 source_relocation 的步骤，随后真实 consumer 严格报“independently admitted first fault artifact”。正例没有 mock validator：修复后的完整 `preflight → connect → consumer.main(--validate-only)` 均实际通过，后者真实走预算、独立 review、adapter/catalog、编译证明、ABI 元数据、原 session 和 512 MiB consumer 内存门。

R3：native 0，errors[]，完整 cleanup / EOF / gzip，20.731 秒，采样 RSS 126,636,032 B。当时 source catalogue 为 882 项，实际 SHA 见 SAFE；不把后续计划/证据文件或最终发布身份称为本次实跑。

## 严格测试边界

原实际七件、参考、P0 输入均只读，未编译或执行 DUT/ELF，也未运行 loader 或 reference forward。新 reference/program/runtime/views 在独立新 material 根实际生成，保原真实校验及 containment，不用共同祖先或手工更改旧 runtime 路径。

为调用完整函数，独立 fixture 使用明确 synthetic executor identity / adapter / budget / approval 元数据；仅精确指定 synthetic PID 的 stat、boot_id 与 monotonic 观察受控模拟，验证函数代码和返回不替换。该身份不是活 owner，不能用于真实执行。原 ABI 字节和 pin 保留，另派生 fixture ABI，仅替换 owned_environment pin 与 environment 的 9 个缓存路径字段；其余环境键、ELF/tool/loader/六库/configs/loader_output 摘要全部逐对象相同。故这不是新身份下的 fresh ABI PASS，更不是数值或资源准入。

## 保留的失败

- R1：fixture 调用 reference 初始化时漏 execution_mode，原精确模式门正确拒绝。只在 R2 runner 的 context 字段补 mode，产品不变。
- R2：fixture material 错放在 strict supervisor 的 stage output 内；原 provider 固定 `references/profile0` 符号链接被原监督器正确拒绝。没有改监督器或删除该链接。
- R3：同一 R2 runner 原字节，material 与 strict run 目录改为兄弟域，和真实生产布局一致。material 仍由实际 extra_watch_roots 监控，所有 TREE / 磁盘保留 / inode 核算及上限保持。 R3 的 stage 512 MiB 上限仅覆盖 run/log；兄弟 material 受 aggregate 12,037,043,872 B、单文件 2 GiB、100,000 entries 和 8 GiB 磁盘 reserve 约束，不冒称 material 也受 stage 512 MiB 门限制。

## 复现

`run_full_connect.py --repo <实际候选源码> --source-pins-sha256 <catalogSHA> --original-execution <已闭原执行根> --output <不存在的新material-fixture根> --offline-review <独审的synthetic adapter review> --offline-review-sha256 <SHA>`。

必须由原严格监督器在已有 numpy runtime 中运行；原 CPU180 / wall210、RSS2 GiB / AS2.5 GiB、未知 owner5 GiB + 1 GiB、原 aggregate tree 与 8 GiB reserve 不变。`--output` 必须与 strict run 目录分离且被额外 watch roots 覆盖。外部 offline review 需与 runner 按实际 catalog 构造的 synthetic commit / 完整差异精确一致；不能替换为真实执行批准。audit hook 禁止进程与网络。

只发布本原字节 runner、有限无路径摘要和本文；不发布原 raw log、实际材料或合成可执行身份文件。`numerical_pass`、`execution_admitted`、`new_runtime_abi_pass` 均 false。
