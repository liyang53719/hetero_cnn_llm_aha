# P0 共享 Vector32 authority 反馈修复：局部真实证据

旧 helper 的当前 authority.currentFault 包含 adapter 自己的 malformed/overrun 故障反射，再用于抑制同一个请求 valid，形成组合环。小边界 fixture 连接真实 adapter、两实际 lease helper、真实32-lane bank及原 scalar；仅 Guard/owner 元数据由 testbench 提供。

- 同一官方 Compiler.toLowFirrtl：旧 helper native1，真实 CheckCombLoops 报环；新 helper native0，无检查禁用。
- 新 helper 仅移除当前反射项，在已有 owner 生命周期内寄存 poison；其他独立故障仍立即阻止首次发布，已 held 请求不撤销。
- 原9协议case仅改fixture名，断言未改；实际 Chisel→Verilator 局部回放 strict0。此处不是纯解释器，也不是完整 HostTop/五块 M128 数值验证。
- 已发布 c50e 的远端 original_high 子异常没有导出，本地精确重现不追认其原缺失异常文本。新增有限诊断另由构建器保留。
- 保留旧源/旧失败证据，不上传 rawlog、classes、IR/SV、权重或参考。SAFE_EVIDENCE 记录实际闭回执和源 hash；旧低级失败不是数值 FAIL，新局部通过不是数值 PASS。
