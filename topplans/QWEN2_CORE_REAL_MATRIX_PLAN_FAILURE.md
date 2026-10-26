# 真实 Matrix 层次计划：FAIL / 数值阻塞

实际 plan-only 在 **2 GiB 采样 RSS 门失败**：2,148,995,072 B，超额1,511,424 B；plan为空，后检未运行，原组 cleanup闭环。详见 [`失败摘要`](../candidates/qwen2_core_real_matrix_plan_failure/README_ZH.md)。保持当前 FAIL 和所有旧 FAIL，不把 source/mock PASS 当作实际 plan/硬件通过。

CPU 只能分别报告已观测 sampled group+parent **20.50099467 s** 与原 final waited-child口径 **2.045371732 s**；后者不是总 CPU，完整最终成本未知。48 TIMESCALEMOD 是中止前日志，不能改写首个 RSS 中止原因或认定无害。

**阻塞仍在：无层次 plan / 无 provider 数值 / 非零 M1 未运行；full128 RTL、full29、90%有效 MAC 未完成。** 不猜具体编译阶段，不自动增加预算或 warning 抑制。下一步先审源码/监督口径修正与新的有界方案，再独立批准；本批没有新执行候选或 GO，canonical todo/ongoing/done 不改。
