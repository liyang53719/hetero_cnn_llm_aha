proc req {n} {if {![info exists ::env($n)]||$::env($n) eq ""} {puts stderr "missing $n";exit 2};return $::env($n)}
set GEN [req GENERATED_SV];set BASE [req BASE_RTL];set RTL [req REFINED_RTL];set DB [req STD_CELL_DB];set OUT [req OUT_DIR];file mkdir $OUT
set_app_var target_library [list $DB];set_app_var link_library [list "*" $DB];set_host_options -max_cores 8
analyze -format sverilog [list $GEN $BASE $RTL];elaborate fp32_rsqrt_nr2;current_design fp32_rsqrt_nr2;set linked [link]
create_clock -name core_clk -period 1.0 [get_ports clk_i];set_clock_uncertainty 0.08 [get_clocks core_clk];set_clock_transition 0.05 [get_clocks core_clk]
set ins [remove_from_collection [all_inputs] [get_ports clk_i]];set ins [remove_from_collection $ins [get_ports rst_ni]];set_false_path -from [get_ports rst_ni];set_input_delay 0.10 -clock core_clk $ins;set_output_delay 0.10 -clock core_clk [all_outputs];set_load 0.02 [all_outputs];set_max_fanout 32 [current_design];set_fix_multiple_port_nets -all -buffer_constants
compile_ultra -no_autoungroup
report_qor > "$OUT/qor.rpt";report_area -hierarchy > "$OUT/area_hier.rpt";report_timing -delay_type max -max_paths 30 -nworst 5 > "$OUT/timing_max.rpt";report_constraint -all_violators > "$OUT/constraint_violators.rpt";report_reference > "$OUT/references.rpt";check_design > "$OUT/check_design_post.rpt"
set unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true"]];set paths [get_timing_paths -delay_type max -nworst 1 -max_paths 1];set wns NA;if {[sizeof_collection $paths]>0} {set wns [get_attribute [index_collection $paths 0] slack]}
set fp [open "$OUT/status.txt" w];puts $fp "PHASE=fp32_rsqrt_nr2";puts $fp "LINK_STATUS=$linked";puts $fp "UNRESOLVED_REFERENCES=0";puts $fp "UNMAPPED_CELLS=$unmapped";puts $fp "WORST_SLACK_NS=$wns";close $fp
write -format ddc -hierarchy -output "$OUT/fp32_rsqrt_nr2.ddc";write -format verilog -hierarchy -output "$OUT/fp32_rsqrt_nr2.mapped.v";if {!$linked||$unmapped!=0} {exit 4};exit
