// Generated from Archspec v6.
package heteronpu_arch_pkg;
  localparam longint unsigned ARCHSPEC_SHA64 = 64'h357b12c07ae1c6e9;
  localparam int unsigned TOTAL_SRAM_BYTES = 4194304;
  localparam int unsigned SRAM_SHARED_L2_BASE = 0;
  localparam int unsigned SRAM_SHARED_L2_BYTES = 1310720;
  localparam int unsigned SRAM_MATRIX_SCRATCHPAD_BASE = 1310720;
  localparam int unsigned SRAM_MATRIX_SCRATCHPAD_BYTES = 786432;
  localparam int unsigned SRAM_MATRIX_ACCUMULATOR_BASE = 2097152;
  localparam int unsigned SRAM_MATRIX_ACCUMULATOR_BYTES = 524288;
  localparam int unsigned SRAM_SEQUENCE_STATE_STAGING_BASE = 2621440;
  localparam int unsigned SRAM_SEQUENCE_STATE_STAGING_BYTES = 786432;
  localparam int unsigned SRAM_EXPERT_ROW_STAGING_BASE = 3407872;
  localparam int unsigned SRAM_EXPERT_ROW_STAGING_BYTES = 393216;
  localparam int unsigned SRAM_AHA_SIDECAR_BASE = 3801088;
  localparam int unsigned SRAM_AHA_SIDECAR_BYTES = 262144;
  localparam int unsigned SRAM_CONTROL_TRACE_BASE = 4063232;
  localparam int unsigned SRAM_CONTROL_TRACE_BYTES = 131072;
endpackage
