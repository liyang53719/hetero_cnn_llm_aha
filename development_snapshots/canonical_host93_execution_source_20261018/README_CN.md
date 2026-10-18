# Host93 有界执行入口复现源码

本包仅持久化已审的三个小入口与有限安全结果；不包含 JAR、HardFloat下载副本、生成Scala树、class、工具二进制、运行日志或当前机器身份。官方依赖按已发布的 Host93 获取计划本地生成。

- acquisition：两个独立组的有界获取入口，默认继承平台运输环境。JAR87总1200秒、HardFloat20总300秒；每个组的新attempt只取一次，按原SHA逐件核验，不执行下载物。
- assembly：60秒单进程源重放入口，从固定111项目来源和20个HardFloat输入生成新的93源闭包。32MiB护栏约束最终源码内容；单文件FSIZE不是整个临时目录总量硬限制。
- class_compile：150秒总窗、最多120秒编译工作的独立CLASS入口，固定87依赖和新93源快照，单CPU、heap1GiB、AS4GiB。它不运行emitter。CLASS首次实际超时失败，未产出class；本包不更改预算、不授权重试。

各目录中的SOURCE-only状态和冷测记录是当时冻结的源门记录，保留原字节；本次实际结果以根目录SAFE_ACTUAL_SUMMARY.json为准。孤立RESULT或SOURCE_RECEIPT不能视作成功，必须同时有外层实际退出码、全程时长及实际库存独核。

唯一投影修改是assembly/MANIFEST.json删除不发布的本地执行路径绑定记录；三个入口及所有测试代码逐字保持。传入路径由复现者显式提供；已发布repo相对来源和源码SHA保留。未来本地日志/receipt由运行产生，不进入本包。

源码冷测沿各子目录README直接入口运行，使用-I-S-B和普通/-O两模式；acquisition需--repo与--acquisition-source，class_compile需--repo，assembly无额外参数。所有冷测均为纯mock；实际网络/Java执行需相应授权和固定输入。

没有新的RTL、真实Host业务、完整N0或完整block数值资格。旧N0会话终态未知事实保持，完整block仍0/5。
