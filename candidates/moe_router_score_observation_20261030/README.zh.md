# TEMP：MoE 全概率只读观察联合候选（未选用）

本包为隔离源码/patch与证据；active `7bb6641b1d07aa4f83ffab1d37aff2d905237db7` 没有选择此观察硬件。不得改active pins、删除旧canonical/ABI门禁或转移旧PASS。

## 内容与精确基线

依赖已发布 `candidates/p0_resident_observation_20261030`（commit `feafbd6d492da76923d23c6cd5dcd9c5e836ad0d`）。四个Scala增量中Top基于该P0版本，保留residentObservation；其他三个基于原fixed155真实选源。driver只提供相对P0 driver的精确patch与新header，不复制大driver。所有base/result SHA、repo路径和commit见 `BASE_AND_RESULT_PINS.json`。

consumer guard基于7bb的 `00bac8ae…`，**不得覆盖P0 consumer `c482295c…`**；二者尚未合并，也未接通raw-score数值比较。官方wrapper patch基于已发布 `805a31aa…`。本包的相对路径/hash可复建源码，但不是完整runtime/toolchain；官方model源需从固定Transformers revision/archive恢复并验证 `ea77a397…`，不是仓库内假造文件。不包含唯一local-only base或声称无需外部依赖。

## 观察语义与不变量

实际 `selection.in.fire` 的score是BF16 Dense logits精确扩展后，经原FP32 max/sub、P7 ExpNegative、stride8累加/升序collapse、reciprocal Div及独立MulIeeeRne形成的softmax概率；不是原始logits。transaction/owner/profile来自实际保留command，token来自计数，expert/score直接selection输入。合法Loop入口明确仅P3/P4；Valid没有伪造profile过滤。

只增Valid-only输出和转接，无ready、无算术/路由/调度反馈；原同分小ID实现不构成用户批准，不改PyTorch topk基线。host collector严格token×expert序列32768项、同身份、live/no-fault；clean terminal与末拍静默（含raw valid）后才写131072B。采满不是数值通过。

官方observer在同原code/实例return事件只保留真实router_probs引用；不重算softmax、不替换forward/topk；退出profiler后验证保存。baseline输出/cache逐字节相等门仍先于新参考保存；初始化先于hook注册，异常冲突保留原异常。7项轻fixture/AST测试不是真实Torch或M128参考结果。helper必须进入实际source pins，参考只在reference_only，绝不成为DUT输入。

## 已执行与未执行

联合155源+P0/MoE覆盖完整字节码编译实际native0，118.871542250秒，observed RSS1574649856 B，862class/17967658B；cleanup-before-reap、EOF/gzip finalized已核。仅编译，非数值或SV。详情见证据JSON。

联合IR session84990环境重连后无终结RESULT/官方LOW：**INCOMPLETE/观测不可用，不继承PASS，不据此说任务已停止**。新225bits/7ports、总119ports均为源码预期，不能继承先前P0 LOW实测112口资格。

完整M128五块数值 **0/5**；最终RTL数值 **0/5**。无SV、DUT、PPA或90%利用率证明。原consumer整体原本已INCOMPLETE/exit2；guard只把MoE已比较子集与缺失scores分开，不是声称发现全局伪造PASS。

## 复建与轻测

在包含上述精确base字节的已验repo上：
```
python -B materialize.py --repo "$REPO" --output "$FRESH_OUT"
cd "$FRESH_OUT"
python -B test_profile_coverage.py
python -B test_tap_source.py
OFFICIAL_MODEL_SOURCE="$PINNED_MODEL_SOURCE" python -B test_local_observer.py
python -B tests/check_driver_syntax.py --repo "$REPO"
c++ -std=c++17 test_raw_scores.cpp -o ./moe-score-test
./moe-score-test
```
`materialize.py`只向不存在的新目录重建经base/result hash验证的副本，不修改repo。运行官方wrapper还需原profiles/stimulus/acquisition依赖与完整pin链，本包未安装这些内容。打包后实际在临时新目录按7个base/result SHA重建成功，并重跑16项轻测（5 consumer guard、4 source/terminal、7 observer fixture/AST）通过。未在打包步骤执行C++或Torch；mock header不构成真实ABI。

不包含IR/class/tensor/weights/raw logs/机器本地绝对路径；未做远端发布或临时数据删除。
