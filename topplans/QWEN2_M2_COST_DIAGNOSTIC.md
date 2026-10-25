# M2 成本诊断有限结果

父公开提交 e9748f224fc9b29f1e91eedbe2ab13dcab0be137。本片新增 candidates/qwen2_attention_cost_diagnostic，默认不接完整 DUT。原 r2 准备源码/mock 和唯一四臂 M2 实际运行已完成有限独审；公开投影范围见该目录 README_ZH.md 与 evidence。

154 是 77 个逻辑测试身份在两模式的执行次数。原 v1 BLOCKED 和 M128 CPU 超限 FAIL 不变。固定顺序 clean CPU 对比不是 benchmark；count inclusive 时间不可加总，M2 BF 19968 次不是 M128 实测。没有最终独立 seal，off/count outputs 未分别保存，不声称独立再次算数验收。

后续若改监测或缓存，须单独 profile、源码审计与准入，不继承本次结果。无 M128 重跑、无编译/RTL，4096 MAC 和 legacy PV 63.57% 上界保留，80/90% 不在本片验收范围。
