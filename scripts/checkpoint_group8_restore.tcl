restore work/results/group8_checkpoint/k.chk
set restored_cycle [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]
if {$restored_cycle <= 0} {error "checkpoint restarted from zero"}
puts "GROUP8_CHECKPOINT_RESTORED_CYCLE $restored_cycle"
run
