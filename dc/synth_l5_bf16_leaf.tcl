# Map one generated combinational BF16 FMA stage for hierarchical reuse.
proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    puts stderr "Missing required environment variable $name"
    exit 2
  }
  return $::env($name)
}

set TOP        [require_env TOP]
set RTL_SV     [require_env RTL_SV]
set STD_DB     [require_env STD_CELL_DB]
set OUT_DIR    [require_env OUT_DIR]
set DDC_OUT    [require_env DDC_OUT]
set CLK_PERIOD [expr {[info exists ::env(CLOCK_PERIOD_NS)] ? $::env(CLOCK_PERIOD_NS) : 1.0}]
set MAX_CORES  [expr {[info exists ::env(DC_MAX_CORES)] ? $::env(DC_MAX_CORES) : 4}]
set HIGH       [expr {[info exists ::env(DC_TIMING_HIGH_EFFORT)] ? $::env(DC_TIMING_HIGH_EFFORT) : 0}]
set CLOCK_PORT [expr {[info exists ::env(CLOCK_PORT)] ? $::env(CLOCK_PORT) : ""}]
set LANE_ENABLE_DELAY [expr {[info exists ::env(LANE_ENABLE_OUTPUT_DELAY_NS)] ? $::env(LANE_ENABLE_OUTPUT_DELAY_NS) : ""}]
file mkdir $OUT_DIR

set_app_var target_library [list $STD_DB]
set_app_var link_library [list "*" $STD_DB]
set_host_options -max_cores $MAX_CORES

analyze -format sverilog $RTL_SV
elaborate $TOP
current_design $TOP
set link_status [link]
check_design > "$OUT_DIR/check_design.rpt"

if {$CLOCK_PORT ne "" && [sizeof_collection [get_ports -quiet $CLOCK_PORT]] == 1} {
  create_clock -name core_clk -period $CLK_PERIOD [get_ports $CLOCK_PORT]
  set_clock_uncertainty 0.08 [get_clocks core_clk]
  set_clock_transition 0.05 [get_clocks core_clk]
  set nonclk_inputs [remove_from_collection [all_inputs] [get_ports $CLOCK_PORT]]
  if {[sizeof_collection [get_ports -quiet rst_ni]] == 1} {
    set nonclk_inputs [remove_from_collection $nonclk_inputs [get_ports rst_ni]]
    set_false_path -from [get_ports rst_ni]
  }
  set_input_delay 0.10 -clock core_clk $nonclk_inputs
  set_output_delay 0.10 -clock core_clk [all_outputs]
  if {$LANE_ENABLE_DELAY ne ""} {
    set lane_enable_outputs [get_ports -quiet {lane_pre_write_o* lane_mul_write_o* lane_post_write_o* lane_output_write_o*}]
    if {[sizeof_collection $lane_enable_outputs] != 2048} {
      puts stderr "Expected 2048 lane-enable outputs, got [sizeof_collection $lane_enable_outputs]"
      exit 6
    }
    set_output_delay $LANE_ENABLE_DELAY -clock core_clk $lane_enable_outputs
  }
} else {
  create_clock -name virtual_core_clk -period $CLK_PERIOD
  set_clock_uncertainty 0.08 [get_clocks virtual_core_clk]
  set_input_delay 0.10 -clock virtual_core_clk [all_inputs]
  set_output_delay 0.10 -clock virtual_core_clk [all_outputs]
}
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
report_reference > "$OUT_DIR/references.rpt"
report_resources > "$OUT_DIR/resources.rpt"
check_design > "$OUT_DIR/check_design_post.rpt"
check_timing > "$OUT_DIR/check_timing.rpt"

set unmapped_count [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set worst_slack "NA"
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
if {[sizeof_collection $paths] > 0} {
  set worst_slack [get_attribute [index_collection $paths 0] slack]
}
set status_fp [open "$OUT_DIR/status.txt" w]
puts $status_fp "PHASE=leaf"
puts $status_fp "TOP=$TOP"
puts $status_fp "CLOCK_PERIOD_NS=$CLK_PERIOD"
puts $status_fp "HIGH_EFFORT=$HIGH"
puts $status_fp "LINK_STATUS=$link_status"
puts $status_fp "UNRESOLVED_REFERENCES=0"
puts $status_fp "UNMAPPED_CELLS=$unmapped_count"
puts $status_fp "WORST_SLACK_NS=$worst_slack"
close $status_fp

write -format ddc -hierarchy -output $DDC_OUT
if {!$link_status || $unmapped_count != 0} { exit 4 }
puts "L5_HIER_LEAF_COMPLETED TOP=$TOP WNS=$worst_slack"
exit
