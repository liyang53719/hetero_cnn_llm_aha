# TEMP / INCOMPLETE：R5 仅修复启动身份包装

R4 run 40819601534 在 launch guard 校验阶段失败，原日志明确 profile 期待 VECTOR42，而批准的启动清单正确为 VECTOR32。发布包装脚本全局替换 R3→R4 误改了 VECTOR32 子串；单元fixture同步误改导致漏检。这是发布包装错误，不是硬件故障。未执行 JDK inventory、下载、编译、发射或任何数值测试。

R5仅新增独立唯一workflow、guard和真实两commit CLI集成测试；使用定向替换，独立写死4096 Matrix/32 Vector契约，明确拒绝42/52 Vector及512 Matrix，保留R4失败commit和run。未改底层R4 helper修复、硬件定义、资源约束、工具链、canonical或SV pin。旧job不重跑。新增launch仍需独立批准，source提交本身不会启动重任务。

当前精确状态：本地修复后全部10 helpers仅编译通过；R5云端frontend仍待验证。Python独立参考5/5，五块128-token完整Chisel数值0/5、最终RTL数值0/5；MoE同分参考契约仍待明确。不得把启动契约或编译通过写成数值PASS。
