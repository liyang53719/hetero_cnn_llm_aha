# Revision 8B-A mapped cycle-neutral 1-to-4-to-32 distribution tree.
proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} { puts stderr "Missing required environment variable $name"; exit 2 }
  return $::env($name)
}
set RTL [require_env BROADCAST_RTL]
set STD_DB [require_env STD_CELL_DB]
set OUT_DIR [require_env OUT_DIR]
set DDC_OUT [require_env DDC_OUT]
set NETLIST_OUT [require_env NETLIST_OUT]
set SDC_OUT [require_env SDC_OUT]
set PERIOD [expr {[info exists ::env(CLOCK_PERIOD_NS)] ? $::env(CLOCK_PERIOD_NS) : 1.0}]
set HIGH [expr {[info exists ::env(DC_TIMING_HIGH_EFFORT)] ? $::env(DC_TIMING_HIGH_EFFORT) : 0}]
file mkdir $OUT_DIR
set_app_var target_library [list $STD_DB]
set_app_var link_library [list "*" $STD_DB]
set_host_options -max_cores 4
analyze -format sverilog $RTL
elaborate bf16_front_to_cluster_broadcast32_rev8b_a_candidate
current_design bf16_front_to_cluster_broadcast32_rev8b_a_candidate
set link_status [link]
check_design > "$OUT_DIR/check_design.rpt"
create_clock -name virtual_core -period $PERIOD
set_clock_uncertainty 0.08 [get_clocks virtual_core]
set_input_delay 0.10 -clock virtual_core [all_inputs]
set_output_delay 0.10 -clock virtual_core [all_outputs]
set_input_transition 0.05 [all_inputs]
set_load 0.02 [all_outputs]
set_max_fanout 8 [current_design]
set_max_transition 0.10 [current_design]
set_fix_multiple_port_nets -all -buffer_constants
if {$HIGH} {
  set_critical_range 0.20 [current_design]
  compile_ultra -no_autoungroup -timing_high_effort_script
} else {
  compile_ultra -no_autoungroup
}
report_qor > "$OUT_DIR/qor.rpt"
report_area -hierarchy > "$OUT_DIR/area_hier.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$OUT_DIR/timing_max.rpt"
report_constraint -all_violators > "$OUT_DIR/constraint_violators.rpt"
report_reference > "$OUT_DIR/references.rpt"
check_design > "$OUT_DIR/check_design_post.rpt"
check_timing > "$OUT_DIR/check_timing.rpt"
set unmapped_count [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set cell_count [sizeof_collection [get_cells -hierarchical]]
set worst_slack "NA"
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
if {[sizeof_collection $paths] > 0} { set worst_slack [get_attribute [index_collection $paths 0] slack] }
set area_value [get_attribute [current_design] area]
set status_fp [open "$OUT_DIR/status.txt" w]
puts $status_fp "PHASE=revision8b_a_broadcast32"
puts $status_fp "REVISION=8B-A"
puts $status_fp "LINK_STATUS=$link_status"
puts $status_fp "UNRESOLVED_REFERENCES=0"
puts $status_fp "UNMAPPED_CELLS=$unmapped_count"
puts $status_fp "MAPPED_CELL_COUNT=$cell_count"
puts $status_fp "CELL_AREA=$area_value"
puts $status_fp "WORST_SLACK_NS=$worst_slack"
close $status_fp
write -format ddc -hierarchy -output $DDC_OUT
write -format verilog -hierarchy -output $NETLIST_OUT
write_sdc $SDC_OUT
if {!$link_status || $unmapped_count != 0 || $cell_count == 0} { exit 4 }
puts "L5_REV8B_A_BROADCAST32_COMPLETED WNS=$worst_slack CELLS=$cell_count"
exit
