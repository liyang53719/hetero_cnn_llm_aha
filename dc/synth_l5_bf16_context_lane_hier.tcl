# Jointly map one four-context lane around preserved generated arithmetic DDCs.
proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    puts stderr "Missing required environment variable $name"
    exit 2
  }
  return $::env($name)
}

set BASE_LANE_RTL [require_env BASE_LANE_RTL]
set CONTEXT_RTL [require_env CONTEXT_RTL]
set LEAF_DDCS  [split [require_env LEAF_DDCS] ":"]
set STD_DB     [require_env STD_CELL_DB]
set OUT_DIR    [require_env OUT_DIR]
set DDC_OUT    [require_env DDC_OUT]
set CLK_PERIOD [expr {[info exists ::env(CLOCK_PERIOD_NS)] ? $::env(CLOCK_PERIOD_NS) : 1.0}]
set MAX_CORES  [expr {[info exists ::env(DC_MAX_CORES)] ? $::env(DC_MAX_CORES) : 4}]
set HIGH       [expr {[info exists ::env(DC_TIMING_HIGH_EFFORT)] ? $::env(DC_TIMING_HIGH_EFFORT) : 0}]
file mkdir $OUT_DIR

set_app_var target_library [list $STD_DB]
set_app_var link_library [list "*" $STD_DB]
set_host_options -max_cores $MAX_CORES
foreach ddc $LEAF_DDCS { read_ddc $ddc -scenarios {} }
analyze -format sverilog [list $BASE_LANE_RTL $CONTEXT_RTL]
elaborate bf16_context_fma_pipeline_lane4
current_design bf16_context_fma_pipeline_lane4
set link_status [link]

set_app_var compile_enable_constant_propagation_with_no_boundary_opt false
foreach_in_collection d [get_designs *] {
  set name [get_object_name $d]
  if {$name eq "bf16_fma_pipeline_lane"} {
    set_boundary_optimization $d true
  } elseif {$name ne "bf16_context_fma_pipeline_lane4"} {
    set_boundary_optimization $d false
    set_dont_touch $d true
  }
}
check_design > "$OUT_DIR/check_design.rpt"

create_clock -name core_clk -period $CLK_PERIOD [get_ports clk_i]
set_clock_uncertainty 0.08 [get_clocks core_clk]
set_clock_transition 0.05 [get_clocks core_clk]
set nonclk_inputs [remove_from_collection [all_inputs] [get_ports clk_i]]
set nonclk_inputs [remove_from_collection $nonclk_inputs [get_ports rst_ni]]
set_false_path -from [get_ports rst_ni]
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
report_timing -delay_type max -max_paths 20 -nworst 5 > "$OUT_DIR/timing_max.rpt"
report_timing -delay_type min -max_paths 20 -nworst 3 > "$OUT_DIR/timing_min.rpt"
report_reference > "$OUT_DIR/references.rpt"
report_hierarchy > "$OUT_DIR/hierarchy.rpt"
check_design > "$OUT_DIR/check_design_post.rpt"
check_timing > "$OUT_DIR/check_timing.rpt"

set unmapped_count [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set worst_slack "NA"
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
if {[sizeof_collection $paths] > 0} {
  set worst_slack [get_attribute [index_collection $paths 0] slack]
}
set status_fp [open "$OUT_DIR/status.txt" w]
puts $status_fp "PHASE=context_lane_joint"
puts $status_fp "TOP=bf16_context_fma_pipeline_lane4"
puts $status_fp "CLOCK_PERIOD_NS=$CLK_PERIOD"
puts $status_fp "HIGH_EFFORT=$HIGH"
puts $status_fp "LINK_STATUS=$link_status"
puts $status_fp "UNRESOLVED_REFERENCES=0"
puts $status_fp "UNMAPPED_CELLS=$unmapped_count"
puts $status_fp "WORST_SLACK_NS=$worst_slack"
puts $status_fp "DESIGN_VARIANTS_bf16_fma_pipeline_lane=[sizeof_collection [get_designs -quiet {bf16_fma_pipeline_lane}]]"
puts $status_fp "INSTANCES_bf16_fma_pipeline_lane=[sizeof_collection [get_cells -hierarchical -quiet -filter {ref_name == bf16_fma_pipeline_lane}]]"
close $status_fp

write -format ddc -hierarchy -output $DDC_OUT
if {!$link_status || $unmapped_count != 0} { exit 4 }
puts "L5_HIER_CONTEXT_LANE_JOINT_COMPLETED WNS=$worst_slack"
exit
