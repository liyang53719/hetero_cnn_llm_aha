# R2 实际共同后端构建证据（PASS 范围限定 / 数值 INCOMPLETE）

原身份 run [40862676969](https://github.com/liyang53719/hetero_cnn_llm_aha/actions/runs/40862676969)、job123409571999、attempt1；本目录仅保存受控摘要字段及公开链接，未重跑。OBSERVED_BUILD_SUMMARY.json 的时间、RSS、hash来自唯一原run下载摘要；下载ZIP digest与GitHub artifact API逐字节核验。

27阶段native0，包括3个child archive、Host archive和Host link。五段实测依次22.904、105.517、266.129、823.985、16.573秒；构建阶段最大RSS3923709952B（Down archive）；整体最大RSS9592324096B（Host frontend），aggregate tree观测峰值4929358855B。以上是工具执行资源/墙钟，不是DUT周期、MAC利用率或目标内存性能。完整4096/Vector32/原物理provider和算术定义未缩减；host峰值再次说明不在本地7GiB上限重复昂贵生成。

实际SV raw SHA c8e6b1c8faf26831d46daea019b70347c1ae441621aa6de3ed69c14b38fd2f53，222202215B；经已审SourceInfo目录规范后6555ede34ba2980a6ebfddb13325ffb14734063d3253fdadd493bfcb4bf67bb5。这是源码目录规范身份，不是数值正确性。

job内部七文件冻结成功，受控摘要只有manifest hash/size和aggregate bytes。由于NO_PAYLOAD_UPLOAD，binary/SV/driver/source/tool/build receipts均未作为artifact留存；当前无法重新读取原ELF或导出其独立hash。不得把manifest hash冒充binary hash，不声称有可下载binary、不产生VERIFIED_GITHUB_ARTIFACT_DOWNLOAD资格。源码pack要求ELF64LE/完整五阶段/stable pins后才完成，当前保留的是该执行成功的受控记录，而非binary本身。

原R1 run40856253077 admission失败记录仍有效，具体文件UNKNOWN；R2通过不回填原失败文件名。完整五块M128 Chisel/最终RTL数值仍0/5；没有运行输入/权重/DUT，没有模型PASS迁移，也没有80/90%实测。

后续可准备同job构建后保留同binary并执行数值的源码方案，另加仅hash/size的摘要字段，避免无授权公开payload；二者都需要独立测试与实际启动审查。未来测试fixture或摘要代码不能当本轮缺失hash证据。不自动重建、不重试本run、不修改公共上传授权状态。
