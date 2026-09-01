if {![info exists ::env(LIB_PATH)] || ![info exists ::env(LIB_NAME)] || ![info exists ::env(DB_PATH)]} {puts stderr "LIB_PATH LIB_NAME DB_PATH required";exit 2}
read_lib $::env(LIB_PATH)
if {[sizeof_collection [get_libs $::env(LIB_NAME) -quiet]] != 1} {puts stderr "library not loaded: $::env(LIB_NAME)";exit 3}
write_lib $::env(LIB_NAME) -format db -output $::env(DB_PATH)
if {![file exists $::env(DB_PATH)]} {puts stderr "DB not created";exit 4}
puts "L10_SRAM_LC_DB_PASS $::env(LIB_NAME) $::env(DB_PATH)"
exit
