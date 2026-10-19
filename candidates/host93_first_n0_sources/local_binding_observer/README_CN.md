# 本地固定 binding 与只读挂载 trust profile SOURCE

本片只读构造真实 binding，消费既有官方五包与当前系统身份。未下载、安装、运行包工具、构建、启动 Host/CI；不创建 work/stage/tools。原 bootstrap v2 与原 CI UID0 分支不变。

## 入口

observer_entry.py 必须 Python -I -S -B，显式提供 --repo、--work-root、--package-root 与 --trust。trust 只能 original-ci-uid0 或 local-readonly-mount；不自动切换。入口以 size/SHA、逐级 NOFOLLOW、稳定同 buffer 加载两个本片模块和已发 bootstrap v2；审计 hook 禁止网络与 native 子进程。只读观察限制为60s wall、40s CPU、512MiB AS、1MiB单输出，不替换或扩张原实际阶段资源门。

binding_observer.observe 读取固定7个系统程序，核真实 resolved path/size/SHA/mode，并调用原 system_identities 复核。固定五包通过原 size/SHA、原 validate_package 和67成员总量/每成员校验，仅在内存持有原数据。未知库不搜索安装；沿原 ELF reader 的九个固定 soname 词表构造有限闭包。三份原 ELF 与两份原 shebang 形成原 native_profile schema；结果仍不证明 ABI/symbol version 或完整编译器辅助程序闭包。

原 binding(raw,pin,repo) 消费生成的 canonical bytes。任何缺包、漂移、未知身份或不满足谓词返回具体阻点且 binding=null；没有合格 binding 的进程 exit2。成功状态是 COMPLETE_STATIC_BINDING_UNQUALIFIED，绝不等于执行许可或 native qualification。

## 独立 LOCAL_READONLY_MOUNT_PROFILE

这是对当前固定系统文件明确选择的独立本地分支，不是把 UID65534 等同宿主 UID0，也不改变原 CI 的 UID0 规则。

- 精确 EUID/EGID1000、无附加组，uid_map/gid_map 都为1000 0 1；保存原 bytes pin。
- profile 精确绑定原 binding pin，以及其中全部程序/库的有限 resolved 文件集合。每文件原 bytes/SHA/mode 保留，记录实际 UID/GID/device/inode。
- 按 mountinfo 最长覆盖 mount 验 ro,nosuid,nodev；嵌套可写挂载不会被外层 ro 掩盖。每文件及 /usr 祖先必须无 group/other write 且当前进程不可写。
- 同一已打开文件 fd 验 fstatvfs 的 ST_RDONLY，读同一fd原 bytes，前后 stat/vfs/path identity 再核；构造前后两次快照一致，使用前后再次逐文件复核。
- native_preflight 只将原 before.st_uid==0 单锚替换为 local_owner(before,resolved)，并证明逆替换。原路径、库 metadata、hash、mode、ELF/shebang 等谓词全部保留。
- 本次只读观察将五份已由原 parser 验证的原包 buffer 通过有限五路径 reader 提供给原 preflight，无 stage 文件伪造。未来实际 stage 读取模式仍使用原 checked，不使用此内存输入模式。
- 这些证据证明本地已绑定只读身份，不证明官方系统镜像供应链来源。unknown/writable/drift 均拒绝。

## 已做与待做

真实只读普通/-O 都成功构造本地 binding/profile，并通过上述原 preflight 单 owner 投影。相同现物选 original-ci-uid0 时正确拒绝 UID65534 的 libc/libm/loader。完整实际身份、路径、mount 记录只保留私有本地输出，不发布进 Git。

纯mock普通/-O、搬迁普通/-O各9组；同buffer入口普通/-O各9项，共54组通过。mock 的 readonly fd 旗标仅用于分支测试，不能冒充真实挂载证据；真实观察单独记录。

原473树、seqnum补丁、make -j1、单CPU、8GiB/3GiB准入、4/6GiB AS和6600s共享预算不变。未来任何实际工具调用仍须独立审定调用方、明确work root、已验binding/profile、原监督和退出cleanup证据。本片不授执行；原 ci_toolchain 的私有工具argv适配另片，不偷偷回退/usr/bin五工具。

## 本次公开投影及最终有限审

状态为 TEMP_SOURCE，正式结论 `SOURCE_GO_EXPLICIT_LOCAL_BINDING_OBSERVER_AND_READONLY_PROFILE_ONLY`。审 MANIFEST 4029 B / `b6783d0893b0aee06a0143d7e39eaafcff977d4ed347c9a209ce88f0ebd64db4`；SUMMARY 4121 B / `ce464f7444822fe6e31644ae84cc3a6ffeaec750324356d3e44a5e3044a92dda`。绑定的是最终来源 MANIFEST 8124 B / `5479837da040462ce5be566dcc4ebeaa74536dbb733fab439663a9181ecb7534`；早期预读身份已被该最终冻结身份取代，不作为本次资格。

独立审在搬迁目录普通/-O各9组、入口普通/-O各9项通过；另对10个实际 profile 目标文件逐一做两模式只读静态验证和漂移反例。目标 mount、namespace/uid-map、inode漂移被拒，无关 mountinfo raw-hash变化不冒充目标变更。以上独审计数与作者的54组记录分列，不能相加当作额外独立测试。COLD_RESULT.json 保留作者冻结时的 PENDING_INDEPENDENT_REVIEW 字面状态；本节记录其后的独审结果，未改写历史冷测记录。

只发布声明的10件安全源码/测试/元数据；9件原字节保留，本README仅补最终身份与边界。私有 binding/profile 本体、实际观察JSON、机器路径库存、原日志和搬迁副本均不公开。COLD中的私有观察size/SHA仅是来源身份，不包含其内容。系统固定路径、UID规则及合成测试路径是源码合同，不是实际私有根目录。

本次仅建立明确的只读静态非null绑定路径，原CI UID0逻辑不变，未授native工具/ABI/后台构建/Host/N0资格；后续caller必须另审并在真实使用前后核同一身份与原资源门。未修改workflow，未重新进行冷测或实际观察。
