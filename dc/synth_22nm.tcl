# Generic Synopsys Design Compiler script for the 22nm standard-cell gate.
# Required environment variables:
#   TOP, RTL_FILELIST, STD_CELL_DBS
# Optional:
#   CLOCK_PORT (default clk_i), CLOCK_PERIOD_NS (default 1.0), OUT_DIR

proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    puts stderr "Missing required environment variable $name"
    exit 2
  }
  return $::env($name)
}

set TOP          [require_env TOP]
set RTL_FILELIST [require_env RTL_FILELIST]
set STD_CELL_DBS [require_env STD_CELL_DBS]
set CLOCK_PORT   [expr {[info exists ::env(CLOCK_PORT)] ? $::env(CLOCK_PORT) : "clk_i"}]
set CLK_PERIOD   [expr {[info exists ::env(CLOCK_PERIOD_NS)] ? $::env(CLOCK_PERIOD_NS) : 1.0}]
set OUT_DIR      [expr {[info exists ::env(OUT_DIR)] ? $::env(OUT_DIR) : "work/dc/$TOP"}]
set MAX_CORES    [expr {[info exists ::env(DC_MAX_CORES)] ? $::env(DC_MAX_CORES) : 4}]
file mkdir $OUT_DIR

set dbs [split $STD_CELL_DBS ":"]
set_app_var target_library $dbs
set_app_var link_library [concat "*" $dbs]
set_app_var search_path [concat $search_path [list . [file dirname $RTL_FILELIST]]]

set rtl_files {}
set fp [open $RTL_FILELIST r]
while {[gets $fp line] >= 0} {
  set line [string trim $line]
  if {$line eq "" || [string match "#*" $line]} { continue }
  lappend rtl_files $line
}
close $fp
if {[llength $rtl_files] == 0} {
  puts stderr "RTL file list is empty: $RTL_FILELIST"
  exit 3
}

set_host_options -max_cores $MAX_CORES
analyze -format sverilog $rtl_files
elaborate $TOP
current_design $TOP
link
check_design > "$OUT_DIR/check_design.rpt"

if {[sizeof_collection [get_ports -quiet $CLOCK_PORT]] > 0} {
  create_clock -name core_clk -period $CLK_PERIOD [get_ports $CLOCK_PORT]
  set_clock_uncertainty 0.08 [get_clocks core_clk]
  set_clock_transition 0.05 [get_clocks core_clk]
  set nonclk_inputs [remove_from_collection [all_inputs] [get_ports $CLOCK_PORT]]
  if {[sizeof_collection [get_ports -quiet rst_ni]] > 0} {
    set nonclk_inputs [remove_from_collection $nonclk_inputs [get_ports rst_ni]]
    set_false_path -from [get_ports rst_ni]
  }
  if {[sizeof_collection $nonclk_inputs] > 0} {
    set_input_delay 0.10 -clock core_clk $nonclk_inputs
  }
  if {[sizeof_collection [all_outputs]] > 0} {
    set_output_delay 0.10 -clock core_clk [all_outputs]
    set_load 0.02 [all_outputs]
  }
}
set_max_fanout 32 [current_design]
set_fix_multiple_port_nets -all -buffer_constants

compile_ultra -no_autoungroup

report_qor                         > "$OUT_DIR/qor.rpt"
report_area -hierarchy             > "$OUT_DIR/area_hier.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$OUT_DIR/timing_max.rpt"
report_timing -delay_type min -max_paths 20 -nworst 3 > "$OUT_DIR/timing_min.rpt"
report_reference                   > "$OUT_DIR/references.rpt"
report_resources                   > "$OUT_DIR/resources.rpt"
report_power                       > "$OUT_DIR/power_estimate.rpt"
check_design                       > "$OUT_DIR/check_design_post.rpt"
check_timing                       > "$OUT_DIR/check_timing.rpt"

set unmapped [get_cells -hierarchical -filter "is_unmapped == true"]
set unmapped_count [sizeof_collection $unmapped]
set worst_slack "NA"
set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
if {[sizeof_collection $paths] > 0} {
  set worst_slack [get_attribute [index_collection $paths 0] slack]
}
set status_fp [open "$OUT_DIR/status.txt" w]
puts $status_fp "TOP=$TOP"
puts $status_fp "CLOCK_PERIOD_NS=$CLK_PERIOD"
puts $status_fp "UNMAPPED_CELLS=$unmapped_count"
puts $status_fp "WORST_SLACK_NS=$worst_slack"
close $status_fp

write -format ddc -hierarchy -output "$OUT_DIR/$TOP.ddc"
write -format verilog -hierarchy -output "$OUT_DIR/$TOP.mapped.v"
write_sdc "$OUT_DIR/$TOP.sdc"

if {$unmapped_count != 0} {
  puts stderr "DC gate failed: $unmapped_count unmapped cells"
  exit 4
}
puts "DC_SYNTHESIS_COMPLETED TOP=$TOP WNS=$worst_slack"
exit
