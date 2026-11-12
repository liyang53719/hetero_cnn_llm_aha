# 17:33 环境回退后的独立修复（执行闭包缺失，INCOMPLETE）

环境由starting恢复ready后，1033–1633全部目录缺失。现存原155源、860类、5补充jar逐hash匹配，86253732B FIR SHA5053dcbd81e4c7cdc24758d773229a52088096590c4da6f87f9521b2573593be匹配，无需重编Scala/elaboration。但官方1.163工具、strict/typed适配、LLVM/object、17库、driver、冻结参考和数值证据当前缺失；16:33成果仅历史报告，不能继承为当前可执行PASS。未重复启动未知旧Host。

实质源码修复：从现存Qwen2源码恢复入口，BF16舍入前拒绝原FP32 NaN/Inf，避免payload被舍入掩盖；增加Dense形状检查、CPU软限以及ACTIVE/STOP记录和保留receipt。13raw与源hash重验，8类receipt反例、3非有限值反例及小Dense差分通过。未全重算参考，完整21-op参考/冻结/flags仍缺。

现存73项native源码pin全部匹配，包含真实Matrix/ICG适配器。旧gotFinish失败仍保留evaluated的缺陷确认存在，在1733副本修复，原pin不改。直接抽取候选eval函数的最小C++测试正常、gotFinish、异常、ICG非法输出失效均exit0；人工Context/Dut函数单测，不是真实库/RTL重测，不继承1533 PASS。仅fixture tc_clk可见，不能冒官方源。

真实raw重新完整hash通过：Qwen2 13张94382080B，0.8B L0 14张43111008B，L3 11张36705280B；三程序生成源码身份仍在。新增最小只读raw reader及3局部测试，不冒Host地址桥恢复；35B两块仍缺payload，不重试受限下载。

main84898eb9及CI43260095362 success已核，仅payload门禁。本轮无活跃Host/完整block数值进展，五块128原Chisel仍0/5，最终RTL及固定4096完整block有效MAC80/90%未测，L0原head4 FAIL保留。下一步需恢复丢失的许可执行工具和适配源码并重测，不能靠摘要拼出PASS；已避免重复大下载/全构建。工作树干净、临时清单保存、清理0。仅允许摘要/hash发布，不上传受限源码、原日志、IR、权重或生成数据。

补充实做：从精确原FIR恢复105条真实assert身份提取，保存clock/predicate/enable/message literal/source及嵌套when/else，6项解析/拒绝测试通过。仅CHIRRTL身份映射，未恢复lowered callback或运行资格。
