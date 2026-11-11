# 12:33 可恢复源码与真实参数链

完整五块M128原Chisel仍0/5，最终同刺激RTL未通过，完整block80/90%利用率无实测。原L0 head4 FAIL不变。用户尚未回复暂停问题，未自行暂停自动化；未知旧Qwen2/L3 Host未重启。

## 本轮基线与独立工作
远端main b2906820，前轮CI43013903858成功仅payload guard；本地旧checkout干净。1133新输入仍在，0733–1033执行闭包仍缺。约8.8GiB内存、57GiB磁盘可用，无清理。

1. 从允许的三份既存源码包正式恢复Qwen2 candidate、legacy_reference、operators及rational依赖，逐SHA匹配0633依赖pin。复用1133已重新验证的真实输入，本轮新执行M128 RMS及完整Q投影301989888 MAC，session43859 exit0；4个完整K1536输出与Fraction一致。norm0 SHA ccf1e6c065c6bc4e90458194aeda7475149451ac73479a6781d2fd638bf631df；q0 SHA1e67553e3bbbd2c1118ad860a4669accbff3ead6dd403439d1cc3d0867e3e5d9。属于独立参考候选值重测，不继承旧完整21op/flags资格；没有运行Host或RTL。

2. 重新构建0.8B原只读参数桥：L0为13训练参数段+history/state冷零共15段，对接原17-op/219 descriptors；L3为11训练参数段+trig共12段，对接原22-op/261 descriptors。27段全部回读长度/hash/地址不重叠核验，原矩阵转置往返及a/b合并拆分一致，F32 gated_gamma保持512B。两profile剩余只读输入缺口均为原hidden BF16[128,1024]262144B，没有伪造原hidden或预填中间参考。冷零hash匹配此前记录，原pin文件已丢，因此不称运行态恢复。这里只是参数布局/字节PASS，完整输入闭包INCOMPLETE。

3. 155份Host候选源从已验旧基底重新构造最小能力参数/准入改动，并反变换逐字匹配；本轮新算Commands/Top hash与0733记录吻合。4项静态正负测试通过，155源Scala parser检查exit0/3.13秒。仅parser，不是typecheck、classes生成、elaboration或数值PASS。源中assert行保持原样，历史107逐条身份仍未知。

4. 基础87个jar合计61870159B全部按原计划SHA本轮重验。b048执行依赖清单另缺26项，含firrtl2/chiseltest/JNA；不把基础编译依赖完整冒执行闭包完整。新Matrix/iDMA/Host IR及严格17联合绑定仍需实际恢复重测，未盲目重启或重复昂贵完整作业。

## TODO与证据边界
继续补执行依赖和统一4096 Host原互连、时钟/reset与严格fatal；随后才恢复完整数值链。35B L0/L3真实完整权重仍缺，不绕原下载拒绝。原始同一4096资源约束、FP32顺序与BF16物化规则不变，32lane共享Vector方案仍未实现通过。
环境回退原因及持久恢复方案未解决，本轮恢复仅证明当前可读实体，不承诺跨环境保留。原产物丢失的历史PASS不迁移。临时文件清单保留，无删除、无权重或生成输入上传；只发布允许摘要/hash，不变相上传被拒源码、原始日志。只读核验与实际脚本/数值重测已分开说明。
