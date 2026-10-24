# 下一片：正常加载源码绑定补测（尚未执行）

当前独审和四模式 PASS 只针对 AST-definition fixture。即使定义 AST 来自相同源码，CPython 3.12 对模块 import 名称的调用编码也会不同，不能用此证据替代真实 runtime 绑定。README 的正常模式为 TEMP。

最小补测不需要先跑完整 block：

1. 使用 R2 已验证的独立 assembled source，重新验证 source manifest 全部 hash 与 observer 七角色 pins；新 manifest 增加 observer/capture/SOURCE_PINS 及原 buffer，不修改 R2 已冻结 manifest/账本。
2. 在新的隔离 CPython 3.12 进程，只从该根正常 import `ffn_attention.attention_owner`、`production_qk16_model.schedule`、`production_qk16_model.ordered_work`、`attention_packed_owner.client` 和旧 capture。复用 R2 harness `run_owner` 使用的真实 import 链，但不调用 run_owner，不构造 MatrixService，不 configure_library/td_reset/CDLL，不接受 job，不读 tensor/reference，不运行 arithmetic/native。
3. 对正常 import 得到的七个 class method 和四个 buffer method 使用 `bind(..., ast_test=False)`。逐项核对 __file__/co_filename、完整文件 hash、完整模块编译 code object、line table。捕获完整 import module 路径与 hash；任何未知 import/prelude/compile/native-load 意图立即拒绝，不用测试 alias 或修改源码替代。
4. 负例包括一字节文件漂移、同源但错误文件路径、缺角色、同方法名替代 code、AST-definition alias 不得通过 normal 模式。每进程 -B，1 CPU/256 MiB/20 CPU 秒/25 wall 秒；先静态检查 import 顶层副作用再执行。这只能升级 normal-import/binding PASS，仍不能升级观察器 runtime 数值 PASS。
5. 该小片通过后才准备 observer 实际真实 owner 的独立受限数值 profile：真服务初始化/ELF加载许可、源/运行时/输入闭包、映射、terminal 后十字段独立参考对比、唯一 attempt、精确 config 独审。此项不是当前已执行操作，也不允许把组件输入当 fullblock输入。

完整 M16 另外还需要新 suffix pc12 direct dispatch、全部 prefix/suffix/operator 控制链与数据中间值观测/准入；不能用 import 成功代替数值运行。README 的约63.57%仅引用父层固定 MAC slot 独立分析，不由这26项测试得出。
