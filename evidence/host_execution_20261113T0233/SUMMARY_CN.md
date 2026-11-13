# 02:33 匹配工具与真实native执行恢复（完整prefill INCOMPLETE）

先核main88ac3fee和CI43346392322 success，仅payload门禁。工作树干净、临时清单已核，清理0。上轮收束后确实无持续长作业，本轮已实际执行，不把派单当运行。未重启未知旧Qwen2/L3 Host。

原37491恢复官方CIRCT1.163固定143163743字节包，SHA核验通过。首次Arc因1.62的sv.ifdef字符串语法失败；96164窄语法转换后发现procedural sv.error跨版语义不兼容。没有删断言换通过，改用1.163直接lower原候选FIR，57296 exit0，保留105原断言。22308实际Arc解析后暴露Matrix/ICG needsClock反馈SCC；新17577已启动17 typed source/sink分离候选编译，真实ready不改常量、同handle状态仍需native绑定。快照时在途，不报编译PASS。

官方Verilator精确pin恢复，真实官方ICG库46096构建exit0；8独立真实handle的未eval销毁、未eval read/clock拒绝、enable/disable高半周期保持测试通过。lib SHA819656a9951b068159c6a899af5b76135fab6cc77a9bca8ebecaf4412cd874e8。另ICG/iDMA真实CABI字段映射2项传输测试通过，不是DMA硬件通过。

Matrix唯一5606已启动，300秒预算/2CPU/make-j1，完整原512 endpoint供8handle合计4096。原FMA emitter编译6.95秒及四段FMA发射4.23秒exit0，快照时进入Verilator生成，尚未完成C++构建。计划产未资格适配库，旧适配器错误失效守护仍需修复，不冒运行资格。DMA927原导出源码闭包缺失。

五块128完整原Chisel仍0/5；最终同刺激RTL及固定4096完整block有效MAC80/90%未测。Qwen2/0.8B只读输入恢复不等于完整数值通过，原L0 head4 FAIL保持，35B完整权重缺失及MoE契约不变。长任务沿原身份继续，不重复昂贵作业；只发布允许摘要/hash，保留本地原日志与源码。
