restore $env(QWEN_RESTORE_PATH)
if {[info exists ::errorCode]} {puts "INSPECT_ERROR_CLASS [lrange $::errorCode 0 2]"}
if {[info exists ::errorInfo]} {puts "INSPECT_ERROR_VARIABLE [regexp -inline {can't (?:set|read) "[a-zA-Z0-9_:()]+"} $::errorInfo]"}
puts "INSPECT_CYCLE [get tb_qwen2_group8_pinned_idma.cycles -radix decimal]"
puts "INSPECT_STEPS [get tb_qwen2_group8_pinned_idma.msteps -radix decimal]"
quit
