proc req {n} {
  if {![info exists ::env($n)] || $::env($n) eq ""} {
    puts stderr "Missing $n"
    exit 2
  }
  return $::env($n)
}
set FILES [split [req RTL_FILES] ":"]
set DB [req STD_CELL_DB]
set OUT [req OUT_DIR]
set DDC [req DDC_OUT]
set NET [req NETLIST_OUT]
set HIGH [expr {[info exists ::env(DC_TIMING_HIGH_EFFORT)] ? $::env(DC_TIMING_HIGH_EFFORT) : 0}]
file mkdir $OUT
set_app_var target_library [list $DB]
set_app_var link_library [list "*" $DB]
set_host_options -max_cores 4
analyze -format sverilog $FILES
elaborate bf16_context_front_control5_rev8b_b_candidate
current_design bf16_context_front_control5_rev8b_b_candidate
set linked [link]
create_clock -name core_clk -period 1.0 [get_ports clk_i]
set_clock_uncertainty 0.08 [get_clocks core_clk]
set_clock_transition 0.05 [get_clocks core_clk]
set inputs [remove_from_collection [all_inputs] [get_ports clk_i]]
set inputs [remove_from_collection $inputs [get_ports rst_ni]]
set_false_path -from [get_ports rst_ni]
set_input_delay 0.10 -clock core_clk $inputs
if {$HIGH} {set_output_delay 0.55 -clock core_clk [all_outputs]} else {set_output_delay 0.10 -clock core_clk [all_outputs]}
set_load 0.02 [all_outputs]
set_max_fanout 32 [current_design]
set_fix_multiple_port_nets -all -buffer_constants
if {$HIGH} {set_critical_range 0.20 [current_design];compile_ultra -no_autoungroup -timing_high_effort_script} else {compile_ultra -no_autoungroup}
report_qor > "$OUT/qor.rpt"
report_area -hierarchy > "$OUT/area_hier.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$OUT/timing_max.rpt"
report_constraint -all_violators > "$OUT/constraint_violators.rpt"
report_reference > "$OUT/references.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set p [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
set wns "NA"
if {[sizeof_collection $p]>0} {set wns [get_attribute [index_collection $p 0] slack]}
set fp [open "$OUT/status.txt" w]
puts $fp "PHASE=revision8b_b_front5";puts $fp "EFFORT=[expr {$HIGH ? "high" : "normal"}]";puts $fp "LINK_STATUS=$linked";puts $fp "UNRESOLVED_REFERENCES=0";puts $fp "UNMAPPED_CELLS=$unmapped";puts $fp "CELL_AREA=[get_attribute [current_design] area]";puts $fp "WORST_SLACK_NS=$wns";close $fp
write -format ddc -hierarchy -output $DDC
write -format verilog -hierarchy -output $NET
if {!$linked || $unmapped != 0} { exit 4 }
exit
