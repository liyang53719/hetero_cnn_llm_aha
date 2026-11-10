# 原 RawPrep 到 GDN 两 chunk 的实际数值链

- done：原 RawPrep 16 heads、128 tokens 的真实写回与真实完成/排空结果，接到 head0 cold initializer、phase1–17 两 chunk 和最终state exporter；逐写比对通过，共1,263,616个32位字。
- done：单一共享scalar及Vector bank，不新增第二套算术。prepared区域初始为空，后续读取断言来自实际写回。测试经Chisel发射SV并Verilator执行，不能称纯解释模型。
- done：首次240s预算到限，chunk0结束且chunk1到phase4；标INCOMPLETE。按联合工作量调整600s/CPU480后同硬件SV哈希重测exit0，286.41s。首次缺HeldDecoupledOffer编译依赖已补原源码。
- ongoing：全部heads尚未跑完；支持--head运行配置0..15，不改变硬件定义/容量。
- todo：覆盖其余heads，连接原投影/完整block，五块同一4096MAC模型128数值后冻结并同刺激RTL。

精确PASS范围仅合成Conv/QKV/AB原始边界下head0两chunk链，不是训练权重完整block，不是生产Guard/lease authority，不证明物理32-lane或4096MAC利用率。五块完整128均INCOMPLETE，0/5；无80%或90%实测，不迁移旧PASS。原RawPrep结果缺完整generation字段，当前cold generation0的scheduler包装receipt来自真实结果及稳定context。

无临时清理，保留首次超时证据。复现自行生成TSV，不上传权重、NPZ、TSV或生成RTL。--head参数须生成和仿真一致。
