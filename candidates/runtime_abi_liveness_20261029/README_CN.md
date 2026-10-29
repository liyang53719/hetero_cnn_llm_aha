# Fresh same-job startup ABI 与存活字节账本（TEMP / 尚未执行 DUT）

## ABI 调用合同
调用者先完成独立owning build/result/frozen payload/source身份验证，不能让任意未审ELF进入此helper。`runtime_abi.prepare(binary,binary_sha,tool_manifest,tool_sha,out)`接受Path和sha字符串：stream hash、ELF64LE x86_64/PT_INTERP/DT_NEEDED有界解析，拒绝rpath/runpath/audit/filter；只允许既有build tool manifest pin中的系统loader，执行一次 `loader --list binary`，按实际解析结果核每个shared library canonical path/bytes/hash。不是执行DUT main或运行周期。

CLI需 `--execute-reviewed-loader-list` 且由既有strict outer supervisor包围；内部20s/15CPU秒/64KiB文件采集界不冒完整group cleanup证明；loader子进程继承外层owned group，不创建新session。不运行不存在的ELF。本轮所有loader输出是明确mock fixture，没有执行任何loader或DUT。

`verify(receipt,receipt_sha,binary,binary_sha,tool_manifest,tool_sha)`在validate/pre/post执行重核独立receipt hash、同一binary、tool、libraries/aliases、interpreter mapping、直接依赖集合、cache/preload未变。consumer Popen必须显式`env=clean_env()`，不继承LD_PRELOAD/LD_LIBRARY_PATH/LD_AUDIT/GLIBC_TUNABLES。不改参考运行wrapper的OMP或数学。

只读`/etc/ld.so.cache`hash；`/etc/ld.so.preload`存在且非空即拒绝，绝不改安全配置。binary采用既有4GiBartifact边界、stream hash；runtime单文件512MiB、toolmanifest32MiB、ABIreceipt64KiB。外部未知库或漂移失败。范围为startup resolution identity，later dlopen/OpenSSL动态provider/实际运行时映射不在此资格内；严格标NOT_QUALIFIED，不将身份匹配提升数值PASS。receipt的独立pin必须来自owning reviewed workflow，不以重新pin攻击性JSON当来源证明。

官方行为依据：[ld.so --list说明](https://man7.org/linux/man-pages/man8/ld.so.8.html)：枚举依赖及解析位置；不调用ldd处理目标binary。

## 实际元数据与存活账本
`live_bytes.metadata(TENSOR_ACQUISITION_PLAN.json, runtime_source_root)`复核五profile tensor数12/14/11/18/15，总70 /3,531,306,272B；三个runtime archive238,463,458/259,895,288/259,161,043B，共享内容去重cache305,867,713B。完整MoE256 experts不裁减。

`census([owned_job_root, repo_root])`按实际文件统计；嵌套root去重、symlink不跟随、hardlink按inode去重。同时导出pathlogical/uniqueinode/allocated/free，明确采样非原子也非peak。准入使用**uniqueinode logical**，与已审watchdog output_sample一致，不把hardlinks重复算入原cap。`admit(snapshot,phase,additional_bytes_upper_bound,remaining_wall_seconds,phase_wall_seconds)`维持8GiB setup/acquisition、12,081,306,272B tree、1.5GB reserve和120s摘要收尾预留。缺显式phase增量上界拒绝，压缩archive字节不是安装峰值。仍须continuous supervisor；不做删除/下载/安装。

只读本地现存三个site为871,930,691/893,790,670/891,753,696B；weights树3,532,041,004B。ACTUAL_LOCAL_LIVE_BYTES.json是当前保留文件的采样，不是未来CI安装/临时解包/reference/output峰值，不迁移旧数值PASS。`wheel_unpacked`可核现存锁定ZIP并读centraldirectory未压缩字节，但仍不能当pip安装临时副本峰值。

未来fresh job必须实际补：完整runtime及临时目录峰值、reference/provider/output/live bytes、最终buildfree、loader真实解析receipt、DUT RSS/速率及可能dlopen；当前无可证五块350min预算。

## 测试与界限
7 ELF/parser/pin/environment/group-inheritance tests +6 mock prepare/verify receipt链tests normal/-O；4真实小临时树/资源gate tests normal/-O。缺library、替换loader、cache/env/tool漂移、路径/ELFoffset/audit等均拒绝。仅metadata和源码轻测，未执行任何真实binary/loader/reference、编译/CI/网络下载。原所有证据保持，公开payload审批不作为本模块依赖。
