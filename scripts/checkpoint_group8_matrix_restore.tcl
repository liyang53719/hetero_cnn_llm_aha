restore work/results/group8_checkpoint/matrix.chk
puts "GROUP8_CHECKPOINT_RESTORED_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
puts "GROUP8_CHECKPOINT_RESTORED_K [get tb_qwen2_group8_pinned_idma.dut.payload.k_q -radix decimal]"
run
