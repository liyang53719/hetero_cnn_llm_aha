// SPDX-License-Identifier: Apache-2.0
// Cycle-neutral fanout for fixed four-context lane-local state controls.
`timescale 1ns/1ps
module bf16_context_control_broadcast512 (
  input  logic [1:0] issue_context_i,
  input  logic issue_clear_i,
  input  logic issue_bypass_i,
  input  logic issue_use_bank_i,
  input  logic completion_fire_i,
  input  logic [1:0] completion_context_i,
  output logic [1023:0] lane_issue_context_o,
  output logic [511:0] lane_issue_clear_o,
  output logic [511:0] lane_issue_bypass_o,
  output logic [511:0] lane_issue_use_bank_o,
  output logic [511:0] lane_completion_fire_o,
  output logic [1023:0] lane_completion_context_o
);
  assign lane_issue_context_o = {512{issue_context_i}};
  assign lane_issue_clear_o = {512{issue_clear_i}};
  assign lane_issue_bypass_o = {512{issue_bypass_i}};
  assign lane_issue_use_bank_o = {512{issue_use_bank_i}};
  assign lane_completion_fire_o = {512{completion_fire_i}};
  assign lane_completion_context_o = {512{completion_context_i}};
endmodule
