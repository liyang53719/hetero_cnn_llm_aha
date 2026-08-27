`timescale 1ns/1ps
module tb_descriptor_v3_capability_decode;
  logic [7:0] record_type;
  logic recognized, executable;
  logic [7:0] status;

  descriptor_v3_capability_decode dut(
    .record_type_i(record_type),
    .recognized_o(recognized),
    .executable_o(executable),
    .status_o(status)
  );

  task automatic check(
    input logic [7:0] t,
    input logic expected_recognized,
    input logic expected_executable,
    input logic [7:0] expected_status
  );
    begin
      record_type = t;
      #1;
      if (recognized !== expected_recognized ||
          executable !== expected_executable ||
          status !== expected_status) begin
        $fatal(1, "type=%02x recognized=%0d executable=%0d status=%0d",
          t, recognized, executable, status);
      end
    end
  endtask

  initial begin
    check(8'h04, 1, 1, 0);
    check(8'h32, 1, 1, 0);
    check(8'h33, 1, 1, 0);
    check(8'h34, 1, 1, 0);
    check(8'h35, 1, 1, 0);
    check(8'h13, 1, 0, 4);
    check(8'h14, 1, 0, 4);
    check(8'h15, 1, 0, 4);
    check(8'h16, 1, 0, 4);
    check(8'h17, 1, 0, 4);
    check(8'h18, 1, 0, 4);
    check(8'h19, 1, 0, 4);
    check(8'h7f, 0, 0, 4);
    $display("DESCRIPTOR_V3_CAPABILITY_PASS metadata=5 policy_status4=7 unknown=1");
    $finish;
  end
endmodule
