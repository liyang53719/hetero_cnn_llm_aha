# Qwen2 Core：真实 normal_m3 限定里程碑

- **实际PASS：**原 SV Core/PackedClient＋脚本Matrix/memory，21689+3时钟、1260 OBS、72零score、prefix[0,1,2]、max1224次-Inf/36次+0。
- BF16 1/3=0x3eab 属编入表＋执行被动断言＋576PV消耗/exit0证据链，不是外部raw PV trace重放。当前56端点是47cache＋7source＋2locale，不回填历史Python缺口。
- 5.809396%是phase占比，余20429周期非idle证明；零值key仍有alias边界，不跨16、不M17/fullFMA/full128/full29/fullprefill/90%MAC。旧PASS/FAIL/STOP与canonical任务状态不改，整体不置done。

[精确层级、角色pins与源引用](../candidates/qwen2_core_client_m3_actual/README_ZH.md)
