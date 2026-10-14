# H2048 RMS 同 bank Scalar 对照与真实服务周期观测

## 范围与当前状态

基线 main 为 `f16df50adfb0f1f4bc668c517a2e29accffe6753`。本批默认 Vector 路径不变，新增编译期 `useVectorEpilogue=false` 的 H2048 受控 Scalar epilogue 对照，以及仅在测试 harness 中的真实内部状态观测。它不是历史 H1024 路径，也不是完整 block、完整 Host/kernel 数值仿真或物理 PPA。

- 已通过：两模式 synthetic M1 数值/事务门；真实冻结 M1 同源同刺激 A/B。
- 已通过：同一个 DUT 不全局 reset，额外保持真实 loan reply 323 拍后，wall、service busy、reply resident 均恰增 323，而 ALU 执行和有效 lane-cycle 完全不变。
- 已通过：新 Scalar 三阶段12种定向取消/clear/恢复、真实 FP32 和 BF16 溢出、两模式资源库存，共3 suite/3 tests。
- 已通过：最终冻结源码下真实 M1/M16/M128 同刺激 A/B，每模式1个 ScalaTest 内依次执行三种规模。两模式153个编译源与45条fixture记录（44个唯一路径）逐SHA完全相同，运行前后不变；全部输出逐bit匹配。
- 后续仅加强结构测试的regreset断言并单独复验1 test通过；生产源和数值harness没有变化，不将该结构测试修改冒充原A/B编译源。

## 相同资源与数值契约

两模式都使用三块 2KiB borrower bank，总 6144B，四个 FP32 标量寄存器，同一生产 core 的 Scalar、原位置 core.elem 及原 12KiB elem SRAM 配置；原 legacy vout16 保留。没有新增 Scalar、Vector ALU 或 bank。相同配置和 CHIRRTL 库存不等价于相同综合面积、物理 banking 或切换功耗。

归约两模式严格相同；epilogue 逐 lane 都是独立 FP32 normalize Mul → FP32 Add(1+原始 BF16 weight) → weighted Mul → 末 BF16 RNE。这是 Qwen3.5 零中心 gamma 契约，不推广到 Qwen2 direct gamma。

每 token Vector 为 4268 Scalar 请求加128 loan；Scalar 对照为10412 Scalar 请求、零loan。两模式DDR都为192个64B读和64个64B写ACK。Scalar对照逐16bit更新原输出beat，整个1024元素chunk填满后才写DDR。

## 计数定义

观测来自原生产实例的 state/op/tile/calcIndex、异常及取消信号。计数只累积在宿主测试器，不新增生产 counter 寄存器。

- elem ALU 执行拍：原 lender 实际 normalize/gamma/weighted 等计算状态，排除 reply、idle、锁定和请求背压。
- effective lane-cycle：当拍未取消且数值有效的逻辑阶段 lane；不是物理寄存器 capture、最终输出发布贡献或晶体管切换。
- service busy：包含计算和 held reply；与 ALU 执行单独报告，不能互换。
- Scalar ALU 执行拍：原 Scalar 的 normal 状态。divWait 单列为已接受 Sqrt/Div 的等待驻留，不称物理迭代忙拍。
- wall：接受 launch 到 done.fire 的边沿间隔，包含全部读/写ACK、请求/返回等待、末ACK延迟和13拍 held done。
- DDR、Scalar、loan、owner/terminal 的服务阶段使用 pre-edge 债务账本和单一互斥分支，每拍只归一类；其总和严格等于 wall。ALU计数是独立分子，不再次加进 wall。

HeteroFP32Alu 是含 AddRecFN 与 MulRecFN 的组合模块，没有自身 busy/clock-enable；这里实际测的是调度执行，不是动态功耗。每loan是2Mul+1Add，没有MAC操作。

## 当前真实 M1 同刺激结果

M1 使用原成功 M16 的第0行，manifest `fdca7a3011740a44d1a1a26cc7570392b5fdb55993a849758829d4b71a205cc3`。两轮编译源集合及每个hash完全相同，fixture前后也相同。只有input/weight进入DDR，inverse和全部结果由实际DUT计算。

| 测量 | Vector epilogue | Scalar epilogue |
|---|---:|---:|
| launch→done.fire wall | 19907 | 42568 |
| Scalar requests | 4268 | 10412 |
| Scalar ALU执行拍 | 4266 | 10410 |
| Scalar divWait驻留 | 51 | 51 |
| elem ALU执行拍 | 384 | 0 |
| elem有效Mul lane-cycle | 4096 | 0 |
| elem有效Add lane-cycle | 2048 | 0 |
| elem service busy | 674 | 0 |
| elem reply驻留 | 290 | 0 |
| 64B读 / 写ACK | 192 / 64 | 192 / 64 |

两模式 BF16 输出逐 bit 相同，互斥wall分解如下：

| 区段 | Vector | Scalar |
|---|---:|---:|
| 全DDR请求/返回及等待 | 2591 | 2591 |
| Scalar归约所有阶段 | 16417 | 16417 |
| epilogue服务所有阶段 | 885 | 23546 |
| held done及退休 | 14 | 14 |
| 合计 | 19907 | 42568 |

42568/19907≈2.13834 是这套人工背压调度下的局部 RMS 周期比。周期模运算的 Scalar/loan 背压在两模式中的相位不同，不将该比值宣称为无停顿硬件加速比、完整block收益或PPA收益。

仅以原 core.elem 的16lane容量为分母，6144/(19907×16)=1.92897%；若分母包含原 legacy vout16、Scalar或Matrix，必须另行标注，不能把未使用单元省略后当全block利用率。该优化仍仅移走原35B prefix Scalar工作约7.04%。阶段最低80%/争取90%，最终实际完整RTL的90%联合验收目标没有改变。

机器回执与完整逐项分桶见 reports/execution/H2048_RMS_SAME_BANK_PERFORMANCE_20261014.json；原始两轮 summary/log 保留在 ignored work。generated_records 明确标为缓存目录库存，单凭它不能证明当前run的RTL归属或mode身份；当前-run资源/模式要按单独结构门与源码身份核验。

## 最终 M16 / M128 同源结果

| 测量 | M16 Vector | M16 Scalar | M128 Vector | M128 Scalar |
|---|---:|---:|---:|---:|
| launch→done.fire wall | 317656 | 680375 | 2540828 | 5442701 |
| owner运行拍 | 317642 | 680361 | 2540814 | 5442687 |
| Scalar requests | 68288 | 166592 | 546304 | 1332736 |
| Scalar ALU执行拍 | 68256 | 166560 | 546048 | 1332480 |
| Scalar divWait驻留 | 813 | 813 | 6520 | 6520 |
| elem ALU执行拍 | 6144 | 0 | 49152 | 0 |
| elem有效Mul lane-cycle | 65536 | 0 | 524288 | 0 |
| elem有效Add lane-cycle | 32768 | 0 | 262144 | 0 |
| elem service busy | 10729 | 0 | 85737 | 0 |
| elem reply驻留 | 4585 | 0 | 36585 | 0 |
| elem result held | 2537 | 0 | 20201 | 0 |
| loan请求 | 2048 | 0 | 16384 | 0 |
| 64B读 / 写ACK | 3072 / 1024 | 3072 / 1024 | 24576 / 8192 | 24576 / 8192 |

M128实际局部周期比5442701/2540828=2.14209737928，wall下降53.3167815%。原core.elem的16lane有效容量分数为786432/(2540828×16)=1.93448750%，等于此满lane测试的49152/2540828调度执行拍分数。其余原legacy vout16和Scalar仍在配置中；这个分母不包含它们或Matrix，不能称整block利用率。33个HeteroFP32Alu模块仅是本harness中Scalar1+legacy vout16+elem16的类别库存，不代表全硬件算术总数、MAC容量或PPA。

### M128互斥wall分解

| 区段 | Vector拍 | Vector占wall | Scalar拍 |
|---|---:|---:|---:|
| Scalar reduction服务 | 2100588 | 82.673365% | 2100599 |
| 所有DDR请求/返回/等待 | 327707 | 12.897646% | 327707 |
| epilogue服务 | 112519 | 4.428438% | 3014381 |
| held done + 终态fire | 14 | 0.000551% | 14 |
| 合计 | 2540828 | 100% | 5442701 |

Vector reduction桶精确拆为：ALU546048、Div等待6520、请求fire546304、请求背压205912、响应fire546304、响应held249244、其他响应等待256。DDR桶精确拆为请求背压131069、响应等待131102、请求/响应fire65536；其中归约读81922、epilogue读163840、epilogue写81945。loan桶为ALU执行49152、请求fire16384、请求背压10398、响应fire16384、响应held20201。三套子桶分别互斥相加，但独立arithmetic计数不再次相加到wall。

两个模式的同一归约工作相差11拍，来自周期性人工背压相位变化。下一瓶颈证据是归约的串行请求/执行/返回服务，以及DDR feed等待；尚未据此实现新归约架构，也没有把这些人工背压比例视作真实系统带宽模型。

### 来源和定向门

M16 manifest为a0634202bcca950242d6e1c160be6897cd5e14e735b80936f625d0167850d6a0，M128为799a8e3bc67c1dd32a77cc4766268a4d5c570639cf1fb7a18f87153fe008fde7。原真实residual和weight经DDR进入生产core服务；mean/inverse由真实Scalar计算，参考inverse从不注入请求。summary和log SHA、完整153源/45条fixture记录哈希与各阶段原始计数在机器回执中。

12种取消覆盖Scalar normalize/gamma/weighted三个请求点的offered abort、accepted abort、held abort、held clear；债务保留至实际返回，clear后同DUT复用。数值门包含±0、BF16 subnormal/tie，以及有限FP32转BF16溢出和真实FP32Inf两类错误，二者均在写出前poison，0写ACK，clear后恢复。结构单测同时比较7个reg和12个regreset声明及所有smem，防遗漏复位寄存器。
