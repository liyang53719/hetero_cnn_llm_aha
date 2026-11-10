# Qwen2 M128 真实输入恢复：PASS 仅限字节转换

- done：重验历史 raw13 真实文件，13个大小/SHA匹配，合计94,382,080字节，Qwen/Qwen2-1.5B-Instruct revision ba1cf1846d7df0a0591d6c00649f57e798519da8。不能再笼统说全部真实权重缺失。
- done：新增 prepare_fp32.py，将原BF16权重逐位左移16位物化为原FP32存储；token IDs 0..127取训练embedding，原始行主序保持不转置，不预置归一化/QKV中间量。13个FP32文件总187,977,728字节，每字重验可逆位提升。三项单测通过（符号零/subnormal/Inf/NaN位型、奇数字节拒绝、缺失输入不创建输出）。
- ongoing：原Conv→RawPrep真实生产者连接在兄弟conv_raw_candidate推进，不修改生产n16下溢契约。
- todo：把该输入包接到原profile0共享4096MAC Host完整执行链，对齐真实算术调度顺序的独立参考，全部中间数值与完整block验收。当前未运行参考forward/Chisel/RTL，五块128仍0/5，80%/90%利用率无新增实测。

输出数据仅本地，源码包只收脚本/pin/摘要，不上传f32le/bin/NPZ/TSV或文本编码的数据。
