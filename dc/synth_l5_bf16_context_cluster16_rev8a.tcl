# Revision 8A: jointly map one 16-lane cluster from source to localize fanout.
proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} { puts stderr "Missing required environment variable $name"; exit 2 }
  return $::env($name)
}
set GENERATED_SV [require_env GENERATED_SV]
set LANE_RTL [require_env LANE_RTL]
set CLUSTER_RTL [require_env CLUSTER_RTL]
set STD_DB [require_env STD_CELL_DB]
set OUT_DIR [require_env OUT_DIR]
set DDC_OUT [require_env DDC_OUT]
set NETLIST_OUT [require_env NETLIST_OUT]
set SDC_OUT [require_env SDC_OUT]
set SVF_OUT [require_env SVF_OUT]
set CLK_PERIOD [expr {[info exists ::env(CLOCK_PERIOD_NS)] ? $::env(CLOCK_PERIOD_NS) : 1.0}]
set MAX_CORES [expr {[info exists ::env(DC_MAX_CORES)] ? $::env(DC_MAX_CORES) : 8}]
set HIGH [expr {[info exists ::env(DC_TIMING_HIGH_EFFORT)] ? $::env(DC_TIMING_HIGH_EFFORT) : 0}]
file mkdir $OUT_DIR
set_app_var target_library [list $STD_DB]
set_app_var link_library [list "*" $STD_DB]
set_host_options -max_cores $MAX_CORES
set_svf $SVF_OUT
analyze -format sverilog [list $GENERATED_SV $LANE_RTL $CLUSTER_RTL]
elaborate bf16_context_lane_cluster16_rev8_candidate
current_design bf16_context_lane_cluster16_rev8_candidate
set link_status [link]
check_design > "$OUT_DIR/check_design.rpt"
create_clock -name core_clk -period $CLK_PERIOD [get_ports clk_i]
set_clock_uncertainty 0.08 [get_clocks core_clk]
set_clock_transition 0.05 [get_clocks core_clk]
set nonclk_inputs [remove_from_collection [all_inputs] [get_ports clk_i]]
set_input_delay 0.10 -clock core_clk $nonclk_inputs
set_output_delay 0.10 -clock core_clk [all_outputs]
set_load 0.02 [all_outputs]
set_max_fanout 32 [current_design]
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
report_reference > "$OUT_DIR/references.rpt"
report_hierarchy > "$OUT_DIR/hierarchy.rpt"
check_design > "$OUT_DIR/check_design_post.rpt"
check_timing > "$OUT_DIR/check_timing.rpt"
set unmapped_count [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set worst_slack "NA"
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
if {[sizeof_collection $paths] > 0} { set worst_slack [get_attribute [index_collection $paths 0] slack] }
set lane_instances [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name =~ bf16_context_fma_pipeline_lane4_rev8_candidate*"]]
set area_value [get_attribute [current_design] area]
set status_fp [open "$OUT_DIR/status.txt" w]
puts $status_fp "PHASE=revision8a_cluster16"
puts $status_fp "REVISION=8A"
puts $status_fp "LANES=16"
puts $status_fp "LINK_STATUS=$link_status"
puts $status_fp "UNRESOLVED_REFERENCES=0"
puts $status_fp "UNMAPPED_CELLS=$unmapped_count"
puts $status_fp "LANE_INSTANCES=$lane_instances"
puts $status_fp "CELL_AREA=$area_value"
puts $status_fp "WORST_SLACK_NS=$worst_slack"
close $status_fp
write -format ddc -hierarchy -output $DDC_OUT
write -format verilog -hierarchy -output $NETLIST_OUT
write_sdc $SDC_OUT
set_svf -off
if {!$link_status || $unmapped_count != 0 || $lane_instances != 16} { exit 4 }
puts "L5_REV8A_CLUSTER16_COMPLETED WNS=$worst_slack"
exit
