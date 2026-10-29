# TEMP / INCOMPLETE：R4 helper 编译接口修复与失败可观测性

## done（精确范围）
- 原 R3 run 40817880119：固定155源编译、原始 high 发射 native 0；helper_compile native 1，原CI只保存569B子日志哈希和SCALA_COMPILE_ERROR分类，不能声称已取得原CI精确错误文本。
- 本地同10个helper集合实际重现 expectedCanonical 缺参；只把既有独立批准 canonical pin 透传至 postHigh 的第二次FIFO变换校验，不从新输出反推pin，不改硬件定义、资源、算术或门槛。
- 修后同10源实际编译 native 0、42个class/10个source families，类文件metadata和哈希由独立review核验；仅编译资格，不是发射或数值PASS。
- helper_compile 前移到 original_high 前以提早发现接口错误，仍先编译完整155源。编译错误摘要仅来自本次编译argv中的.scala文件，限制8组/4KiB UTF-8，过滤secret-like及绝对路径；不上传完整日志或环境。

## ongoing / todo
- 新 R4 FRONTEND_ONLY 仍待云端实跑：canonical、transform、SV身份与串行前端不能继承本地编译PASS。
- Python独立参考5/5不是硬件数值通过；五块128-token完整Chisel数值0/5、最终RTL数值0/5，利用率未RTL实测。MoE同分参考契约仍待用户明确。
- 保留R3及所有旧源码commit/运行身份；本次普通Git更新现有小文件，新R4唯一launch路径需独立审核后才加入。禁止重跑旧任务或自动重试。
- 仍为同4096 Matrix MAC/32共享Vector候选，未放宽资源上限、证书路径、canonical pin或SV身份门槛；无权重、NPZ、生成IR/SV、class、二进制上传。
