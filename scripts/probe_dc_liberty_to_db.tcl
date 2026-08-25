if {![info exists ::env(PROBE_LIB)] || ![info exists ::env(PROBE_DB)]} {
  puts stderr "PROBE_LIB and PROBE_DB are required"
  exit 2
}
set loaded [read_lib $::env(PROBE_LIB)]
if {[sizeof_collection [get_libs tiny_probe -quiet]] != 1} {
  puts stderr "tiny_probe library was not loaded"
  exit 3
}
write_lib tiny_probe -format db -output $::env(PROBE_DB)
if {![file exists $::env(PROBE_DB)]} {
  puts stderr "DB output was not created"
  exit 4
}
puts "DC_LIBERTY_TO_DB_PASS $::env(PROBE_DB)"
exit
