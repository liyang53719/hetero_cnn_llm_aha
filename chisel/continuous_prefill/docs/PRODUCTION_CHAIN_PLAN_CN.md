# 共同生产执行链开发计划

基线：cd144f38508358303f2445ee893efb18403a0a99。该基线的 real16 通过范围是合成权重、16 个 BF16 FMA lane、内部 MemoryRequest/Response，不是原512-MAC/Command128/pinned-iDMA整链。

硬件源只修改 Scala/Chisel。保留旧通过配置、生成产物、失败日志和 checkpoint；后续构建使用新目录。不创建新分支，不 force-push。

## 本轮顺序

1. 将 RetainedMatrix 的 Dense 映射从单行16列改为完整16行32列。Dense、QK、PV必须共用一个原 Revision8B endpoint，不得重复实例化阵列。保持每个输出递增K的FP32 FMA顺序，统计有效MAC与实际阵列MAC分别计数。QK/PV初期允许低利用率映射，但不得称为性能完成。
2. 用真实保留RTL验证完整tile、列/行尾块和多个K步骤；再把相同路径放入15阶段连续block，逐阶段读取DUT实际DDR输出比较，保留毒值、写回ACK、错误隔离检查。
3. 按现有Command128字段及typed descriptor合同接入共同入口；不能把内部构造的matrix command说成host graph已经接入。明确是否经过实际descriptor fetch。
4. 接入锁定版iDMA：只在真实backend发出并完成AXI读写后返回MemoryResponse。直接AXI适配器不叫pinned-iDMA；缺少上游依赖时单列阻塞，不能用stub结果升级验收。
5. 在同一固定输入和精度合同上复跑real16；最后保存源码/工具/生成RTL/输入身份、全量阶段结果及执行命令。随后才扩展q1024、多层、官方权重和两个新模型。

## 独立验收等级

- 原512阵列完整tile数值通过。
- 原512阵列上的完整block连续数值通过。
- Host Command128/descriptor路径通过。
- 实际pinned-iDMA路径通过。
- real16生产整链通过。
- q1024整网与800MHz DC另行验收。

各等级必须有单独原始日志和被测源码身份；上一级的通过不自动提升下一级。仅规划或启动测试不得记为PASS。

## 本地执行职责

本地agent只复核指定提交、执行已经给出的固定命令并返回原始结果，不修改代码、数值阈值、模型尺寸或参考实现。开发侧负责所有接口适配与失败修复。
