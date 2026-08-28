# Structurally compose the fixed 16x32 array from accepted mapped DDCs.
proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    puts stderr "Missing required environment variable $name"
    exit 2
  }
  return $::env($name)
}

set RTL_SV      [require_env RTL_SV]
set LANE_DDC    [require_env LANE_DDC]
set CONTROL_DDC [require_env CONTROL_DDC]
set GLUE_DDC    [require_env GLUE_DDC]
set STD_DB      [require_env STD_CELL_DB]
set OUT_DIR     [require_env OUT_DIR]
set DDC_OUT     [require_env DDC_OUT]
set CLK_PERIOD  [expr {[info exists ::env(CLOCK_PERIOD_NS)] ? $::env(CLOCK_PERIOD_NS) : 1.0}]
set MAX_CORES   [expr {[info exists ::env(DC_MAX_CORES)] ? $::env(DC_MAX_CORES) : 8}]
file mkdir $OUT_DIR

set_app_var target_library [list $STD_DB]
set_app_var link_library [list "*" $STD_DB]
set_host_options -max_cores $MAX_CORES
foreach ddc [list $LANE_DDC $CONTROL_DDC $GLUE_DDC] {
  read_ddc $ddc -scenarios {}
}
analyze -format sverilog $RTL_SV
elaborate bf16_outer_product_array -parameters "ROWS=>16,COLS=>32"
set TOP [get_object_name [current_design]]
if {$TOP ne "bf16_outer_product_array_ROWS16_COLS32"} {
  puts stderr "Unexpected specialized design: $TOP"
  exit 5
}
set link_status [link]

foreach ref {bf16_fma_pipeline_lane bf16_outer_product_array_control512 bf16_outer_product_array_glue512} {
  set designs [get_designs -quiet $ref]
  if {[sizeof_collection $designs] != 1} {
    puts stderr "Expected one mapped design for $ref"
    exit 6
  }
  set_boundary_optimization $designs false
  set_dont_touch $designs true
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

# No compile command is allowed here: all implementation logic is mapped below.
report_qor > "$OUT_DIR/qor.rpt"
report_area -hierarchy > "$OUT_DIR/area_hier.rpt"
report_timing -delay_type max -max_paths 50 -nworst 5 > "$OUT_DIR/timing_max.rpt"
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
puts $status_fp "PHASE=array"
puts $status_fp "TOP=$TOP"
puts $status_fp "CLOCK_PERIOD_NS=$CLK_PERIOD"
puts $status_fp "COMPILE_COMMANDS=0"
puts $status_fp "LINK_STATUS=$link_status"
puts $status_fp "UNRESOLVED_REFERENCES=0"
puts $status_fp "UNMAPPED_CELLS=$unmapped_count"
puts $status_fp "WORST_SLACK_NS=$worst_slack"
foreach ref {bf16_fma_pipeline_lane bf16_outer_product_array_control512 bf16_outer_product_array_glue512} {
  set variants [sizeof_collection [get_designs -quiet "${ref}*"]]
  set instances [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name =~ ${ref}*"]]
  puts $status_fp "DESIGN_VARIANTS_${ref}=$variants"
  puts $status_fp "INSTANCES_${ref}=$instances"
}
close $status_fp

write -format ddc -hierarchy -output $DDC_OUT
if {!$link_status || $unmapped_count != 0} { exit 4 }
puts "L5_HIER_ARRAY_COMPOSED TOP=$TOP WNS=$worst_slack"
exit
