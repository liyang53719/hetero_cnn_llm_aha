# L3真实M128 RMS/QKnorm精确节点审计（局部PASS）

新增独立 `exact.py`：有限FP32转Fraction，整数商/余数执行RNE，除法精确有理商；sqrt不依赖libm/NumPy结果，通过FP32正数位序二分定位相邻根，再用精确平方中点决策。返回原HardFloat位序OF/UF/NX，tininess-after-rounding；非有限、负sqrt、零除数拒绝，不伪造完整IEEE全域资格。

对已hash核验的真实0.8B L3 M128数据，覆盖input RMS128行、post RMS128行、Qnorm128×8行、Knorm128×2行，共1536个真实sqrt/div输入对。归约保持原32-lane映射、512分块、residue/lane折叠顺序；全部平方/累加/尺度/epsilon以及normalize/gamma乘加逐节点用独立精确有理数RNE对照，而非只合成叶子。共1771008 mul、712704 add以及1536 sqrt和1536 div，值均一致，实际flags仅0/1。用精确sqrt/div替换后，四阶段全部BF16保存输出逐字一致。没有重新执行Dense、attention或完整硬件。

普通首轮只核归约+sqrt/div，原session6442 exit0；扩大至完整normalize/gamma节点后session91233 exit0/17.13s，-O检查不依赖assert。最后加入依赖pin预检后在原预算再次执行，终态及耗时以RESULT与run_final.log为准。CPU590s/wall600s、AS2GiB。固定7个sqrt/div/flags边界与2拒绝case普通/-O通过。

此PASS仅以上实际有限输入四个归一化阶段的数学值/标志审计，不等同Chisel/HardFloat实现通过，也不外推Dense、所有未来输入、其他profile或全block异常资格。后续Matrix/其他scalar flags仍NOT_QUALIFIED；完整五块硬件仍0/5，旧head4 FAIL不变。无周期或利用率实测。没有修改原fatal策略，也没有权重/数组上传。

依赖源及摘要逐一SHA校验见DEPENDENCY_PINS；每个实际输入文件SHA在RESULT。复现（已有按pin恢复本地数据的工作区）：`OPENBLAS_NUM_THREADS=1 timeout 600 python -O round_20261110T1033/l3_exact/run.py`。
