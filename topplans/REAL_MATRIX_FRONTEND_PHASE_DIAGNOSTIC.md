# 原前端阶段诊断：FAIL 保留

- **已完成证据封存，不是目标通过**：本次 2 GiB RSS 门失败，sampled 2,149,695,488 B，plan 空；原 0334 /flat4096 FAIL 保留。
- 新增实际证据是 5 个收到的官方入口标记。最后收到 post_parameter_link_entry 后区间 RSS 上升，但不等于精确当前函数、热点、根因或 profile。
- 586 次调用只保存 120 行＋latest；label 全调用计数/峰值依赖已冻 observer 源，不虚称全量独立重算。sampled CPU 13.467568583 s 与 final waited-child 1.832441821 s 不同覆盖，完整 CPU 未知。
- source/mock 与包检查可 PASS；target 仍 **RSS FAIL/no plan**。0 retained warning/error 头不等完整 lint；原警告历史、未知 transient/fallback 和原资源失败不改变。
- 下一步仅需另审的只读源码诊断；本包不包含或授权新 native 方案、重试、加预算。provider 数值、8×512 fit、full128 RTL/full29/90% MAC 仍未验收；canonical todo/ongoing/done 不变，整体不置 done。

详见 [实际与源码边界](../candidates/real_matrix_frontend_phase_diagnostic/README_ZH.md)、[独立实际投影](../candidates/real_matrix_frontend_phase_diagnostic/evidence/ACTUAL_FAILURE_REVIEW.json)、[五标记摘要](../candidates/real_matrix_frontend_phase_diagnostic/evidence/PHASE_SUMMARY.json)。
