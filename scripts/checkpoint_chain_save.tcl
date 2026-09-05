restore work/results/checkpoint_continuity/first.chk
puts "UCLI_BASELINE_GLOBALS [llength $::ucliCore::_vars_list] CURRENT_GLOBALS [llength [info globals]]"
set ::ucliCore::_vars_list [info globals]
puts "CHAIN_ENTRY [get tb_checkpoint_continuity.cycle -radix decimal]"
run 100 ns
puts "CHAIN_SAVED [get tb_checkpoint_continuity.cycle -radix decimal]"
save work/results/checkpoint_continuity/second.chk
quit
