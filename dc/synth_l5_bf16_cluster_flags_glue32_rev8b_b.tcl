proc req {n} {
  if {![info exists ::env($n)] || $::env($n) eq ""} {
    puts stderr "Missing $n"
    exit 2
  }
  return $::env($n)
}
set RTL [req FLAGS_RTL]
set DB [req STD_CELL_DB]
set OUT [req OUT_DIR]
set DDC [req DDC_OUT]
set NET [req NETLIST_OUT]
file mkdir $OUT
set_app_var target_library [list $DB]
set_app_var link_library [list "*" $DB]
set_host_options -max_cores 4
analyze -format sverilog $RTL
elaborate bf16_cluster_flags_glue32_rev8b_b_candidate
current_design bf16_cluster_flags_glue32_rev8b_b_candidate
set linked [link]
create_clock -name virtual_core -period 1.0
set_clock_uncertainty 0.08 [get_clocks virtual_core]
set_input_delay 0.10 -clock virtual_core [all_inputs]
set_output_delay 0.10 -clock virtual_core [all_outputs]
set_input_transition 0.05 [all_inputs]
set_load 0.10 [all_outputs]
set_max_transition 0.23 [current_design]
set_max_fanout 32 [current_design]
set_fix_multiple_port_nets -all -buffer_constants
compile_ultra -no_autoungroup
report_qor > "$OUT/qor.rpt"
report_area -hierarchy > "$OUT/area_hier.rpt"
report_timing -delay_type max -max_paths 20 > "$OUT/timing_max.rpt"
report_constraint -all_violators > "$OUT/constraint_violators.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set p [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
set wns "NA"
if {[sizeof_collection $p]>0} {set wns [get_attribute [index_collection $p 0] slack]}
set fp [open "$OUT/status.txt" w]
puts $fp "PHASE=revision8b_b_flags_glue32";puts $fp "EFFORT=normal";puts $fp "LINK_STATUS=$linked";puts $fp "UNRESOLVED_REFERENCES=0";puts $fp "UNMAPPED_CELLS=$unmapped";puts $fp "CELL_AREA=[get_attribute [current_design] area]";puts $fp "WORST_SLACK_NS=$wns";close $fp
write -format ddc -hierarchy -output $DDC
write -format verilog -hierarchy -output $NET
if {!$linked || $unmapped != 0} {exit 4}
exit
