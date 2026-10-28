# 原同一 Top：实际 high→low 结构通过，完整数值仍0/5

**第三次实际运行完成原 HostBlockTopV4 的 Chisel elaboration 与官方 `Compiler.toLowFirrtl`，包括其初始化/组合环检查。** 不是仅Scala类型编译，也不是改wrapper绕过错误；但仍不是SV/最终RTL生成或仿真、数值、PPA或利用率证明。

## 两个真实失败及精确源码修复

1. **1432 FAIL，native1**：RawPrep `head(4).asUInt.pad(66)`仍带Bool类型，constructor要求失败。只改为显式UInt范围切片`head(4,4).pad(66)`，值/地址不变。
2. **1450 FAIL，native1**：修复RawPrep后已elaborate，但官方CheckCombLoops发现GQA准入 `job.fire→faultNow→resetRequired→parent canStart→job.valid` 反馈。四个job.fire拒绝分支改为握手沿注册status/poison/drain，准入不再反射即时faultNow；运行中currentFault、未知返回、数值路径、held请求与还债其余逐字不变。
3. **1500 PASS（仅结构），native0**：原同一Top/诊断main完成官方high与low。前两次失败目录、receipt、日志原样保留；旧source/model/typecompile PASS不冒充构造或无组合环证明。

本包同时给两份真实修复源，不要求不存在的“已发布中间RawPrep/GQA包”。两源**先后各自**做增量编译：RawPrep baseline1000→1新类；GQA baseline991→10新类。最终31源159类=29个冻结fence父源148类+两修复11类；不是同时2源或完整31源重编。实际诊断使用1001类=842历史+159最新类，56个源码pin=31最新+25额外requires-parent诊断支持源。公开最新映射为2新源/24已公开继承/5requires-parent。

## 实际结构证据

wall254.152秒、CPU204.50秒、peakRSS2681233408B、输出树635320582B，前后各1656严格pin。起始3313868800B、结束2676150272B，满足未放松的3GiB启动/2GiB结束门；没有通过删除/截断输出代替预算。

实际14项诊断输出均有pin/hash：high97,256,876B；两份low均258,102,601B，SHA256 `f4bb8b87dea31205536d828d17bfab75e6ce255011ef7e15151055c29228691d`。**这不是最终RTL hash。** 大IR、annotation、层级文件及class均不上传，只发布摘要/身份。

高低层级均核到8×512=4096逻辑Matrix MAC endpoint、一个32-lane Element bank、一个iDMA、85端口（41输入/44输出）、844位Host launch。**全Top仍有81个FP32 ALU实例与17个Scalar模块（16 legacy+1 policy）**，不能把一个共享32-lane bank说成全Top只有32ALU/一个FPU。

Matrix endpoint与iDMA在本次FIRRTL是原blackbox接口，核过实例类型、seed512/result16384及seed参数，不等于内部RTL数值/物理乘加/真实RAM端口或II重新验证。层级计数不是PPA。

**30条宽度警告全部保留：21 W004、9 W005。** `WIDTH_WARNINGS.json`逐条保留source basename/行列和消息，仅移除云端路径；结构通过不等于索引边界、协议或数值无问题。

## 小检查、复现与磁盘解除阻塞

普通Python/`-O`的RawPrep128地址案例/4负控，GQA112抽象准入/activefault案例/5负控，以及公开包hash和摘要不变量检查通过。它们不执行Chisel、不重新计算大IR。独立实际结构review与bundle映射review分别绑定，两个短链接JSON不是额外独立审查。

`REPRODUCTION.json`是精确实际argv占位配方、未变caps和14输出合同。仍需父级完整56源身份/1001class/build闭包、106 jars、314-file JDK、原诊断main及严格有界supervisor；不是全新checkout一步复现或新运行授权。当前执行输入闭包已核，旧缺失编译receipt/历史JSON全图仍不宣称可重验。

单独root验证的依赖迁移释放2,070,339,584B：5处已安装运行依赖/可重建缓存、48,284文件与5,095目录内容/metadata核对后切换。没有删除用户输入、模型权重、IR、RTL或仓库证据。目标为临时易失存储，可能需恢复；旧resolved-path pins不改写为继续成立，也没有据此宣称runtime import/数值成功。`DISK_UNBLOCK_SUMMARY.json`只保存脱敏摘要与证据hash；本次发布没有迁移/清理动作。

从包目录运行，保留相邻已发布`host_runtime_gqa`，原RawPrep必须匹配pin：

```sh
python -B verify_package.py
python -B verify_summary.py
python -B check_width_fix.py --original-rawprep-source /path/to/original/GdnRuntimeRawPrepOwnerV7.scala
python -B check_gqa_admission.py
```

将`python -B`换为`python -B -O`复核优化模式。

## 下一门

非零profile全局launch seal仍关闭；high/low不能证明这些数值事务可达或正确。五块完整128-token Chisel数值仍0/5，同刺激最终RTL仍0/5，无利用率实测，MoE tie契约待定。

下一步同一源码审查实际准入、30条索引警告，准备五套完整Record128/DDR刺激与独立参考，在原Top比较逐层/final输出、KV/GDN状态；真实模型通过后冻结源码/输入/参考/配置，再同一最终RTL hash回放五块。资源并发受限不能缩水4096硬件，也不能以结构PASS代替完整数值验收。
