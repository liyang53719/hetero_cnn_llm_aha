# 共同命名空间 B1：固定新 A IR → 单文件 SV，未执行

输入为独审通过的 collection A：IR 39,466,374B / db430673f18166b3ce7c8703251b881d5446f71d70ddb29077f004a1db3599ba，receipt 86cd18077090e686991d81fe6a06497b29362ed6f6f3bd24cdac5a838ac55979。原95源、557+4类；不混旧namespace IR，不重跑Java。

沿已实际生成69MB SV的 v7 原 runner/owned/strict/leader sampler，预算180总/150工具、单CPU/AS2GiB/file128MiB/tree256MiB采样softcap/log2MiB、2048采样；优化/preserve-values/randomization及verbose不改。原输出上限依据文件仍保留为历史背景，当前共同输出大小未知。父Python checker无AS硬限（原已披露），全部后验仍受统一deadline。失败不自动扩门或重试。

仅固定firtool1.62.1生成 ProductionQk16KernelCollection.sv。check_sv使用已审offline v8的instance span修复、唯一module/受限无条件直接实例语法，仍拒if0/generate/ifdef及未知形态。目标资源仍从 ProductionQk16KernelBench遍历，核8endpoint/8clock/1iDMA；容器必须有精确Bench+4FMA兄弟，四FMA不得出现在Bench子树。四FMA原顶层名及方向/宽度逐项对已审PORTS固定schema，全文件module定义唯一。新增fma_ports直接复用已审四组件parser函数。

这一库存是词法/固定直接实例形态证据，不是通用SV语义证明；外部端口表达式宽度、provider参数真实展开留B2。四FMA兄弟IO保留靠原source/dontTouch和固定firtool，B1核声明/兄弟存在；不声称任意端口连接功能已证明。FMA内部helper可被工具共享或改名，不要求原重复的helper名字保留。

建议命令（需root单次GO）：
python -B production_qk16_kernel_collection_sv_plan_v2_20261017/run_sv.py --ir production_qk16_kernel_collection_structure_attempt_v1_20261017/structure/ProductionQk16KernelCollection.fir --receipt production_qk16_kernel_collection_structure_attempt_v1_20261017/receipt.json --firtool production_qkv_native_tools_v10_20261017/firtool --out production_qk16_kernel_collection_sv_attempt_v2_20261017 --execute

后续B2另外审：308固定provider源（312减4独立FMA）+共同SV=309；保留tc_clk一次及原8incdirs/profile，lint --top-module ProductionQk16KernelBench。本轮不Verilator/lint/native/sim。未来动态直接消费同一SV资产，不Chiseltest独立重发。

V2 仅补原 Bench 全端口 schema：从旧实际69,464,271B/SHA93fe8475… SV提取完整 directions/widths，在共同输出中逐项相等检查，防止根变子模块时接口被优化。生成源/优化/预算不变。
