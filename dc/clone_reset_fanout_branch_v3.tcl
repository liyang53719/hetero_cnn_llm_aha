proc need {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {error "missing $name"}
  return $::env($name)
}
set input [need INPUT_DDC]
set out [need OUT_DIR]
set db [need STD_CELL_DB]
file mkdir $out
set_app_var target_library [list $db]
set_app_var link_library [list "*" $db]
read_ddc $input
for {set index 0} {$index < 9} {incr index} {
  set name "operator_reset_fanout_branch_v3_$index"
  copy_design operator_reset_fanout_branch_v3 $name
  current_design $name
  write -format ddc -output "$out/$name.ddc"
}
exit
