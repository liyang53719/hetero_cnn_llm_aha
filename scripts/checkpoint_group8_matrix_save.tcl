run 60 us
set saved_cycle [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]
puts "GROUP8_CHECKPOINT_SAVED_CYCLE $saved_cycle"
set saved_k [get tb_qwen2_group8_pinned_idma.dut.payload.k_q -radix decimal]
if {$saved_k <= 0 || $saved_k >= 1536} {error "checkpoint does not cover partial Matrix K accumulation"}
puts "GROUP8_CHECKPOINT_PARTIAL_K $saved_k"
save work/results/group8_checkpoint/matrix.chk
quit
