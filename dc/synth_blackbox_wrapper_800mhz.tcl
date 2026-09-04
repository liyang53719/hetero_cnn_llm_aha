proc need {n} {if {![info exists ::env($n)]||$::env($n) eq ""} {error "missing $n"};return $::env($n)}
set top [need TOP];set rtl [split [need RTL_FILES] ":"];set child [need CHILD_REF];set db [need STD_CELL_DB];set out [need OUT_DIR];file mkdir $out
set_app_var target_library [list $db];set_app_var link_library [list "*" $db];set_host_options -max_cores 8
analyze -format sverilog -define SYNTHESIS $rtl;elaborate $top;current_design $top;link
set design [get_designs -quiet $child];if {[sizeof_collection $design]!=1} {error "missing child"};set_dont_touch $design true
source [file join [file dirname [info script]] common_clock_800mhz.tcl];hetero_apply_primary_clock clk_i hetero_clk
set_max_transition 0.25 [current_design];set_max_fanout 32 [current_design];set_fix_multiple_port_nets -all -buffer_constants;compile -map_effort low
report_qor > "$out/qor.rpt";report_area -hierarchy > "$out/area_hier.rpt";report_reference > "$out/references.rpt";check_design > "$out/check_design_post.rpt"
set top_unmapped [sizeof_collection [get_cells -hierarchical -filter "is_unmapped == true && ref_name != $child"]]
set fp [open "$out/status.txt" w];puts $fp "STATUS=[expr {$top_unmapped==0 ? {PASS_WRAPPER_MAP} : {FAIL_UNMAPPED}}]";puts $fp "TOP=$top";puts $fp "CHILD_BLACKBOX=$child";puts $fp "TOP_UNMAPPED_EXCLUDING_CHILD=$top_unmapped";close $fp
write -format ddc -output "$out/$top.shell.ddc";exit
