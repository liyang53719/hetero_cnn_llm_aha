# Qwen3.5 allocation guard：主机微优化候选

状态：本批小批提交；metadata冷回归及限定微测PASS，完整模型重新资格验证仍为TEMP_NOT_EXECUTED。基于远端a27fea8866e7f2349f594d19500c0eac8982ebf9的准确导出；full_driver基线SHA256为1f83a81331b59048edfd41487c12b5d6423049935936e67d71b06971298282f2。没有改动冻结run/source。

## 改动与不变项

仅将allocation键集合检查在双方都是exact built-in dict时改为keys-view相等，避免每次构造两个set；其他mapping/subclass走原set表达式。后续逐键对象identity检查、错误信息、guard执行顺序和每tick前后调用频率保持原样。无数值、调度、内存握手、abort/retirement或原生库改动，不缓存成功检查。第一版无type fallback存在自定义keys()覆盖差异，已在独立候选修复，不应采用旧版。

## 当前PASS精确范围

- 可移植冷回归：1个unittest方法覆盖89个确定性metadata场景，normal与-O均通过；包括新增/删除/同数量换键、对象替换、可变别名、恢复、假keys及mapping fallback。测试从实际候选提取完整guard AST，用独立metadata doubles执行，不导入模型或调用native。
- 独立复核：119个场景结果、异常和资源检查顺序与基线一致；包括raising/lying keys、定制iteration、UserDict、MappingProxy及无keys duck mapping。仅metadata等价，不是完整模型数值或异常时间实测。
- 微测：单CPU、256MiB地址空间上限、30秒硬时钟/CPU限额；实际14.728秒，峰RSS18,976KiB。同一确定性映射、每组9轮×10,000调用，原/新顺序交替；只计allocation子表达式，不是整个guard或fullmodel。
- 57-region中位：原7178.263ns/调用，新5555.575ns/调用，约1.292×；tracemalloc临时峰4712→640B，保留增量两者均104B。57来自默认空TypedMemory、两输入窗口的静态分配数，并非新的fullmodel采样。
- 1-region中位比率0.891×，反而变慢；16/128/512分别1.195×/1.276×/1.370×。这是一次主机环境微测，不是置信区间、跨平台保证或端到端加速承诺。tracemalloc数据是短循环峰额外字节，不是累计分配次数。

## 下一步

- [x] exact-dict快速路径及原式fallback；独立metadata审查。
- [x] fail-closed变异/alias回归与有界host-only微测。
- [x] 可移植测试已独立静态审查；按用户既有维护授权和小批清单提交。
- [ ] 本批未启动新完整运行；任何后续运行须另行制定冻结输入、资源预算与验收计划，按用户既有维护授权执行，不修改本次已终止运行的预算。不得继承已丢失/UNKNOWN结果。

持续回归的baseline由候选源码逆替换得到，不能代替本次准确远端历史baseline的独立审查。任意敌对key对象或并发改表不在等价声明内；真实基线使用整数地址键。

没有native/RTL/完整模型执行，没有MAC利用率声明，没有weights或数值payload。旧UNKNOWNrun和冻结运行证据均未触碰。

## 可复现限定微测与持续回归

运行 `python candidates/qwen35_gdn_prefill/benchmark_allocation_guard.py`，结果 JSON 写 stdout。脚本内强制单 CPU、30 秒 wall/CPU、256 MiB AS；不导入模型，不调用 native。候选 full_driver 全文件 SHA256 固定为 e6e5a7c2b45e05f8081bb8d825a1832a0d8038bec7f301ade2c596f236b412c2。旧表达式按唯一精确字节逆替换重建，并记录新旧表达式 AST SHA；这只重建旧 predicate，不宣称重建整个历史源码。历史来源仍由原远端导出审查支持。

可移植脚本新测：15.495 秒、RSS 19,060 KiB。1/16/57/128/512-region 比率分别为 0.866/1.162/1.298/1.296/1.298×；1-region 仍回退。仅主机子表达式，不可推算完整模型或硬件收益。原报告保留，新报告为 PORTABLE_BENCHMARK_RESULT.json。

测试代码已改为正常缩进的可读 Python，格式化前后 AST 相同；normal/-O 各一个 unittest 方法、89 场景仍 PASS。完整模型重新资格验证仍 TEMP。本批未启动新完整运行；任何后续运行须另行制定冻结输入、资源预算与验收计划，按用户既有维护授权执行，不修改本次已终止运行的预算。

进度不变量回归：保留 d68d50143749f73d3c8c098953d4906216c0e7b5ebaca196bdc48d107cbb63ad 历史 fixture，只对唯一原位 allocation guard 的第一个 operand 做精确 AST pin 归一化。identity all(...)、其余 guard 和所有其他方法仍整段比较；不把 _check_resources 排除。新增四个测试方法覆盖 pin 篡改、六种未知 predicate、七种缺失/重复/换位/畸形形状、三个 operand 之外变异。两个冷测试文件合计 normal/-O 各 25 方法 PASS，非完整仓库或模型验收。

本批最终清单包含生产单表达式、两个冷测试、可运行微测、中文计划及两份小型测量摘要；既有历史 fixture 不变、不纳入新增发布文件。CI 自动发现新增 test_*.py；本次已修复原进度 AST 测试对新 guard 的明确一项冲突，无需放宽 runner 或修改冻结 run pins。计时范围包括 key 比较及后续 identity 扫描，不是纯 keys-view 比较。
