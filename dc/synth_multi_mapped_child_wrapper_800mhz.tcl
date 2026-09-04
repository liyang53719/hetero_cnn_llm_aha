proc need {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {error "missing $name"}
  return $::env($name)
}
set top [need TOP]
set rtl [split [need RTL_FILES] ":"]
set ddcs [split [need CHILD_DDCS] ":"]
set refs [split [need CHILD_REFS] ":"]
set db [need STD_CELL_DB]
set out [need OUT_DIR]
set max_transition [expr {[info exists ::env(MAX_TRANSITION_NS)] ? $::env(MAX_TRANSITION_NS) : 0.25}]
file mkdir $out
set_app_var target_library [list $db]
set_app_var link_library [list "*" $db]
set_host_options -max_cores 8
foreach ddc $ddcs {read_ddc $ddc}
analyze -format sverilog -define SYNTHESIS $rtl
elaborate $top
current_design $top
link
foreach ref $refs {
  set design [get_designs -quiet $ref]
  if {[sizeof_collection $design] != 1} {error "missing child $ref"}
  set_boundary_optimization $design false
  set_dont_touch $design true
}
source [file join [file dirname [info script]] common_clock_800mhz.tcl]
hetero_apply_primary_clock clk_i hetero_clk
if {[info exists ::env(INPUT_DELAY_NS)] && $::env(INPUT_DELAY_NS) ne ""} {
  set constrained_inputs [remove_from_collection [all_inputs] [get_ports clk_i]]
  set_input_delay $::env(INPUT_DELAY_NS) -clock [get_clocks hetero_clk] $constrained_inputs
}
set_max_transition $max_transition [current_design]
set_max_fanout 32 [current_design]
set_fix_multiple_port_nets -all -buffer_constants
set map_effort [expr {[info exists ::env(MAP_EFFORT)] ? $::env(MAP_EFFORT) : "low"}]
if {$map_effort eq "high"} {set_critical_range 0.10 [current_design]}
compile -map_effort $map_effort
report_qor > "$out/qor.rpt"
report_area -hierarchy > "$out/area_hier.rpt"
report_reference > "$out/references.rpt"
report_constraint -all_violators > "$out/constraints.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$out/timing_max.rpt"
check_design > "$out/check_design_post.rpt"
check_timing > "$out/check_timing.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
set wns NA
if {[sizeof_collection $paths] > 0} {set wns [get_attribute [index_collection $paths 0] slack]}
set area 0.0
foreach_in_collection leaf [get_cells -hierarchical -filter "is_hierarchical == false"] {
  set value [get_attribute -quiet $leaf area]
  if {$value ne ""} {set area [expr {$area + $value}]}
}
set status PASS
if {$unmapped != 0} {set status FAIL_UNMAPPED}
if {$wns eq "NA" || ($wns ne "NA" && $wns < 0)} {set status FAIL_TIMING}
set fp [open "$out/status.txt" w]
puts $fp "STATUS=$status"
puts $fp "TOP=$top"
puts $fp "CLOCK_PERIOD_NS=1.250"
puts $fp "WORST_SLACK_NS=$wns"
puts $fp "UNMAPPED_CELLS=$unmapped"
puts $fp "TOTAL_AREA=$area"
close $fp
write -format ddc -hierarchy -output "$out/$top.ddc"
exit
