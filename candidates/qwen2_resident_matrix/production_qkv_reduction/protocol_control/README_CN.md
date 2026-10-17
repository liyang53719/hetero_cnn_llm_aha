# Host + production QKV router 控制门：三个有界失败，非 PASS

本目录保存可复现源码、固定 metadata fixture/依赖 pin，以及去标识化失败证据。生产默认关闭 patch 已独立 class compile；这里是下一控制门，不覆盖真实 Dense/Matrix/SFU/iDMA 算术或 QwenOwnerKernel 物理债务。

## 实际结果
- v7：94 Scala class compile 及 CHIRRTL结构通过。7模块、0memory/extmodule/FPU，CHIRRTL 2,047,981 bytes。解释器写 lowered FIRRTL 遇2MiB统一文件限额，callback未进入。
- v8：只分开生成文件8MiB与父日志2MiB。lowered FIRRTL正常生成3,907,694 bytes，callback进入；60秒callback预算耗尽，无case PASS，没有1024周期标记。
- v9：只增加诊断println。174次初始化poke、首ready.expect、首监视与clock均完成，最后报告cycle64；仍在原预算耗尽，无case PASS。标记无时间戳，不能分配阶段耗时，也不能推断组合环或确切总cycle数。

三次均完成严格 scoped cleanup。没有Verilog/SystemVerilog，没有数值执行。FAILURE_SUMMARY.json是安全投影，不是原receipt字节；保留原receipt/log SHA与相对cleanup时序，不包含机器boot ID/PID/session/绝对monotonic时刻。完整本地证据留存。三个失败保持失败，不自动续跑或升格协议PASS。

## 源码复现（不执行硬件）
```
python -B reproduce_sources.py --version v7 --out <fresh-v7>
python -B reproduce_sources.py --version v8 --out <fresh-v8>
python -B reproduce_sources.py --version v9 --out <fresh-v9>
```
复现检查history/VERSIONS.json固定identity。主版本为v9，历史v7仅owned runner不同，v7/v8使用标记前Spec。独立生产91-source目录来自已固定默认关闭QKV候选：71 Scala +20 HardFloat；不复用其他候选Host源码。

`run_protocol.py` 的 --execute 会实际编译、emitCHIRRTL并启动Treadle；没有新批准不得再运行。依赖只使用106-jar lock的显式6 removal/25 addition，不合并旧87全部classpath。包内没有jar/classes/weights/raw日志/大IR产物。

## 边界
- 实际 HostBlockCommands + Public21QkvReductionRouter + coordinator/bridge，服务为metadata/有限sentinel脚本响应。
- resident只覆盖所有权请求/返回；kernel五项物理债务未实例化。
- 正确的功能基线并不满足性能目标：原Attention约48.2% ideal上界；完整有效MAC利用率90%目标不变。
- 后续编译后端方案见 COMPILED_BACKEND_PLAN_CN.md；当前工具不足，未安装或运行新工具。

## 纯源码分发后继

本包不携带6个command.bin/descriptor.bin，也不以base64或文本编码替代。固定发布的public_dispatch/generate_contract.py从真实metadata recipes生成Command128和descriptor，再逐字节核验原10文件FIXTURE_PINS（包括原gate/3manifest及6个二进制表）。原manifest/gate/hash不变。

先运行 python -B generate_fixtures.py --source-root <已发布仓库根> --out <全新fixture目录> 可独立生成；该脚本执行的只是metadata/control模型，无权重或算术运行。

历史重放入口改为 python -B reproduce_sources.py --version v9 --source-root <已发布仓库根> --out <全新目录>。v7/v8同样可用；重放会生成并核验fixtures。不要直接从未物化fixtures的源码包运行历史硬件launcher。

源码冷测不要求预先存在binary，只检查metadata与6个预期table pins；实际生成/完整hash验证单独执行，不能把源码冷测称为硬件PASS。
