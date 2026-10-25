# M128 终态取值与 oracle 隔离准备计划

候选：`candidates/qwen2_m128_terminal_capture_prepare`。状态仍是 NOT_READY / default-off，仅源码与纯 mock 准备资格；没有 DUT 执行或数值通过。

已完成：原 single-prefix/pc12/suffix 完整终态后透传 x、原 SiLU seal 与真实 RoPE half-domain 操作数；新 oracle-root 拒绝 sticky；联合已审 RoPE r2 和已发布 trace r2 的 bounded retention/清理故障隔离。私有联合独审 SHA 为 `7bb4b3194eaf1b64e0169edff21ba383310e7c260f8ee96664f28eafcb88cc9d`，公开投影另由本候选 manifest 校验。

公开包交付八个原字节 Python 后像、source-only patch/composer、逻辑 source/runtime/provider pins、历史失败摘要和测试证据。基线是旧 composed postimages，不是 raw main；跨片新联合后像不继承旧 M16 运行资格。RoPE 私有 SOURCE_PINS 配置未交付，正常 import 尚不能运行，逻辑模板明确未绑定。

后续必须独立闭合：实际 source/code/runtime/native/modules/maps/fd 准入与新配置身份、完整输入 pre/posthash、fresh 官方32768/rope1e6 M128 reference 终态身份、精确 comparator、预算和一次执行 GO。现有 wall <=1800 上限未抬高。本包不能满足这些执行条件。

原47+11项历史纯mock与12组独审组合负例已通过；公开只新跑6项轻量 stdlib smoke，绝不称原58项全部复现。repeat/logits/mask 不补造，部分因果字段不升格 full29；没有数值无干扰、DUT、RTL 或性能 PASS。
