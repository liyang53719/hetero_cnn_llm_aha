source work/results/q1024_captured_oproj_replay/next_control.tcl
if {[file exists $qwen_checkpoint_target]} {error "refusing to overwrite checkpoint"}
run 1 ms
puts "SEGMENT_SAVED_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
save $qwen_checkpoint_target
quit
