if {[info exists env(QWEN_RESTORE_PATH)]} {
    restore $env(QWEN_RESTORE_PATH)
    puts "SEGMENT_RESTORED_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
}
run 1 ms
puts "SEGMENT_SAVED_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
puts "SEGMENT_MATRIX_STEPS [get tb_qwen2_group8_pinned_idma.msteps -radix decimal]"
save $env(QWEN_SAVE_PATH)
quit
