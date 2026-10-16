# U00.2 原始 Public M128 云端实际运行：内层预算失败与下一步

## 结论

2026-10-16，唯一获准的云端原始 Public M128 运行在固定 commit `be00eb8e4bc75e2e41f2a434d05d4c901ed3faa5` 上结束，退出码1，安全summary为 `FAILED` / `numeric`。总耗时2762.816418秒，未完成数值比较或postflight，没有Public数值PASS、RTL通过或90%MAC利用率证据。

本次明确定位到原始2400秒内层执行预算：`ffn_public/execute_numeric.py:109` 在Public FFN Host边沿检查绝对deadline并抛出ValueError，经同文件427行及 `ffn_drain/check_numeric.py:39` 上报。它不是之前CI的外层2430秒TIMEOUT，也不是已观察到的数值误差超限。没有加预算或自动重跑。

## 实际证据

- 原始safe3JSON逐字节保留：summary1960B/SHA256 `0a6764b46df7f5c5e798f3e491bda3d8ad594cf8b17294fdf68ce8bc8af99be8`；progress79B/SHA256 `d48207e852bdac9e6b946329cee952ea2cf3d2569e60d583589c3467255fc951`；source_hashes39690B/SHA256 `99d4548f9e20edde2f2d42d36848ad25996fa1aae9e44025a403ffd27304ab28`。
- launch contract为 `b4ea311e11a64695fba4ccfc1f512240ddccdbada99710d58a1a36dbe5d1d96b`；原始285源、12个严格生成变体；运行时源manifest为 `9d1aa25d2f76aea864c86dbfa7cfc3a724cb2e6bafd2c8f8158d19937f057f33`。
- 冻结context为 `5864b89dd54542f0b64abb15c44df314a78cc1009ac3785d3b8854433f6cf241`；原始900/2400/2430/3420秒预算不变。源/runtime/context均在终态后重新核对。
- fresh环境、固定revision的94,382,080B载荷、双reference、native16/native128、library与seal后，setup返回COMPLETE_FRESH_SETUP，记录335.069335秒。本次setup完成不能代替后续Public数值验收。
- 最后源绑定的原子进度为sequence61，`actual_execute/ENTERED`、`public_suffix`、FFN PC16 REQUEST；writer elapsed2273.228089879秒，phase elapsed2261.354416201秒。接受计数：request15、owner_result14、completion16、result0；Host model ticks18,941,741。
- 对私有失败报告做严格有界标量投影：实际执行host wall2400.210057941秒，prefix完成82.376933662秒；最终Host model ticks19,929,718，接受计数仍15/14/16/0，完成PC连续0–15。Attention已推进，未完成的是包含FFN PC16在内的剩余后缀；不能把最后快照当作精确停止时刻。
- 私有失败报告仅留大小309466B和SHA256 `a58d7b3133bfc55012a2cccfba8dbd40a3760b3e11b17833a0ee1636ee8b3b13`，不提交其内容、权重、数组或私有日志。

失败checkpoint及冷验证位于 `candidates/qwen2_resident_matrix/raw_kv_public_recipe_cloud_failure/`。离线测试验证归档字节/字段/source身份和无PASS继承，不会重新执行模型，也不把自述元数据当成独立外部认证。

## 时间与计数边界

writer、actual_execute阶段和实际Public内层timer起点不同。当前留存材料不足以给出精确Attention-only时间或精确FFN剩余预算；早先把2400减phase elapsed得到的约138秒，只是不同起点的粗差值，不作为证据。不能把本次路径耗时与旧不同commit/源闭包/CPU结果直接作性能回归比较。

Host计数是软件模型已接受事件，不是RTL周期、物理资源数量、有效MAC数或墙钟利用率。数值comparison未执行到终态，故既不宣称数值正确，也不宣称发现数值不一致。所有Public acceptance/postflight/full29/RTL标志保持false。

## 中文计划与检查清单

- [x] 两次不合格CI CPU placement证据单独归档，停止随机换VM重试。
- [x] 在合格云CPU上执行一次原始完整bootstrap/fresh setup/Public路径，官方包与固定分段载荷留在私有venv/workspace。
- [x] 保持原始预算、backend/dispatch/source/数值gate；保留安全终态及源绑定阶段证据。
- [x] 定位原始内层2400秒deadline在FFN Host边沿失败，确认Attention已完成推进；没有Public PASS。
- [x] 独立审查本次失败checkpoint与冷测试结果：47项测试在普通/优化、discovery/package四种模式均通过，另179个恶意变体及source/runtime角色互换均被拒绝；证据候选已保存，待协调者发布。
- [ ] 下一步沿已审查packed数据通路的Public集成减少Python边界/逐包调用等软件开销；先做有界语义与事务等价验证、源身份/资源约束和独立审查，再申请一次明确资源计划的整链路验证。
- [ ] 不采用仅扩大预算的重跑；不绕过原始数值、backend、source、吞吐或硬件资源gate。
- [ ] 三个目标模型的典型block、固定batch1/M128、实际RTL及有用墙钟MAC利用率90%仍是最终目标；本失败证据不关闭这些验收项。
