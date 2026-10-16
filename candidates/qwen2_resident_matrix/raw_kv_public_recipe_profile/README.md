# Public PV16 独立 native pair reference profile

## 中文计划
- 已完成：fresh native16 与 native128 在实际 `brg_matmul:avx512_core_bf16` dispatch 上通过原始全部数值 gate；安全结果见 `raw_kv_native_pass_results`。这只建立本次 native/independent reference 比较。
- 已完成：独立的新 Public producer profile、双 case 身份和精确 dispatch 冷 admission 检查、262-source 闭包；27项冷测试 normal/-O 通过（8.405/7.894秒）。
- 进行中：独立源码审查。
- 待实现：配对 setup producer/assets verifier overlays、封存 manifest、linked runner；本切片 `authorize_run` 始终拒绝。
- 待执行：新的原始 Public PV16 全链真实数值运行，保留 27 assigned official gates / 28 observed fields / full29=false 的准确范围；不继承 native PASS。

## 不同 reference 的边界

Public 的 sequential C++ hardware reference 与 block/pair C++ reference 保持原源码、独立产物和读取 fence。OfficialAttentionOwner 现有 QK16-stripe/fold/multiply、PV16、Dense/Matrix/Host 数据流均保持原样。新的 native 独立 QK pair recipe 只属于 PyTorch-reference producer，不能替换 hardware oracle 或 owner 算术。真实 Public 同输入运行及原始 gate 才能建立两者关系。

`dispatch.validate_pair` 只检查有界元数据。本次完整 source/result/payload/双库/receipt/pins 身份必须由外层输入，fresh M128 small-gate SHA 必须指向同一次 M16。两次原始数值 PASS、完整 diagnostics、全部9条 BF16 matmul 均为 `brg_matmul:avx512_core_bf16` 才能通过。AMX、混合 implementation、纯 info 未知、缺少 execution/postflight、外国或陈旧收据都拒绝。未知 ISA 不能当成身份；不设置 ATEN、oneDNN 或硬件强制选项。有限实例通过不证明通用 backend order。

`profile.snapshot` 冻结原 Public M128 launch 与已验证 native v3 的完整源闭包，再加入本切片及实际 PASS 证据。当前不产生/安装 overlay，不执行 package、producer、library 或数值入口。旧 M16/M128 source contracts、原算术、门限与历史失败收据保持原字节。

## 后续最小接线

1. 新 setup profile 通过显式 adapter 复用原 native generator、Recipe、original verdict/export/diagnostic helpers；不伪造 native-only runtime 的252-source context，也不把 native16/native128 产物冒充 native_m16/native。
2. 配对 assets admission 同时绑定 generated gate 和双库身份，再接受新 producer exports；保持全部232个 native16/128产物验证和源闭包一致。original runtime_identity 不能单独接受新 recipe。
3. fresh16→128 两个独立 child 经过完全相同的 dispatch contract，成功后才 seal references。kernel build 由唯一父进程拥有，两库共享30秒；不能嵌入会与 compiler 进程组清理竞争的 setup child。
4. 新 linked runner 保持900秒 setup、2400秒 work、2430秒 external、3420秒 outer/60分钟 job。全部 clone/source/preflight/cleanup 计入原绝对 deadline。这里只声明已批准的边界，尚无可执行 runner。

冷测试只使用标准库、原有 metadata helpers 和合成控制收据。不会加载 NumPy/Torch/ctypes native library，也不会运行模型。实际 native PASS 证据与冷测试、未来 Public PASS 分开报告。

冷检查命令：

    python3 -B -m unittest candidates.qwen2_resident_matrix.raw_kv_public_recipe_profile.test_profile candidates.qwen2_resident_matrix.raw_kv_public_recipe_profile.test_dispatch -q

另以 python3 -B -O 重跑。已验证的历史 PASS receipt 在测试中只是格式/兼容性 fixture，不能作为当前新运行 freshness 证据。
