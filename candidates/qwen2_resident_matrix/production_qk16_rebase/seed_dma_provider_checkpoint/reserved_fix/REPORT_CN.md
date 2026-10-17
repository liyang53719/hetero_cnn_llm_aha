# reserved beat/commit READY 最小追加修复

基础是已通过512-lane组件lint的 begin.ready 候选，追加恰两条assign：beat_ready与commit_ready的quiet资格复用现有begin_quiescent。没有新增状态、寄存器、算术或端口；变量名沿既有命名以保持最小delta。

证明不依赖上层：reserved=0时两ready恒0；reserved=1时seed_block恒1，本地scheduler禁止issue，array_control.input_write=in_valid&&in_ready为0，因此fullquiet=retainedquiet。故两ready本身及所有fire在二态输入下相同。实际日志beatready共享同式经DFG合并进入allCommit，不能误称只有beat握手。

fullquiescent、reserved fault、非法早到beat/commit拒绝、identity/count/finite保护、write/commit/fault/ACK/hold所有其它原式完全保持。busy时begin.valid原有poison契约保持。SOURCE_PINS绑定上一组件候选和实际完整noinline失败；PATCH只两处替换。

冷模型枚举14布尔输入×4个count边界=65536组合，比较全部边界输出，包含同时三valid、非法identity/count、abort/heldACK/poison、step。移除reserved本地block会导致READY不等的反例，防止只靠上层假设。这里没有时钟、X/Z或完整FSM动态证明，不将模型提升为RTL实际消环；新工具资格仍需独审/root单次授权。

复现：python -B test_cold.py；python -B -O test_cold.py。replay.py --source-root 指向上一begin.ready候选source根，--out必须新目录。没有修改任何冻结源码、共同SV或main。
