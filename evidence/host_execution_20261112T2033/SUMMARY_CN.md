# 20:33 再次回退与现存源码有限修复（执行BLOCKED/INCOMPLETE）

等待环境ready后再次只剩0833及更早，1733–1933全部执行闭包/参考/修复/证据缺失。FIR仍精确5053dcbd81e4c7cdc24758d773229a52088096590c4da6f87f9521b2573593be。原54848 owner此前直接观察exit0及LLVM产物，这是历史终态；当前poll Unknown不改变历史终态，也不证明当前可执行闭包，不能重启或继承丢失PASS。

具体修复与新测试：现存inspect_ir脚本默认FIR路径漏json_retry且文本正则会重复统计printf中的assert，候选修复为真实操作行计数及原Top层次展开，实际105assert/17extern，4测试通过。这是诊断代码修复，非Host执行。

现存ICG适配器gotFinish/非法输出/异常后快照仍可读的失效次序，在候选副本修复；直接抽取原eval/read函数用人工Dut/Context测试，分别-3/-4/-5后read均-2。原pin未改，非真实native/RTL重测。

新增只读参考恢复预检，在任何数值计算前检查连续receipt和COMPLETE依据，6类坏链/输出损坏/虚假完成负例拒绝、3类正例通过。当前实际入口0份已执行receipt，明确COLD_NO_EXECUTED_EVIDENCE；这是恢复预检，不是数值进展，未重新全算。

main4ce886ca与CI43291975149 success核验，仅payload门禁。没有重复大下载、全编译或真实参考重算；原未知完整Host不重启。五块128完整原Chisel仍0/5，最终RTL与固定4096完整block有效MAC80/90%未测，L0原head4 FAIL和35B权重阻塞不变。继续活跃Host必须先恢复并保留可靠执行闭包；反复回退使前轮成果无法复用。临时清单已核、工作树干净、清理0。仅允许摘要/hash发布，未上传源码/权重/原日志或绕过拒绝。
