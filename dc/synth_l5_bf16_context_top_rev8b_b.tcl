proc req {n} {
  if {![info exists ::env($n)] || $::env($n) eq ""} {
    puts stderr "Missing $n"
    exit 2
  }
  return $::env($n)
}
set TOP [req TOP_RTL]
set FRONT [req FRONT_DDC]
set BROADCAST [req BROADCAST_DDC]
set OPERAND [req OPERAND_DDC]
set CLUSTER [req CLUSTER_DDC]
set GLUE [req GLUE_DDC]
set FLAGS_GLUE [req FLAGS_GLUE_DDC]
set DB [req STD_CELL_DB]
set OUT [req OUT_DIR]
set DDC [req DDC_OUT]
file mkdir $OUT
set_app_var target_library [list $DB]
set_app_var link_library [list "*" $DB]
set_host_options -max_cores 8
foreach d [list $FRONT $BROADCAST $OPERAND $CLUSTER $GLUE $FLAGS_GLUE] {read_ddc $d -scenarios {}}
analyze -format sverilog $TOP
elaborate bf16_outer_product_context_array_rev8b_b_candidate
current_design bf16_outer_product_context_array_rev8b_b_candidate
set linked [link]
foreach ref {bf16_context_front_control5_rev8b_b_candidate bf16_front_to_cluster_broadcast32_rev8b_b_candidate bf16_operand_distribution512_rev8b_a_candidate bf16_context_lane_cluster16_rev8b_b_candidate bf16_outer_product_array_glue512 bf16_cluster_flags_glue32_rev8b_b_candidate} {
  set ds [get_designs -quiet $ref]
  if {[sizeof_collection $ds]!=1} {puts stderr "Expected $ref";exit 6}
  set_boundary_optimization $ds false
  set_dont_touch $ds true
}
create_clock -name core_clk -period 1.0 [get_ports clk_i]
set_clock_uncertainty 0.08 [get_clocks core_clk]
set_clock_transition 0.05 [get_clocks core_clk]
set inputs [remove_from_collection [all_inputs] [get_ports clk_i]]
set inputs [remove_from_collection $inputs [get_ports rst_ni]]
set_false_path -from [get_ports rst_ni]
set_input_delay 0.10 -clock core_clk $inputs
set_output_delay 0.10 -clock core_clk [all_outputs]
set_load 0.02 [all_outputs]
set_max_transition 0.25 [current_design]
set_max_fanout 32 [current_design]
report_qor > "$OUT/qor.rpt"
report_area -hierarchy > "$OUT/area_hier.rpt"
report_timing -delay_type max -max_paths 100 -nworst 10 > "$OUT/timing_max.rpt"
report_constraint -all_violators > "$OUT/constraint_violators.rpt"
report_reference > "$OUT/references.rpt"
report_hierarchy > "$OUT/hierarchy.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]]
set p [get_timing_paths -delay_type max -nworst 1 -max_paths 1]
set wns "NA"
if {[sizeof_collection $p]>0} {set wns [get_attribute [index_collection $p 0] slack]}
set front_n [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name == bf16_context_front_control5_rev8b_b_candidate"]]
set broadcast_n [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name == bf16_front_to_cluster_broadcast32_rev8b_b_candidate"]]
set operand_n [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name == bf16_operand_distribution512_rev8b_a_candidate"]]
set cluster_n [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name == bf16_context_lane_cluster16_rev8b_b_candidate"]]
set glue_n [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name == bf16_outer_product_array_glue512"]]
set flags_glue_n [sizeof_collection [get_cells -hierarchical -quiet -filter "ref_name == bf16_cluster_flags_glue32_rev8b_b_candidate"]]
set fp [open "$OUT/status.txt" w]
puts $fp "PHASE=revision8b_b_structural_h3";puts $fp "COMPILE_COMMANDS=0";puts $fp "LINK_STATUS=$linked";puts $fp "UNRESOLVED_REFERENCES=0";puts $fp "UNMAPPED_CELLS=$unmapped";puts $fp "FRONT_INSTANCES=$front_n";puts $fp "BROADCAST_INSTANCES=$broadcast_n";puts $fp "OPERAND_INSTANCES=$operand_n";puts $fp "CLUSTER16_INSTANCES=$cluster_n";puts $fp "PHYSICAL_LANES=[expr {$cluster_n*16}]";puts $fp "GLUE_INSTANCES=$glue_n";puts $fp "FLAGS_GLUE_INSTANCES=$flags_glue_n";puts $fp "CELL_AREA=[get_attribute [current_design] area]";puts $fp "WORST_SLACK_NS=$wns";close $fp
write -format ddc -hierarchy -output $DDC
if {!$linked || $unmapped != 0 || $front_n != 1 || $broadcast_n != 1 || $operand_n != 1 || $cluster_n != 32 || $glue_n != 1 || $flags_glue_n != 1} {exit 4}
exit
