# 2026-11-14 06:33 hetero：INCOMPLETE

统一4096 Matrix MAC、数值/异常策略不变。五块M128完整原Chisel仍0/5，完整RTL及完整block有效MAC利用率未测。

## 真实RMS第二行
session14321 exit0：从已验20680完整包恢复到23515，新增2835周期/25.004秒active，前2/128行12288个实际ACK字节与独立参考完全一致。3个完整安全checkpoint，最终包SHA b0904429405d9957ba66948ef927df08ae727f40621459dc1dd3a340fde052f6。
fresh-process继续120周期到23635，轨迹及20块终态hash一致。没有完成128行首RMS或完整block。参考仅比较实际写回，不向DUT供中间值。
已立即沿23515启动下一有界continuation01原session53828，每1000周期安全保存、80秒提前收尾、90秒硬界；不等整点，不重复未知旧29364。后续结果须沿原身份核，不冒在途PASS。

## L0与复现
官方pin 14e738b5d0cc69aa27a95dde272aea41fde44f2f原生chunk_size64、seq_len>1走chunk，无上游整体M1限制。官方cumsum/exp/matmul不定义项目固定scalar次序及strict UF fatal，不能用公式授权放宽。
当前strict phase6失败后不能跳到phase7或后续冒完整执行。19份本地最小复现依赖hash核验通过并拒错误pin，未重复失败前缀/Bank测试。要另立finite-gradual候选是新的数值策略决策，原strict FAIL必须保留，未实施；NX本已允许，不混淆UF与NX。

## 当前边界与维护
Qwen2/L3完整独立参考保持复用；35B真实权重/冻结Torch运行闭包与MoE数值/tie资格仍缺。旧29364Unknown不重启。基线main6c4a89a5b1526e21c2cbabbed918f12c3b5d3e93，CI43562758999 success仅payload守卫。
临时清单已核、工作树clean，清理0；保留运行文件/唯一证据，远端仅允许摘要和中文计划，不上传源码/权重/NPZ/原日志。

## 实际共享Scalar联合子链
原adapter直接连接原Qwen2ContinuousBlock sharedScalar及原Scalar模块，Core参数与Host共享服务相同，外部Matrix/DDR静止、不发owner job。10例实际运算、真实Core request.fire/result.fire计数、adapter计数及4拍返回背压验证通过，非手工计数shim。lease仍为合成输入，不能称真实allocator/完整MoE授权链通过，也不涉及4096 Matrix数值资格。
首次测试过早要求adapter寄存issued==1，在零/短延迟错误响应的首可见拍失败；只将测试在4拍hold后核寄存计数，未改DUT/未重编RTL，复用archive重新链接执行通过，最终真实Core/adapter均1/1/1。保留首次源码/日志，不把第一次失败隐藏。分别记录采样首可见计数以核明组合issuedNow与寄存issued时序。

持续工作更新：continuation01原53828已exit0，保存到cycle30703，ACK仍12288B，最终包fresh-process120周期及20块差分通过。已立即从30703启动continuation02原23287，仍在途，不重算前缀；下一检查必须沿原身份取终态。
实际首可见计数trace确认case6/7 Core issued=1而adapter寄存issued=0；4拍hold后双方1/1/1，首测采样定因有实测支持。
