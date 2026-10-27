# TEMP：MoE FFN r2 类型与三个短控制事实

本片保留原生产六源类型检查（28 新类）、单独 Spec 类型检查（1 新类），并发布三个短 mock 协议负控 case 的准确事实。原 Java exit0、3/3 完成，但原监督包装器的 reporter 正则遗漏 `should`，因此原 wrapper exit1 / qualified=false **仍是 FAIL**。新增小解释器只读已保留的 732 字节日志，不重跑或重写原结论。

## 已知未闭合点

- 本片 DenseWriteback、ActivationGroup 的资格条件仍拒绝 transactionId=0；真实父 Admission 首事务为0。三短负控不覆盖首0完整链，不能据此说完整 group 已接通。相关 RouterDense/Gather/DownReader/pipeline 的后继统一修复另案，不混本片。
- 正向192 Scalar+64 format 长 case未执行；actual Scalar、ALU、formatter、Dense/DDR、完整序列父链及数值均未验证。logical32是控制接口，不是32条物理 II1 lane；五块完整原Chisel M128/同4096 RTL资格仍0/5。
- 原 STOP、包装 FAIL、rawconsumer 与 group/source 层级均保留。没有 Host/新 RouteGroup txn0/helper/权重、class、IR 或工具缓存。

## 可恢复源码与选择

`DEPENDENCY_RESOLUTION.json` 固定当前公开提交与16个源码/recipe引用。四个依赖源可按精确blob直接恢复；QwenOwnerProtocol515389须按公开 composed/ordered-vector recipe恢复，根目录旧版本不能替代。完整baseline编译另需原20份HardFloat精确pins；本片不声称自包含编译或完整历史动态闭包。20个 selected class 符号来源明确，但不发布其二进制。

仅选择此包的一个FormatV3定义与固定ScalarV2协议引用，不混同名shadow；不能把五个整依赖文件一起编译冒充原20类选择。未来目标执行须独立封定工具、输入、环境与监督准入。本包只做来源/包装与小解释器控制，不新增目标执行。
