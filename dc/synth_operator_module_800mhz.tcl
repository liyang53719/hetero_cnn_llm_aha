proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    puts stderr "Missing required environment variable $name"
    exit 2
  }
  return $::env($name)
}

set top [require_env TOP]
set rtl_files [split [require_env RTL_FILES] ":"]
set std_cell_db [require_env STD_CELL_DB]
set clock_port [expr {[info exists ::env(CLOCK_PORT)] ? $::env(CLOCK_PORT) : "clock"}]
set out_dir [require_env OUT_DIR]
file mkdir $out_dir

set_app_var target_library [list $std_cell_db]
set_app_var link_library [list "*" $std_cell_db]
set_host_options -max_cores 8
analyze -format sverilog -define SYNTHESIS $rtl_files
elaborate $top
current_design $top
link
check_design > "$out_dir/check_design_pre.rpt"

source [file join [file dirname [info script]] common_clock_800mhz.tcl]
hetero_apply_primary_clock $clock_port hetero_clk
set_max_transition 0.25 [current_design]
set_max_fanout 32 [current_design]
set_fix_multiple_port_nets -all -buffer_constants
compile_ultra -no_autoungroup

report_qor > "$out_dir/qor.rpt"
report_area -hierarchy > "$out_dir/area_hier.rpt"
report_reference > "$out_dir/references.rpt"
report_resources > "$out_dir/resources.rpt"
report_clocks > "$out_dir/clocks.rpt"
report_constraint -all_violators > "$out_dir/constraints.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$out_dir/timing_max.rpt"
report_timing -delay_type min -max_paths 20 -nworst 3 > "$out_dir/timing_min.rpt"
check_design > "$out_dir/check_design_post.rpt"
check_timing > "$out_dir/check_timing.rpt"

set unmapped_count [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set worst_slack NA
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
if {[sizeof_collection $paths] > 0} {
  set worst_slack [get_attribute [index_collection $paths 0] slack]
}
set total_area 0.0
foreach_in_collection leaf [get_cells -hierarchical -filter "is_hierarchical == false"] {
  set leaf_area [get_attribute -quiet $leaf area]
  if {$leaf_area ne ""} { set total_area [expr {$total_area + $leaf_area}] }
}
set status PASS
if {$unmapped_count != 0} { set status FAIL_UNMAPPED }
if {$worst_slack eq "NA"} { set status FAIL_NO_TIMING_PATH }
if {$worst_slack ne "NA" && $worst_slack < 0.0} { set status FAIL_TIMING }

set fp [open "$out_dir/status.txt" w]
puts $fp "STATUS=$status"
puts $fp "TOP=$top"
puts $fp "CLOCK_NAME=hetero_clk"
puts $fp "CLOCK_PERIOD_NS=1.250"
puts $fp "SETUP_UNCERTAINTY_NS=0.080"
puts $fp "WORST_SLACK_NS=$worst_slack"
puts $fp "UNMAPPED_CELLS=$unmapped_count"
puts $fp "TOTAL_AREA=$total_area"
close $fp
write -format ddc -hierarchy -output "$out_dir/$top.ddc"
write -format verilog -hierarchy -output "$out_dir/$top.mapped.v"
write_sdc "$out_dir/$top.sdc"
exit
