proc need {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {error "missing $name"}
  return $::env($name)
}
set std [need STD_CELL_DB]
set macro_dbs [split [need SRAM_DBS] ":"]
set operator_ddc [need OPERATOR_DDC]
set sram_ddc [need SRAM_DDC]
set out [need OUT_DIR]
file mkdir $out
set_app_var target_library [list $std]
set_app_var link_library [concat [list "*" $std] $macro_dbs]
set_host_options -max_cores 8
read_ddc $operator_ddc
read_ddc $sram_ddc
create_design operator_macro_inventory_shell_v3
current_design operator_macro_inventory_shell_v3
create_port clk_i -direction in
create_port rst_ni -direction in
create_net clk_net
create_net rst_net
connect_net clk_net [get_ports clk_i]
connect_net rst_net [get_ports rst_ni]
create_cell u_operator operator_root_bridge_owner_shell_v3
create_cell u_sram l10_sram_macro_inventory_top
connect_net clk_net [get_pins u_operator/clk_i]
connect_net clk_net [get_pins u_sram/clk_i]
connect_net rst_net [get_pins u_operator/rst_ni]
link
source [file join [file dirname [info script]] common_clock_800mhz.tcl]
hetero_apply_primary_clock clk_i hetero_clk
set_max_transition 0.25 [current_design]
set_max_fanout 32 [current_design]
report_qor > "$out/qor.rpt"
report_area -hierarchy > "$out/area_hier.rpt"
report_reference > "$out/references.rpt"
report_constraint -all_violators > "$out/constraints.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$out/timing_max.rpt"
check_design > "$out/check_design_post.rpt"
check_timing > "$out/check_timing.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set macro_count 0
foreach ref {l2sp6144x128wm ctsp4096x128wm dp2048x64wm dp4096x32wm} {
  set macro_count [expr {$macro_count + [sizeof_collection [get_cells -hierarchical -filter "ref_name == $ref"]]}]
}
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
set wns NA
if {[sizeof_collection $paths] > 0} {set wns [get_attribute [index_collection $paths 0] slack]}
set area NA
redirect -variable area_text {report_area}
regexp {Total cell area:[[:space:]]+([0-9.]+)} $area_text match area
set status PASS
if {$unmapped != 0} {set status FAIL_UNMAPPED}
if {$macro_count != 124} {set status FAIL_MACRO_COUNT}
if {$wns eq "NA" || ($wns ne "NA" && $wns < 0)} {set status FAIL_TIMING}
set fp [open "$out/status.txt" w]
puts $fp "STATUS=$status"
puts $fp "TOP=operator_macro_inventory_shell_v3"
puts $fp "CLOCK_PERIOD_NS=1.250"
puts $fp "WORST_SLACK_NS=$wns"
puts $fp "UNMAPPED_CELLS=$unmapped"
puts $fp "PHYSICAL_MACROS=$macro_count"
puts $fp "TOTAL_CELL_AREA=$area"
close $fp
write -format ddc -hierarchy -output "$out/operator_macro_inventory_shell_v3.ddc"
exit
