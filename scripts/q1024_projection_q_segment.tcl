restore $env(QWEN_RESTORE_PATH)
# VCS W-2024.09 clears this UI baseline on restore. Re-establish it before
# saving again so readonly tool globals are not serialized as user variables.
# Replay control lives in external receipts, not pre-existing Tcl globals.
set ::ucliCore::_vars_list [info globals]
puts "SEGMENT_ENTRY_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
source work/results/q1024_continuous/next_control.tcl
if {[file exists $qwen_checkpoint_target]} {error "refusing to overwrite existing checkpoint"}
run 2 ms
puts "SEGMENT_SAVED_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
puts "SEGMENT_MATRIX_STEPS [get tb_qwen2_group8_pinned_idma.msteps -radix decimal]"
save $qwen_checkpoint_target
quit
