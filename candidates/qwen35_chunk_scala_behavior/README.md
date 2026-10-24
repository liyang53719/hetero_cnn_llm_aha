# 真实 Scala AddressPlan 行为资格公开摘录

独立实际复核：PASS_ACTUAL_SCALA_ADDRESS_PLAN_METHOD_EVALUATION_ONLY。本包只是源码与有限状态摘录，不是独立可执行闭包。

## 内容与身份

- source/GdnChunkAddressPlanBehavior.scala、run_behavior.py、launch_behavior.py 保留冻结候选精确原字节。没有修改测试或监督行为。
- 两份生产 Scala 已在 db4977f 的 candidates/qwen35_chunk_contract/source/ 提交，本包只引用，不复制。阶段一仅编译新测试源，引用原 27 个生产 class，不重编生产源码。
- INPUT_PINS.json 只用相对逻辑名称及 bytes/SHA-256 描述 354 项冻结输入，共 297406220 B：314 工具、6 监督辅助输入、2 生产 Scala、1 合同 manifest、27 原 class、3 先前编译证据、1 新测试源。原 class 共 124993 B，只有摘要，没有 class 字节。
- 87 个固定编译 classpath JAR 是 314 工具的子集，不能重复计数，也不声称是最小依赖。行为 classpath 恰为新测试 class、原生产 class、Scala 2.13.16 library 三项，唯一 JAR 是 Scala library。
- 先前编译 OUTPUT_MANIFEST、RESULT 与 ACTUAL_REVIEW 只列 pins，不含原始内容。工具、支持文件、生产源码与 manifest pins 复用已有脱敏元数据，并与新冻结计划元数据逐项核对。
- ALLOWLIST.json 限定恰好 9 个公开文件；MANIFEST.json 校验其他 8 文件，自身不自哈希。不得递归发布父目录。

## 已复核的实际结果

唯一实际尝试顺序完成两个 JVM：编译阶段自然 exit 0，行为阶段自然 exit 0。两阶段均有 WNOWAIT code=1/status=0，已回收、进程组 absent、cleanup confirmed，未超时。kill_attempted=true 是已观测自然退出后的原进程组清理，不能误称为超时强杀，也不能删去此事实美化结果。

实际 Scala main 输出 PASS_SCALA_ADDRESS_PLAN_BEHAVIOR_ONLY。161258 是 check 辅助函数的动态断言求值次数，包含循环中重复求值，不是 161258 个独立测试案例；1090 是预期拒绝辅助函数调用次数，13 是具名检查组数。以上数字均不代表完备覆盖。

新生成 2 个测试 class，共 76713 B；封存输出 21 文件、785301 B，均不收录于本包。354 项输入前后完全一致；阶段中间只复核原 27 个生产 class 与新测试 class，不声称中间重新 hash 全部 354 项。最终两套 class 未漂移。独立解析的 class-load 记录有 1330 个唯一类，5 个必需类存在且来源精确；4 个硬件 Bundle 类及 chisel3、firrtl、circt、hardfloat 包均未加载。测试还直接检查真实生产对象及 Plan 等纯 Scala 类型的 CodeSource。

编译阶段内部计时 9.92845 秒、行为阶段 0.945938 秒。launcher stdout 内部总计时约 11.517577852 秒（保留 9 位小数）；RESULT 内部计时为 11.517333194 秒。两者测点不同，不是摘录制作方独立测量的外层 wall time。

独立实际复核摘要：13606 B，SHA-256 33bec671116fd6af252f718454f06da41837c6e397606dd5cd82a99858a10eeb。terminal RESULT 摘要：32745 B，SHA-256 5a97bbb4fdc47e4c4de471f9d8406e6e826ef733e89160e0eb33a458103da794。仅公布摘要，不公布原始收据；摘要不能替代完整原始证据。

## 结论严格限于哪里

本次直接求值真实 Scala AddressPlan/Geometry/VectorPolicy，覆盖 M16/M128 容量、24 个矩阵固定 offsets、head→initial→chunks 存储次序、63→64 行边界、padding 地址拒绝、状态 FP32/输出 BF16 地址末拍、56-bit 完整端点、对齐、五 span 十组两两别名、cold/warm/root/generation 与策略、阶段 predecessor、声明字节义务。

expectedAckBytes 只表示 Scala 返回的字节义务，不表示任何实际传输、ACK 或握手发生，没有新增 MockACK。FP32/BF16 检查只涉及地址布局，不证明 GDN 数值运算。纯 Scala Plan 等对象确实被构造；硬件 Bundle/Module 未构造，Chisel 未展开，RTL 未生成。

真实 ACK/握手、GDN 算术、硬件 chunk64 prefill、完整 block、利用率资格仍全部为 false。五个 RTL 目标仍为 0/5；旧 Qwen2 full 执行及清理状态仍 UNKNOWN，不继承任何先前 PASS。

## 两阶段入口模板的限制

REPRODUCE_COMMAND.txt 是接收方显式提供变量的解释性入口模板，不自动发现、下载或映射输入，不是新的通用 runner，也不是原监督。接收方须独立取得并校验输入，尤其原生产 class 目录必须恰好 27 项。

原 launcher 固定 CPython 3.12.14、隔离标志及未公开的 FROZEN_PLAN.json（187104 B，SHA-256 e96bc944f72aab79227a65ab11826e898f3ad12e15d328be08c52d78cf658c9a），依赖未收录监督与工具。因此两份原 Python 源仅供审阅，不能直接运行。不要伪造替代计划冒充原冻结运行。

模板不实现原 180 秒全局期限、共享 start+150 工作截止、编译最多 120 秒/行为最多 30 秒且均受共享截止约束，也不实现 CPU/RSS/输出上限、输入身份确认、WNOWAIT/回收/清理、class-load 拒绝规则或证据封存。不能把两个阶段预算当独立重置，也不能将直接执行模板等同于本次受监督运行。独立运行需另行审查并冻结输入和监督。

原 Python 源中的 /proc、/proc/meminfo、/tmp 是通用 Linux 接口常量，按精确原字节保留，不是机器私有根。相对 pins 仅是身份标签，不是路径解析器、下载器或执行授权。

## 摘录制作边界

只读原测试与 runner 源码、冻结计划元数据及已有脱敏 pins；没有读取原始实际日志/收据、工具、class 或监督 payload。终态事实及独审摘要由实际复核方提供。只做 AST/内存代码对象语法检查与元数据/公开字节 hash 核验，没有 import/exec 候选、运行静态检查器、测试、JVM 或编译器；没有修改冻结候选或仓库，没有 push。

本包明确不包含原计划、机器根、原始 argv、日志/收据/ADMISSION、runtime/JDK/JAR/class 二进制、数组/权重及任何运行 payload。
