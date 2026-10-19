# 最小 PC0 → ACK0 → PC1 → ACK1 桥接 SOURCE v1

本目录是隔离的源码候选。生产28件已按 PRODUCTION_MANIFEST.json 冻结；原仓库、旧 N0 实际工作树、RTL 算术和已生成 archive 未改。本目录尚未 C++ 编译、未执行 RTL，也没有 qraw 数值比较结果。

## 已写生产边界

- 保留原 N0 scheduler、N0 retirement adapter 的逻辑和具体模型入口。新 pc01_driver 在同一栈保持原 scheduler/adapter 存活，完成 fresh reset、唯一 launch、原 PC0 和 ACK0 后，创建私有 PC1 scheduler。全程只有一个 Host/context/root/Syms 和一份 RAM；没有离线 N0 输入入口。
- runtime_policy 仅新增 qraw 分类。runtime_ram 增加单独 PC1 adapter 指针、generation=1 固定 permit、独立 AW serial 和 qraw publication。原 PC0 permit/tag/generation和N0 B门保持原逻辑，未改为通用可写范围。
- PC1 写权限来自实际 Host 公共 job.valid/ready 接受和固定 Dense job身份。后继 router=2，普通/FFN/SiLU路径不作为 PC1 来源。实际 AXI W 数据来自同一模型，只能在 qraw范围经完整 AW/W/B账本成功后写入相同 RAM；全覆盖、SSA、strobe、WLAST、ID、4KiB和56位边界全部前验。
- 同沿模型、共享 vector/Matrix、AXI独立ledger和读债检查全部先于 B mutation。B后只作 noexcept 退休。ACK1需要完整qraw、owner done、共享服务退休和精确completion；post_pc=2/jobs=2后零次后续eval，不接受PC2。
- qraw输出仅完整196608个FP32。新驱动不计算参考、不加bias、不舍入BF16；独立数学和DUT-order两轨输出身份仍由独立模型小片提供，当前 UNBOUND。

## 观察范围

Pc1ProductionGuard复用现有只读注册、实际地址/位宽/type/model身份检查，以及原 GeneratedBinding/SiLU observer。仅观测已在当前archive中的公共job/done、router、共享vector、Matrix issue/counters和AXI边界；不新增RTL taps，也不声称直接观察了每个内部tile/window事件。物理done的内部资源条件以固定原RTL源码语义为前提，外部观察独立核最终无债和完整输出。

共享binaryAdd的请求、保持、操作数、结果和active退休分别匹配router/owner/vector三层；合法add不冒充SiLU捕获。Matrix每次accepted step要求原transposed sliceMask=255，并核steps/wideSteps逐沿增量。终态wideSteps=73728、sliceSteps=589824、executed/useful MAC均301989888，add vectors=12288。

## 窗口与资源

性能分母固定4096×(ACK1高沿−PC1接受高沿+1)，包含全部加载、计算、partial合并、写回、stall和退休。全PC01总周期另外记录，不能将PC1利用率叫whole-block利用率。主时钟周期与host墙钟分开。

全PC01探索cycle ceiling仍为原8000000，包含重新执行的PC0，并不保证PC1一定完成；未完成明确INCOMPLETE且不写部分qraw。完整本地长执行总墙钟、原CPU/地址空间及尾部落证预算尚未绑定，本目录不授执行。RELINK_CONTRACT仅准备单CPU、fresh输出、原flags、仅driver编译/链接的命令计划。

## 冷测的真实范围

实际完成42普通、42优化模式、42搬迁普通、42搬迁优化，以及实际same-buffer入口9普通/9优化，总186项。包括全qraw抽象覆盖、W先于AW、错误owner/tag/generation/serial、提前/错误B、strobe/WLAST、SSA、guard越界、同沿fault前拒、ACK1和读取发布。

源码检查消费同一次读取且size/SHA固定的28件C++ buffer；测试模块先pin同buffer再compile。入口的同长内容替换、长短文件、路径父遍历、文件/父目录symlink均有拒例。日志和测试fixture仅保留本地，未删除。Python抽象ledger不是C++实现，SOURCE静态检查不能替代真实C++编译/接口资格、RTL或数值验证。没有继承原测试作为本次新通过数。

## 复用与公开投影

原完整普通archive与三个runtime对象、原driver依赖receipt中的固定生成/Verilator头共19个现物，仅在private/RELINK_INPUTS记录本地绑定。本候选未复制/改写这些现物。后续须按原工具身份/只读信任profile、源码与现物前后hash、fresh输出、原监督器与明确总截止执行；不得调用带重新生成规则的旧Makefile。

可公开本public目录的文本源码和安全元数据；private目录、cold_logs、cold_cases及cold_relocated不公开。PROJECTION区分原字节复制、有限派生和新增源码；SOURCE_PINS固定44项原来源。独立 SOURCE 审阅结论尚未填入，不能将本README视为GO。
