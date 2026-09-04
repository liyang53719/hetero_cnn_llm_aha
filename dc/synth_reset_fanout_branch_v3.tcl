proc need {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {error "missing $name"}
  return $::env($name)
}
set rtl [need RTL]
set db [need STD_CELL_DB]
set out [need OUT_DIR]
file mkdir $out
set_app_var target_library [list $db]
set_app_var link_library [list "*" $db]
set_host_options -max_cores 1
analyze -format sverilog $rtl
elaborate operator_reset_fanout_branch_v3
current_design operator_reset_fanout_branch_v3
link
set_dont_touch [get_cells -hierarchical *]
create_clock -name virtual_reset -period 1.250
set_input_delay 0.100 -clock virtual_reset [all_inputs]
set_output_delay 0.100 -clock virtual_reset [all_outputs]
set_input_transition 0.050 [all_inputs]
set_load 0.020 [all_outputs]
set_max_transition 0.230 [current_design]
set_max_fanout 32 [current_design]
compile -map_effort high
report_qor > "$out/qor.rpt"
report_area > "$out/area.rpt"
report_constraint -all_violators > "$out/constraints.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set fp [open "$out/status.txt" w]
puts $fp "STATUS=[expr {$unmapped == 0 ? "PASS" : "FAIL_UNMAPPED"}]"
puts $fp "UNMAPPED_CELLS=$unmapped"
close $fp
write -format ddc -output "$out/operator_reset_fanout_branch_v3.ddc"
exit
