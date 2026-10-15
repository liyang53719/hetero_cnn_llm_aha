# 独立完整 block CI 准备（尚未触发）

已实现平台盘点、外部审核hash锁定的新root/platform纯绑定器，以及全fresh14
原料metadata/full audit分离reader、五role物化和typed metadata-only reader。
当前24项冷测试（5盘点＋10runtime绑定＋9fresh14）普通与-O通过。
workflow-template.yml 不在
.github/workflows，不会因 push 自动执行。它不会下载权重、加载 native、
生成参考或执行 DUT；无论六项身份是否齐全，都不能产生数值准入。
只准许上传明确单文件 platform_inventory.json（版本、六项文件 hash/大小、
编译器驱动 hash/大小、缺项），没有任意目录或通配符。
这不是曾被拒的 FROZEN_CONTRACT/RECOVERY/pins 的转存或替代传输。

## 真正数值 CI 的最短路径

1. 原 attempt02 窗口结束且无可续接执行后，再评估单次 CI 成本/预算。
   不在该窗口内重复数值。先审查并安装单独 workflow_dispatch 配置，
   checkout 固定 commit；不修改既有 cold-only workflows。
2. 在新 runner 固定 Python 3.12.14、官方 Torch 2.10.0+cpu、NumPy 2.3.5，
   wheel 固定文件 hash 后安装。初始化需实际核 CPU capability、线程4/1、
   deterministic、torch build hash、六 native 字节及 import origin。
   同版本不意味着同 Python ELF。当前 inventory 只盘点，不验证这些条件。
   g++ 驱动 hash 也不代表 cc1plus/linker/运行库；复用原 builder 的完整
   编译器来源检查、flags/四源码检查及新 ELF/receipt 验证。
3. 建立只针对一个已盘点 CI checkout 的显式新绑定。
   原 runtime_relocation.ROOT、six-native path/hash、runtime_read_sha256、
   native_artifact receipt/ELF、input metadata 与 fresh-reference bindings
   均需新身份。不得删除原 hash 检查或接受任意路径/任意版本。
   旧 reference 的精确 hash 只是旧平台记录，不预设新平台等价。
4. 固定官方 revision/ranges/hash 可复用，重新下载13 raw并生成14 typed。
   tail 当前 strict_reader 固定本地混合来源的两reuse＋12fresh，因此新CI
   全fresh14segment不能假装满足它；应采用已有 acquire.py 全fresh路径，
   新fresh_tail.py已提供明确materialize/metadata-only reader适配，尚未以真实全fresh14数据执行。
   QKV原8range与widen/transpose转换、byte correspondence检查可复用。
5. 原官方capture的算术/顺序与完整29输出可复用；以新平台source/native/raw
   边界生成一次全新参考，审查数值规则与差异，再冻结新seal。
   不能把本地旧receipt或当前reference payload上传后当成CI fresh。
6. 原runner计算链、tail、retained write严格ACK补丁、完整资源/债务/输出seal、
   comparison函数与supervisor进程组/heartbeat可复用。只对准入绑定建立新
   明确closure；真实observer enter/exit与后验policy读集冷门先过。
   审定单次3300/3330预算及job总超时，完整raw/reference恢复耗时另计；
   保留单slot concurrency/cancel-in-progress:false，禁止自动重试。
7. 仅明确允许的紧凑摘要/日志供artifact上传：完整block终态、算术比较摘要、
   固定MAC资源与完整block周期分母、占空比、source/input/reference摘要hash。
   上传前独立allowlist检查。禁止raw/typed/npz/可重建权重、禁止被拒metadata。
   完整参考与DUT张量只能在runner临时磁盘生成和比较，不能artifact整目录。

现有CI只证明cold测试或payload guard，不具备上述完整执行入口。
现有工具列出的唯一用户电脑离线，saved coding environments为空；
没有已验证的在线持久云配置可直接接续原执行。
新绑定器只构造受审核配置，不执行runtime验证；全fresh reader只接受审核的
seal/ready digest。还需新平台实际初始化与完整recipe/lifecycle/gates接线。
这些步骤未完成，不能报成可立即执行的数值workflow。

## 冷测试

python -B -m unittest discover -s candidates/qwen2_fullblock_ci_prepare -v
python -B -O -m unittest discover -s candidates/qwen2_fullblock_ci_prepare -v

测试覆盖固定原pins、外部reviewed digest、精确root/sixnative、独立platform
契约、禁止执行策略漂移、无I/O纯绑定；14fresh receipt覆盖、重复/缺失/复用
拒绝、时间顺序与源边界、metadata reader禁止打开任何.bin。
用真实固定形状的合成HTTP metadata和稀疏stat-only占位文件，不是官方输入验证。
未进行新的下载、参考、DUT或RTL执行。

## 可调用入口

fresh_tail.metadata(root, subset, reviewed_raw_seal_sha256)：只读JSON/source与stat。
fresh_tail.audit_raw(...)：显式读取全部raw并验证固定segment/tensor hash。
fresh_tail.materialize(root, subset, new_out, reviewed_raw_seal_sha256)：原转换与独立byte correspondence。
fresh_tail.input_metadata(root, out, reviewed_ready_sha256, reviewed_raw_seal_sha256)：只读JSON/source与stat。
runtime_binding.bind_runtime(...)：精确原pins＋独立审核root/platform契约，返回不准入数值的纯配置副本。

root由新审核契约准确锁定；不将caller自行计算的hash当审核。
这些契约不在本批上传范围，所有被拒metadata仍不上传。

物化写完五role后再做完整raw审计与source边界复核，完成前不发布INPUTS_READY。
绑定器可描述新的observed平台，不保证原capture支持该平台；完整live gate仍须
独立检查Python3.12等实际兼容要求，不能把纯绑定结果当准入。
