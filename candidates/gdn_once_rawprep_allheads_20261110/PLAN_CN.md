# 单次 RawPrep，同实例全head：明确数值契约失败

- done：heads2同实例合成边界数值PASS；新SV哈希04d2e5ca765453ccbceab995022c979a694f62585c101d4fc0264c1546d58a74。
- done：同一SV全16回归实际执行，一次RawPrep后head0–3各两chunk及export通过。
- FAIL：head4、chunk0、phase7在cycle23,785,058返回Numerical status8。exit1，wall620.24s，无超时；此前写比对未发现不一致。未重启昂贵作业。
- done：独立参考首个tiny+inexact乘法位于row59/colbeat0/k2/lane2：0713e498 × b8009900 → 80252558。原bank短诊断实测policy0产生flags3/error=true，policy3同一数值flags3/error=false。
- blocker：原HostRuntimeChunkProtocolV9将n16映射LegacyFatalUnderflow0、n32映射FiniteGradualUnderflow1；参考保留subnormal。原16head契约对该输入拒绝是实际行为，不是算术结果不一致，不能静默切policy后冒原契约PASS。需明确是否单独评估既有gradual运行契约；不改算术、舍入、FMA或MoE路由。
- todo：契约明确后继续全heads及真实投影/完整block；完整五块128仍0/5，最终4096MAC/RTL/利用率均未通过。

完整16状态从INCOMPLETE更新FAIL。短bank诊断不是完整数值通过。所有临时数据保留，无删除、无NPZ/权重/TSV上传。旧PID40532仍EXIT_UNKNOWN未操作。末行静态vector/format计数是per-head标签，合计只按实际完成head计算。
