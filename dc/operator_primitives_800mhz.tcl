# Authoritative clock contract for newly generated operator primitives.
# Source this file after current_design/link and call:
#   hetero_apply_800mhz_constraints clk_i
set HETERO_CLOCK_PERIOD_NS 1.25
set HETERO_SETUP_UNCERTAINTY_NS 0.08
set HETERO_CLOCK_TRANSITION_NS 0.05
set HETERO_IO_DELAY_NS 0.10

proc hetero_apply_800mhz_constraints {clock_port_name} {
  global HETERO_CLOCK_PERIOD_NS
  global HETERO_SETUP_UNCERTAINTY_NS
  global HETERO_CLOCK_TRANSITION_NS
  global HETERO_IO_DELAY_NS

  set clock_port [get_ports -quiet $clock_port_name]
  if {[sizeof_collection $clock_port] == 0} {
    error "800MHz constraint: clock port '$clock_port_name' not found"
  }
  create_clock -name core_clk -period $HETERO_CLOCK_PERIOD_NS $clock_port
  set_clock_uncertainty $HETERO_SETUP_UNCERTAINTY_NS [get_clocks core_clk]
  set_clock_transition $HETERO_CLOCK_TRANSITION_NS [get_clocks core_clk]
  set non_clock_inputs [remove_from_collection [all_inputs] $clock_port]
  if {[sizeof_collection $non_clock_inputs] > 0} {
    set_input_delay $HETERO_IO_DELAY_NS -clock core_clk $non_clock_inputs
  }
  if {[sizeof_collection [all_outputs]] > 0} {
    set_output_delay $HETERO_IO_DELAY_NS -clock core_clk [all_outputs]
  }
  set_max_transition 0.25 [current_design]
  set_max_fanout 32 [current_design]
}
