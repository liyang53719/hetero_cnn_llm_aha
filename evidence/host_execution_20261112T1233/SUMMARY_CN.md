# 12:33 完整参考值冻结与真实Host编译边界

现场1133保留。原72018确认exit0，完整21阶段/22输出、源码、13真实raw/转换身份及trig本轮重新校验，无重算。参考身份400a81dc6e1128101d24f625402a9fbef288f4722fea4f0dc81a328f14073139；最终y SHA cbda6ba00853708fab397dadafbf731b29a8b134f6d9f6541e6b7a5fce6f6cb5。仅参考值冻结，不是硬件资格。flags边界测试发现core.mul允许最小subnormal×0.5归0而ops.mul fatal；最终/保存输出有限不证明中间无UF，完整flags仍未通过。Host只允许原始输入/trig，禁止预载参考中间值。

真实整Host strict IR Arc尝试70721失败于Matrix needsClock→ICG→ready反馈环，已通过新DPI语法，不以常量ready伪消环。实作17同ID sink/source typed分离绑定，修复两次DPI输出语法错误并保失败证据；当前共享真实handle注册/稳定迭代/真实包装未实现，snapshot契约不证明state-only，禁止执行未完成闭包。

原四段FMA生成及真实Verilator原pipeline编译/有限运行全部exit0（70536/47385/77642）：1×2+3=5、flags0，停写保持3周期，reset清零。仅单lane必要依赖，不替代固定8×512/4096；匹配rev8b数组源、官方ICG/iDMA、shared17仍缺。

0.8B两层真实14/11源张量hash重验，16/13段只读输入实际恢复，原17/22命令及views/roles/binding已交Host线程。地址读/只读写拒绝/越界缺映射4测试通过，仅输入桥；L0新padding单列、原32B不改，head4 FAIL保留。35B限制未绕过。

五块M128完整原Chisel仍0/5，同刺激RTL未过、4096完整block有效MAC80/90%未测。原未知Host不重启。开工main739c666b，CI43210893506success仅Git门禁。工作树干净、临时清单保存、清理0。仅允许摘要/hash发布，不上传源码、IR、日志、权重或生成数据。

42253已由原身份收终态：shell exit0但真实Arc exit1，不能报成功。修正split后越过反馈SCC/语法，后续因array<1xi3/i16>被scalarize而hw.array_concat要求array失败，无LLVM输出。未启动更多长测。下一步需最小等价证明窄数组lower兼容转换，再核真实native稳定迭代，原错误完整保留。
