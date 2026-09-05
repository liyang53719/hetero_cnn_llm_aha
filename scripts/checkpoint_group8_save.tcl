run 20 us
set saved_cycle [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]
if {$saved_cycle <= 0} {error "checkpoint before execution"}
puts "GROUP8_CHECKPOINT_SAVED_CYCLE $saved_cycle"
puts "GROUP8_CHECKPOINT_DMA_BUSY [get tb_qwen2_group8_pinned_idma.ibusy -radix decimal]"
puts "GROUP8_CHECKPOINT_FLATS [get tb_qwen2_group8_pinned_idma.flats -radix decimal]"
save work/results/group8_checkpoint/k.chk
quit
