restore work/results/checkpoint_continuity/first.chk
puts "CHECKPOINT_RESTORED_CYCLE [get tb_checkpoint_continuity.cycle -radix decimal]"
if {[get tb_checkpoint_continuity.cycle -radix decimal] != 78} {error "checkpoint did not restore saved cycle"}
run
