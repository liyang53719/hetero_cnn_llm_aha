# PC01 最小 driver 重链 SOURCE

本片只复用已有普通 archive、三个 runtime object、固定生成/Verilator header，共19现物；同buffer复核28件桥生产源并写fresh47件数据。只执行两阶段：新 pc01_main.cpp 的固定 -O0/C++17 编译、按原顺序链接。不会运行产生的PC01 ELF，不调用旧Makefile、backend构建或SV生成。原N0与缓存树保持只读。

## 固定来源与前后门

复用原run_reference helper的有限读验/保存和原ci_support_v3 fixed_support/run_phase，原WNOWAIT、自然退出、reap、owned-group cleanup和首错误优先不变。原dependency_gate只在固定soname表加入libatomic.so.1；两个原ELF数值上界投影保持原已审实现，没有重写parser。数学模型的36项编译依赖加libatomic、libpthread.a与libpthread_nonshared.a为39项。现场只读profile已按原UID1000/映射、ro/nosuid/nodev、同fd只读、owner/mode/hash逐项检查，但这不是native资格。实际每phase前后仍重验。

私有配置和19项缓存目录由精确size/SHA绑定；公开只含身份、固定系统程序角色和源码相对路径。普通archive魔数必须!<arch>，thin archive拒绝。source/cache同buffer落fresh普通文件，前后逐字验；compiler-search仅四个已固定真实工具的有意symlink，数据路径禁止symlink。-B与独占PATH固定cc1plus/collect2/as/ld，不回退同名系统工具。env、argv、source、profile、对象和最终ELF前后复验。

## 单次低资源合同

最早t0包含launcher读取、命令/解释器/hash/准入。总上限180秒；初始读验+stage最多30秒，compile总95/work80/CPU80，link总25/work10/CPU10，尾预算30。原每phase内含cleanup5/postflight10。外层TERM170、再KILL5、最后shell证据5，共180；尾30实际包括最多20父落证+5fallback kill+5外层证据，不承诺另给父30秒。

单CPU，父/子AS6GiB，FSIZE64MiB，tree256MiB/log1MiB；累计rusage maxrss门6GiB不冒称每phase独立峰值。入口及两native之前仍要MemAvailable≥8GiB、磁盘≥3GiB。首失败停止，compile失败绝不link；保存/恢复错误不得替换原错误，安全码仅固定词表，未知null。成功要求两自然exit0、cleanuptrue、全部前后身份相同、固定ELF依赖闭合与外层exit0共同成立。

本SOURCE尚未C++编译/链接或执行native。冷测状态以COLD_RESULT.json为准，测试使用纯Python和mock，不能等同C++接口资格。私有launcher/配置/catalog/profile、cold日志和搬迁fixture不公开。

## 后继长执行边界

已明确分两步预算：独立重链≤180秒；后继只读接受成功ELF/receipt，另一个真实t0、最长10620秒，含120秒尾和≤60秒三轨比较；授权上界相加≤10800秒。两步之间等待不计仿真时间，也不宣称同一t0。Host将从fresh reset重跑PC0并继续PC1到ACK1，不能恢复已退出进程或加载离线N0。8M是全PC01探索帽，不是完成保证。
