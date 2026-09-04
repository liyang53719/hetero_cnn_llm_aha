proc need {name} {if {![info exists ::env($name)]||$::env($name) eq ""} {error "missing $name"};return $::env($name)}
set db [need STD_CELL_DB];set top [need TOP];set input [need CHILD_DDC];set output [need OUT_DDC];set report [need OUT_REPORT]
set_app_var target_library [list $db];set_app_var link_library [list "*" $db];set_host_options -max_cores 8
read_ddc $input;current_design $top;link
set cells [get_cells -quiet -hierarchical *];if {[sizeof_collection $cells]>0} {remove_attribute $cells dont_touch}
set designs [get_designs -quiet *];if {[sizeof_collection $designs]>0} {remove_attribute $designs dont_touch}
ungroup -all -flatten
set hier [sizeof_collection [get_cells -quiet -hierarchical -filter "is_hierarchical == true"]]
set unmapped [sizeof_collection [get_cells -quiet -hierarchical -filter "is_unmapped == true"]]
set fp [open $report w];puts $fp "TOP=$top";puts $fp "HIERARCHICAL_CELLS=$hier";puts $fp "UNMAPPED_CELLS=$unmapped";close $fp
write -format ddc -hierarchy -output $output
if {$hier!=0||$unmapped!=0} {exit 3};exit
