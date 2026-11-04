# GDN 原串行16兼容路径的真实32lane叶候选

## 已完成

在隔离目录新增 `source/GdnRuntimeChunkExecuteOwner32V1.scala`，覆盖原phases5–17，另有单叶emitter。原ExecuteV8、原Top、source-selection、lease、预算和发布状态均未修改。当前候选**未接入生产Top，未授权FULL**。

32个独立列每lane保持原升序K、从+0起始、先FP32 Mul再FP32 Add，不使用FMA或重排归约。成对64B读分别核tag/error/finite，普通结果写低半并等ACK，再写高半并等ACK，之后才进入下一组/row。Triangular solve只选k<row，row0只读RHS；系数物理beat可能含未使用的对角word，不能说完全不读取其所在beat。Phase17两笔真实64B FP32读之后，只发一次原bank32 policy4 pure-format请求，提取BF16位域，不增加本地舍入器。

## 实际证据

- 官方pinned Chisel plugin完成该真实leaf的Scala编译。复用旧成功stage1的已哈希依赖class，直接用到的GDN/layout/Protocol定义与兼容源逐项匹配；这不是重编完整159源。
- 实际 `circt.stage.ChiselStage.emitCHIRRTL` 成功。357,918 B CHIRRTL，SHA256 `c2e9e8fd15edc1f6688037bfa828713be153f81fc3412b3ad96637d91c6aef6e`。
- 实际IR有一个leaf module，0子模块、0memory；request/result为32lane，memory payload仍512bit；三个payload寄存器各1024bit，共384B。相对V8增加1536bit payload和净1bit控制，未把寄存器位数冒充门面积。
- 单叶源码SHA256 `0fe8672a3e8673f795a3452b8bbd1c9b49ccdeb1a3d4eb4d43f1686349ecae6d`。
- 独立Python模型覆盖地址/计数、逐lane算术顺序、BF16 RNE、ACK依赖及错误/回压。正常与python -O各17/17通过，分别3.598秒/17,860KiB RSS和3.538秒/20,276KiB RSS；每轮30s/128MiB限制。完整结果见tests/MODEL_TEST_REPORT.json及测试日志。这些不执行候选Chisel FSM。
- 本轮两次测试入口失败完整保留：第一次使用旧ChiselStage类名导致编译失败；第二次leaf编译成功，但emitter给CHIRRTL API不支持的--target-dir参数。仅修emitter，leaf源码不变；第三次成功。所有5个阶段均有日志EOF/gzip及owned-group cleanup/reap证据。
- 含失败的5阶段累计wall 34.7824秒、child+supervisor CPU 35.6532秒，最高sampled child RSS 235,331,584 B。阶段总数不含preflight哈希与外部编排开销；采样上限不是cgroup零超冲保证。没有安装、下载、SV/RTL lowering、模拟器或完整DUT。

## 收益及瓶颈边界

M128每head/chunk，phases5–17：

- 向量请求659,456 → 329,728，恰减半。
- 64B读355,264 → 344,800；只消除重复系数读，B/RHS/factor两笔供数仍真实存在。
- 64B写7,424 → 7,424，保持全部ACK。
- 内存事务合计只少约2.89%，不是供数带宽翻倍。
- 原非重叠issue/wait静态弱下界2,044,288 cycles，新下界1,363,904。下界变化不是实测加速比或完整周期保证。

三个1024bit缓存不能消除串行DDR服务、逐K依赖或其他GDN owner成本。只把有效lane从16填至32不能宣称整个block达到80–90%有效MAC。P0/P2/P4无直接GDN执行收益；五块同硬件回归仍必须做。

## 可合并范围与下一步

只把新候选目录作为source-only实验代码审查；不要把它替换到原兼容执行源或把旧artifact标为该硬件。`candidate.patch`只新增候选源、测试和文档，不自动改任何source catalog/selection/approval。

最小后续是新Chunk32 route/authority及exact count的完整闭合，详见INTEGRATION_PLAN.zh.md。旧slot10的Vec16 ABI、RMS slot11不得复用；旧Derived4704请求不能除2。新whole-Chunk exact总数为H*C*334176+4*M*H。接入后先受限真实owner/router协议仿真，再统一Top与五profile原路径验收。

当前没有完整数值PASS、RTL PASS、端到端性能或新artifact，也没有发布。
