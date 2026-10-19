# 单次 fresh PC01 实际尝试：PC1 合同错误，未产生 capture

正式独立实际审查结论：ACCEPT_ACTUAL_PC01_CONTRACT_FAILURE_PC1_022_ONLY。review_pc01_capture_failure_actual_20261019T2053 的MANIFEST为380字节 / 63fcbb1ec1dfe3ac1ab10ab0a8eb17913b1cf37b27bc23da5e123da37de12e70，SUMMARY为9383字节 / e53a59e4f085a3616a97ffbfc78bfe5f8354e77994af0a4dccc2473569310824。

仅聚合已保留原证据，不运行native、RTL或参考模型；原件和原PASS不改。

## 已观测实际结果

本轮从2026-10-19 19:52:21.295524 UTC开始，原outer收据于20:46:40.793025 UTC结束；outer退出1，墙钟3259.5155213670078秒。native自然退出1，墙钟3258.247189秒，timed_out=false、cleanup_confirmed=true、reaped=true。WNOWAIT原观察为CLD_EXITED/status1；后续清理发送signal的记录不能改写自然退出原因。协调器状态INCOMPLETE，首异常ValueError、failure_code=null，监督层CHILD_EXIT_NONZERO；这些与driver安全诊断分开保留。

132字节原native诊断的安全字段为scope PC0_ACK0_PC1_ACK1_M128_ONLY、status CONTRACT_ERROR、phase RTL_PC1、code PC1_022、numeric_comparison NOT_RUN。capture目录存在但为空，counts.json、actual_n0.f32le和actual_qraw.f32le均未写。没有本轮N0输出SHA、PC1逐值结果、完整计数或数学误差。

## 控制流可以支持的范围

固定driver在转入RTL_PC1前必须经过完整ACK0退休强门：单launch/job/done/ACK、post-PC1、committed/writeback各786432字节、N0 B12288；随后复制N0并在内存计算SHA。结合已绑定源的安全诊断，可作该前置控制流已经过的推断；本轮没有导出的计数/数组/SHA，不能独立授予N0与原3c25077e…参考逐bit匹配，也不能把旧轮N0周期或数值PASS移植到本轮。

PC1_022只定位到固定identity检查的8谓词合并失败：runtime phase、N0 published、qraw未published、root指针、reset、resetRequired、gotError、gotFinish。原诊断没有逐谓词值、失败周期或调用点；具体失败项和根因保持UNKNOWN。不得把后来静态假说倒填成此轮实际观测。PC1接受/退休进度、ACK1、主周期与利用率均未独立观测，不能据墙钟推算或声称完成。

三轨数值比较NOT_RUN。official_raw_numeric_pass、application_accuracy_pass、typed_recipe_bit_exact_to_rtl均null，full_block_pass=false，五block仍0/5；此轮是合同失败，不是已证实的数值不匹配。

## 资源与来源

独立重链最多180秒，本轮新t0最多10620秒，合计授权上界10800秒；本轮实际未墙钟超时。8000000主周期仍只是cap，没有导出的实际周期计数，不能称已耗尽。AS限额6GiB，native用户/系统CPU分别3242.865532/2.720812秒；435208KiB RSS是协调器子进程累计记账，不是独立phase峰值。

原7成员证据MANIFEST为882字节 / 9476ed1280b0048f6cbb8261f9ee4b16dcd90b58c30152749a3a2b6370b28db9。SUMMARY仅列安全数字、已公开源码位置及原件size/SHA；不发布私有机器路径、命令、raw日志、输入、数组或二进制。本次汇总不删除任何原件、不重跑作业、不替换原参考或阈值。

## 独审身份复核范围

终止后独立只读核对原7件证据、11项工作树、同一已接受ELF/object/archive、47项副本、28桥源、44上游来源及全部16输入94920448字节。输入字节hash已经核对，没有重新计算输入数值；本轮没有输出数组。这个独审后验不能冒充协调器自然exit0之后才执行的成功postflight或三轨比较。固定PC1_022的8谓词/4调用点仍不能由原诊断区分，未改变UNKNOWN结论。
