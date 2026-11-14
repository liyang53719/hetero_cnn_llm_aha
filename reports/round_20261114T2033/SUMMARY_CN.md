# 2026-11-14 20:33 hetero：Host安全编译路径推进（INCOMPLETE）

## 原身份终态
- 原43670确证600秒上限收尾，exit-15；CPU599.05s，峰值383936KiB，无对象。并非OOM，未重启未知旧37765，不再重复原IR同预算。
- 起始main81a59437989814032a83f2588e2a221fa171c097，CI43632954751成功，仅payload guard；本地旧HEAD54776eab工作树干净。

## 实质代码与验证
- 新基于官方LLVM CodeExtractor的安全工具：AllowAlloca=false，原caller栈不搬到helper，每段100–1000条。2048向量、source/strict计数与异常负例一致；160 liveout×2048、caller槽及两侧哨兵一致。不同于已证明栈逃逸的arc-split-funcs，不运行后者风险候选。
- 第一版实际Host提取42.08s完成278helper，helper无alloca，106strict/17sink/26source顺序ABI不变。但caller槽739→22772，最大块82599→72407，成本不理想，未长编译。
- 聚合参数候选49.74s完成，caller槽1017，最大块50652，但eval行数增至462565、打包操作增加，仍未长编译，不因槽数降低宣称性能成功。
- 新预选原始区间工具避免反复提取生成的packing；多段2048数值、160输出与1536重叠指针顺序微型通过。Host仅静态扫描534段/297122指令，尚未实际内存段提取或编译。
- 官方O1微型source重读、strict正负及17宽ABI通过，不加fastmath/虚假pure属性。大O1首次verify-each在90s超时（798次整模块校验）；新5381保默认最终VerifierPass，40.56s成功，未关闭模块校验。实际eval仍106 strict、17sink、26source，无LLVM浮点算术。
- O1新IR SHA256 df30f7b43e7beb30645f74061f2ceb89dee83963534021d4dfca982fd28e70e7。此候选未使用危险Arc拆分，仍需Host实际验证。

## 在途与五块
- 唯一新36001对上述不同O1 IR进行llc -O0 PIC，180s/6GiB、独占锁与10秒CPU/RSS心跳；快照30.01s墙钟/29.97sCPU、RSS212892KiB。尚未取得成功对象；成功也先核当前layout/凭据，不能直接全profile运行。
- 五块完整128原Chisel数值仍0/5：Qwen2、0.8B L0/L3、35B L0/L3。固定4096与统一硬件约束保持；完整RTL/完整block有效MAC利用率未测。
- L0 strict下溢FAIL、35B真实权重/数值契约/准入阻塞保持。旧37765UNKNOWN未重启，不继承丢失50行PASS。新恢复候选尚非最终统一五块通过源码。
- 下一：沿36001收终态；对象成功才接已备真实85端口AXI/原21命令215描述符和有限首RMS，失败则利用已验证的原始区间提取方案，不盲重试。

## 保留与清理
- 临时清单已查，约349MB新增源码/候选/失败证据及运行锁均保留，清理0。仅允许摘要/中文计划上传，无权重、NPZ、IR、检查点或被拒源码发布。
