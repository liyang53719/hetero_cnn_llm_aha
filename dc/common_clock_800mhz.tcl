# Canonical active clock constraint for all new synthesis and STA runs.
# Historical 1.0 ns reports remain provenance only and must not be relabeled.
set HETERO_TARGET_CLOCK_MHZ 800
set HETERO_TARGET_CLOCK_PERIOD_NS 1.250
set HETERO_SETUP_UNCERTAINTY_NS 0.080
set HETERO_IO_BUDGET_NS 0.100

proc hetero_apply_primary_clock {{port_name clk_i} {clock_name hetero_clk}} {
  global HETERO_TARGET_CLOCK_PERIOD_NS
  global HETERO_SETUP_UNCERTAINTY_NS
  global HETERO_IO_BUDGET_NS

  set clock_port [get_ports $port_name]
  if {[sizeof_collection $clock_port] != 1} {
    error "expected exactly one primary clock port named $port_name"
  }

  create_clock -name $clock_name \
    -period $HETERO_TARGET_CLOCK_PERIOD_NS \
    -waveform [list 0.000 [expr {$HETERO_TARGET_CLOCK_PERIOD_NS / 2.0}]] \
    $clock_port
  set_clock_uncertainty -setup $HETERO_SETUP_UNCERTAINTY_NS [get_clocks $clock_name]

  set non_clock_inputs [remove_from_collection [all_inputs] $clock_port]
  if {[sizeof_collection $non_clock_inputs] > 0} {
    set_input_delay $HETERO_IO_BUDGET_NS -clock [get_clocks $clock_name] $non_clock_inputs
  }
  if {[sizeof_collection [all_outputs]] > 0} {
    set_output_delay $HETERO_IO_BUDGET_NS -clock [get_clocks $clock_name] [all_outputs]
  }
}

puts "HETERO_ACTIVE_CLOCK target=${HETERO_TARGET_CLOCK_MHZ}MHz period=${HETERO_TARGET_CLOCK_PERIOD_NS}ns"
