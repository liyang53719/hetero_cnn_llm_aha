restore $env(QWEN_RESTORE_PATH)
puts "SEGMENT_ENTRY_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
source work/results/q1024_continuous/next_control.tcl
if {[file exists $qwen_checkpoint_target]} {error "refusing to overwrite existing checkpoint"}
run 1 ms
puts "SEGMENT_SAVED_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
puts "SEGMENT_MATRIX_STEPS [get tb_qwen2_group8_pinned_idma.msteps -radix decimal]"
save $qwen_checkpoint_target
quit
