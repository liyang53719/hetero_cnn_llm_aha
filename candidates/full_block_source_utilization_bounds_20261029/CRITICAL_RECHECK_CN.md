# 关键复核（只读源码、独立算术；非DUT运行）

1. 实际64×2 chunk完整M128控制，不是重复M1。Coordinator:93 tokens128→2chunks；269保存phase16 stateReady，271保存phase17 outputReady，273 chunk++后issueLoad；LoadPrepV2:221-230必须收到同身份前chunk16/17 ACK receipt。ExecuteV8:164 previousBase在chunk1指向cb−chunkBytes+offset(next_state)，79-80供phase9/11/15；91 outputToken=(chunk<<6)+row。64行完整矩阵/solve阶段见ExecuteV8:39-50。
2. 同拍issue/retire被字面FSM排除：ExecuteV8:106 valid仅issueVector、114 ready仅waitVector，115 mem.valid仅issueRead/write、121 response.ready仅waitRead/write；190 memory.fire后注册state=waitRead/write，233vector.fire后waitVector，无组合旁路。wait态对应request.valid=false，故也不能retire旧请求同时issue新请求。≥2周期/事务下界成立，与外部是否零延迟无关。
3. 独立手工常数求和，未import复现脚本：
   - read = 2×35072+2×17888+2×69632+34816+69632+1024+1024+1024+2048+512 = 355264
   - vector = 2×65792+2×32768+2×131072+65536+131072+512+512+1024+1024+512 = 659456
   - write = 2×256+2×512+2×512+512+1024+512+512+1024+1024+256 = 7424
   - 最少2×(355264+659456+7424)=2044288周期/head/chunk。
   与FULL_BLOCK_BOUNDS.json每phase求和断言相等。×32(P1 16heads×2chunks)/×64(P3 32heads×2chunks)等于此前下界。

保留事实层级：只证明源码控制/算术下界，未证明模型/RTL完整数值通过。
