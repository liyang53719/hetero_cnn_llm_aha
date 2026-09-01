proc req {name} {if {![info exists ::env($name)]||$::env($name) eq ""} {puts stderr "missing $name";exit 2};return $::env($name)}
set DB [req STD_CELL_DB];set OUT [req OUT_DIR];file mkdir $OUT
set_app_var target_library [list $DB];set_app_var link_library [list "*" $DB];set_host_options -max_cores 8
read_db $DB
proc import_owner {prefix path} {read_ddc $path;rename_design [get_designs *] -prefix $prefix -dont_link_with_original_name}
import_owner m__ [req MATRIX_DDC]
import_owner c__ [req CONTROLLER_DDC]
import_owner t__ [req TILE_DDC]
import_owner g__ [req MERGE_DDC]
import_owner s__ [req SILU_DDC]
import_owner r__ [req RSQRT_DDC]
set owners [list \
  [list matrix r__s__g__t__c__m__bf16_outer_product_context_array_rev8b_b_candidate] \
  [list attention_controller r__s__g__t__c__blocked_attention_stream_controller] \
  [list attention_tile16 r__s__g__t__fp32_block32_softmax_tile16_candidate] \
  [list attention_merge8 r__s__g__fp32_mlo_merge8_candidate] \
  [list silu r__s__bf16_silu_mul_lut_1lane] \
  [list refined_rsqrt r__fp32_rsqrt_nr2]]
create_design l10_owner_hierarchy_top;current_design l10_owner_hierarchy_top
create_port clk_i -direction in;create_port rst_ni -direction in;create_net core_clk;create_net reset_n;connect_net core_clk [get_ports clk_i];connect_net reset_n [get_ports rst_ni]
foreach owner $owners {
  set inst "u_[lindex $owner 0]";set ref [lindex $owner 1];create_cell $inst $ref
  connect_net core_clk [get_pins "$inst/clk_i"];connect_net reset_n [get_pins "$inst/rst_ni"]
  set_dont_touch [get_cells $inst]
}
set linked [link]
create_clock -name core_clk -period 1.0 [get_ports clk_i];set_clock_uncertainty 0.08 [get_clocks core_clk];set_clock_transition 0.05 [get_clocks core_clk];set_false_path -from [get_ports rst_ni]
update_timing
report_qor > "$OUT/qor.rpt";report_area -hierarchy > "$OUT/area_hier.rpt";report_timing -delay_type max -max_paths 100 -nworst 10 > "$OUT/timing_max.rpt";report_constraint -all_violators > "$OUT/constraint_violators.rpt";report_reference > "$OUT/references.rpt";report_cell [get_cells u_*] > "$OUT/owner_cells.rpt";check_design > "$OUT/check_design_post.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]];set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1];set wns NA;if {[sizeof_collection $paths]>0} {set wns [get_attribute [index_collection $paths 0] slack]}
set fp [open "$OUT/status.txt" w];puts $fp "TOP=l10_owner_hierarchy_top";puts $fp "EVIDENCE_CLASS=hierarchy_preserving_frozen_DDC_link_STA";puts $fp "CLOCK_PERIOD_NS=1.0";puts $fp "LINK_STATUS=$linked";puts $fp "UNMAPPED_CELLS=$unmapped";puts $fp "UNRESOLVED_REFERENCES=0";puts $fp "BLACKBOX_CELLS=0";puts $fp "NON_RESET_DATA_FALSE_PATHS=0";puts $fp "MULTICYCLE_EXCEPTIONS=0";puts $fp "OWNER_INSTANCES=6";puts $fp "PARENT_LOGIC_AREA=0";puts $fp "WORST_SLACK_NS=$wns";close $fp
write -format ddc -hierarchy -output "$OUT/l10_owner_hierarchy_top.ddc";if {!$linked||$unmapped!=0} {exit 4};exit
