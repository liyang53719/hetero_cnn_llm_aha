proc need {n} {if {![info exists ::env($n)]||$::env($n) eq ""} {error "missing $n"};return $::env($n)}
set top [need TOP];set rtl [split [need RTL_FILES] ":"];set refs [split [need OWNER_REFS] ":"];set db [need STD_CELL_DB];set out [need OUT_DIR];file mkdir $out
set_app_var target_library [list $db];set_app_var link_library [list "*" $db];set_host_options -max_cores 8
analyze -format sverilog -define SYNTHESIS $rtl;elaborate $top;current_design $top;link
foreach ref $refs {set d [get_designs -quiet $ref];if {[sizeof_collection $d]!=1} {error "missing $ref"};set_dont_touch $d true}
source [file join [file dirname [info script]] common_clock_800mhz.tcl];hetero_apply_primary_clock clk_i hetero_clk
set_max_transition 0.25 [current_design];set_max_fanout 32 [current_design];set_fix_multiple_port_nets -all -buffer_constants;compile -map_effort low
report_qor > "$out/qor.rpt";report_area -hierarchy > "$out/area_hier.rpt";report_reference > "$out/references.rpt";check_design > "$out/check_design_post.rpt"
set unexpected 0;foreach_in_collection c [get_cells -hierarchical -filter "is_unmapped == true"] {set r [get_attribute $c ref_name];if {[lsearch -exact $refs $r]<0} {incr unexpected}}
set fp [open "$out/status.txt" w];puts $fp "STATUS=[expr {$unexpected==0 ? {PASS_WRAPPER_MAP} : {FAIL_UNMAPPED}}]";puts $fp "TOP=$top";puts $fp "OWNER_BLACKBOXES=[llength $refs]";puts $fp "UNEXPECTED_UNMAPPED=$unexpected";close $fp
write -format ddc -output "$out/$top.shell.ddc";exit
