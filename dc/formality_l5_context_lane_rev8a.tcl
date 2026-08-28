# Formality template for Revision 8A lane source-to-mapped equivalence.
proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} { puts stderr "Missing required environment variable $name"; exit 2 }
  return $::env($name)
}
set GENERATED_SV [require_env GENERATED_SV]
set LANE_RTL [require_env LANE_RTL]
set IMPL_NETLIST [require_env IMPL_NETLIST]
set STD_DB [require_env STD_CELL_DB]
set SVF_FILE [require_env SVF_FILE]
set OUT_DIR [require_env OUT_DIR]
file mkdir $OUT_DIR
set_app_var synopsys_auto_setup true
set_svf $SVF_FILE
read_sverilog -r [list $GENERATED_SV $LANE_RTL]
set_top -r bf16_context_fma_pipeline_lane4_rev8_candidate
read_db -i $STD_DB
read_sverilog -i $IMPL_NETLIST
set_top -i bf16_context_fma_pipeline_lane4_rev8_candidate
match
verify
report_verification > "$OUT_DIR/verification.rpt"
report_failing_points > "$OUT_DIR/failing_points.rpt"
exit
