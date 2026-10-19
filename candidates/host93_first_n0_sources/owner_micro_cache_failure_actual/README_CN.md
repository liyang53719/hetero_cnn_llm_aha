# TEMP：Owner 局部 cache 编译与有限运行失败

原 session 44110 已自然终态。build 自然退出 0，用时 62.420557 秒；owner run 自然退出 1，用时 109.877769 秒。两阶段均未超时，cleanup 已确认。outer 退出 1，用时 176.78127549499914 秒，于 2026-10-19T23:42:25.191602+00:00 结束。原 EXECUTION_RESULT.status 保持 INCOMPLETE，failure_type 为 ValueError，原 failure_code/failure_boundary 仍为 null；run 原监督诊断为 NATIVE_SUPERVISION / CHILD_EXIT_NONZERO。本摘要将本轮实际结果明确记为 FAIL，不给旧 receipt 倒填字段。

## 已观察的有限进展

复用原已验证生成树的 516 个 obj 源文件，完成新的 owner executable 编译；本轮未重新生成、未重建 backend，也未复用原 Host archive。生成 makefile 字节未改，旧绝对 fixture 仍按原合同只读核验。ELF 为 12,718,080 字节，SHA-256 a91ff84921ba6b116b762a3f4eb384f1518be88e3feca562c1ee2996b6ba4fa1。

完整 run log 共 4 行、13,238 字节，SHA-256 6de8bfac1443d0beeae995b365b431f59fde5a6df63c2fb214b36038b19d1a02。末行报告 CONTRACT_FAILURE / RESET_REQUIRED_HIGH，edge=76580，采样标签为 HIGH_EVAL_POST_SOFTWARE_PREVIOUS_EDGE。此前软件已记录两个 window request 与两个 terminal，terminal edge 分别为 52379、62000；当前处在首个 drain 已发起、尚无已记账 drain terminal 的阶段。软件记录 matrix groups/dones 均为 2、issues=7680；当前 RTL matrix wideSteps=7680、steps=61440、sliceMask=255。

末行的软件账本记录：write descriptor=1、data beats=10、committed bytes=640、write responses=0；N0 returned=786432 字节、Wq returned=491520 字节。该软件账本只处理到上一沿，不能用 response=0 推断当前高沿没有 ACK，也不能把当前 valid=0 时的 payload 当作已退休 terminal。以上是 typed-RAM 接口账本，并非 iDMA/AXI B 退休证明。

当前高沿 RTL 标量中，owner_sharedPoison/router_bad/coor_bad/coor_serviceError/win_resetRequired 为 1，coor_ng=0、coor_block=1；banks_poison/matrix_poison 为 0。这里只保留同时观测到的值，不据此排列先后因果或认定某一模块首错。typed RAM 或 RTL 首因仍待查。

## 资格和证据边界

本轮为 fresh owner 端口的合法 job 微场景，未执行 Host PC0 前缀和 iDMA/AXI；预定的 ng=160 partial1 首 issue 目标未观测到，完整 job 未完成。full_job/full_block 为 false，五 block 仍 0/5；official/application/typed-to-RTL 资格保持 null。本轮不能合并为原 Host 失败的同因重现，historical_host_failure_reproduced 仍为 null。

原七件证据 manifest：959 字节 / 140559eb53a4ef330a5e8e54b1b544d801b323bc2c39bcfe2b9bb3cb969935f4。完整日志、原工作树、生成缓存、数组和二进制保留在私有证据中；公开仅含固定安全计数及内容身份。该摘要制作没有新生成、编译、RTL、重链或测试，也未改原 FAIL。

## 正式 actual 独审

正式 actual 独审已封：review_owner_cache_actual_20261019T2348，MANIFEST.json 786 B / 0a832dcb156af5f8df8620b2b43846dd0071bd36afdf42c0b9e3091a7fafbdcd；SUMMARY.md 9476 B / 14bb3cbebaa5002dad596c235db675cec66904a60e0ec8c8101d735ac853f1b1。verdict 为 ACCEPT_ACTUAL_OWNER_CACHE_BUILD_NATURAL_ZERO_RUNTIME_RESET_REQUIRED_HIGH_ONLY，仅接受本次 cache 编译成功及局部运行在 RESET_REQUIRED_HIGH 自然非零终止的事实，不授予上游根因、Host 同因或数值正确性。v2 只填正式身份与审查状态，原事实和资格边界不变。
