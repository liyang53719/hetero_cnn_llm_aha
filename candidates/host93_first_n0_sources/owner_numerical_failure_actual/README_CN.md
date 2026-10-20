# TEMP：Owner v4 实际消费非有限 Matrix result 的有限失败

原 session1021 已自然终态。compile 自然0 / 1.782645秒，link 自然0 / 0.123377秒，run 自然1 / 154.618345秒；均未超时、cleanup=true。outer exit1 / 164.20999363900046秒，于2026-10-20T00:45:12.880209+00:00结束。原 EXECUTION_RESULT 保留 INCOMPLETE/ValueError、null failure_code/boundary，run 监督诊断为 NATIVE_SUPERVISION/CHILD_EXIT_NONZERO；本轮安全实际结论仍为 FAIL。

## 本次新增的实际证据

末条 code=RESET_REQUIRED_SETTLED，edge92364。Numerical 观察在同一实际消费前采样 LOW_PRE_EDGE_ACTUAL_CONSUMPTION：result valid/ready均1、result_fire=1、context0、error0、last1，result_protocol_bad=0。该记录只证明被观察的 Matrix result 协议谓词满足，不把它扩大成整个系统协议成功。

被消费的4096个FP32 word中，1472个为nonfinite；masked_words=0、bf16_range_rejects=0。首个失败项index0，raw_unsigned=2143289344，即0x7fc00000，记录分类QNAN；坐标logical_row=0、column_offset=0，结合windowNg=160得到输出列160。只有此首项的QNAN类别得到记录，不能把全部1472个nonfinite都写成QNAN。完整4096项payload的little-endian SHA-256为853e86559d6b797538ab01a4a754fda33423c26f48c2364312f287d3e6c31ddd；公开仅该hash与有限首项标量，不上传payload数组。

消费前finite=0、responseBad=1、status=0；result_finite_disagreement=0。候选Numerical写条件为matrix=1、burst=0、drain=0，当前burst_fire/active_tile_fire均0。随后同沿high status=8，falling-low settled status仍8；原same_edge_winner保留UNKNOWN_NOT_ALL_LATER_WRITES_SAMPLED。该证据闭合实际result消费、非有限谓词与本沿Numerical状态变化，尚不说明非有限值最早在哪里生成，也不证明所有同沿后写的最终优先次序。

元数据为groupSequence3、ng160、K[0,1024)、blockId1、pairReverse1、contexts5、pendingK1023、pendingContext4；matrix wideSteps12800、slice steps102400。first_result_problem、first_status0_to8_pre_edge和current_pre_edge三份记录一致；observer_error=0，先前first_burst_problem/first_tile_problem为null。当前消费是context0 result，pendingContext4是已发issue侧状态，不能把二者混成同一result context。

## 已通过位置与未完成范围

此前首drain已在edge81467真实退休：128 typed write responses、128 descriptors、1280 data beats、81920 committed bytes。第三window request在edge81469，当前requests3/terminals2、matrix groups3/dones2；没有第三window terminal，ng160 partial1首issue目标未达到。以上是owner typed-RAM场景，不是Host AXI B或PC0前缀的执行证据。当前valid0的window/drain寄存payload不覆盖先前已验证的terminal。

本轮只编译新driver并链接原已核archive/runtime objects，没有重新生成或编译model/backend。新ELF为12826184B / 482a6d48bf8e3e320c9dd4634308dad1209acc9d49ad6c44afdd8f81eaacfceb。完整run log四行34777B / 5bf4b4fa15b820c25f2743777286c2fb823fdee2ca910975f8f5831974a57260。日志和输入/权重/数组/二进制均保留私有，公开只有安全聚合事实与内容身份。

原Host失败只在ng160/计数位置相容，同因未证；旧v2早期FAIL和v3 settled FAIL不修改。full_job/full_block=false，五block仍0/5，official/application/typed-to-RTL/historical-host-reproduction均为null。本轮没有完整输出或数值比较资格。非有限值上游来源和具体修复仍需独立诊断。

七件原证据manifest：957B / 6912c2979ad9c37a89ef334e88af8eefb2718cef9ee48e23257bcbfd5c8c9a26。摘要制作仅只读核原件，没有新native或测试。正式actual独审身份见下；原FAIL和未知上游来源边界不变。

## 正式 actual 独审及计数来源

review_owner_numerical_actual_20261020T0046：MANIFEST.json 1213B / e569e7897d10f300c245b24cc9ffeb72d8cc7dd95282ae69835b558c32ac4685；SUMMARY.md 9536B / 01e92b6d94c23679c80efc7c70ebae1b0e03ab9c3c1336fa70a1f80c74737158；verdict ACCEPT_ACTUAL_OWNER_V4_MATRIX_NONFINITE_CONSUMPTION_FAILURE_ONLY。

计数应精确读为4096个未屏蔽FP32槽、1472个非有限、2624个有限；2624为4096−1472。聚合计数和payload SHA来自已独审fixed scanner的实际日志；本次没有保存或公开该4096项数组，也未由独审重新计算整组payload。首项0x7fc00000可独立按FP32位编码确认为quiet NaN，仅此首项有该分类。

独审核验当前53项/38regular/38071029B工作树、338份原生成输入/79657058B、7fixture/12copies、完整输入、新ELF/.d及23成员archive/3runtime对象关联。39系统依赖沿SOURCE资格、本次未重hash；原608整棵compiled tree未本次重新全核。运行失败后success-only caller postflight未执行，独立终态读验不倒填该阶段。v2只补正式身份、核验范围及计数来源元数据，原测量数值不变。
