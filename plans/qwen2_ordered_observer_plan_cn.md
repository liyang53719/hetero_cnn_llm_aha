# QK16 有序 fold 观察器最小片

父提交：039bef44e37062e317af705ac8569db9809d7e3c。

1. 复用已有十字段 buffer，不改冻结生产/owner/work/旧观察器。新增源码绑定监控，仅监听实际 owner、schedule、work、consume 和 client。
2. 严格区分投机 scale 与 score append 后已提交前缀；按 legacy PV 的八次真实概率复用计数，不能由一份参考值复制补齐。
3. 终态封存要求全部有效中间值、尾部掩码、每个 work 的 ACK/done 和 owner terminal 清债。原 done 后去除结果对象强引用，观察失败不改变 DUT。
4. 先完成 CPython 3.12 有界纯软件正负测试和独立审查。当前 fixture 使用真实定义 AST 和 scripted endpoint，绝不是新 native 数值或 RTL 执行。
5. 下一批再处理真实 source-loaded 模式与完整 block suffix pc12 dispatch、新 profile/admission、输入/工具/参考 manifest。不能修改旧 observer pins 绕过守卫，也不能复用历史 PASS 充当新运行。

交付与精确边界见 [候选说明](../candidates/qwen2_ordered_observer/README.md)。本批禁止 native 重编译、新 native 执行、M16/M128、Chisel elaboration/RTL/EDA。完整固定资源利用率证据仍 TEMP。
