`timescale 1ns/1ps
module tb_command_event_scoreboard_sram_100k;
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  logic host_valid,host_ready,run_valid,run_ready,completion_valid,completion_ready;
  logic[127:0] host_data,run_data;
  logic[55:0] completion_data;
  logic init_done;
  logic[4:0]command_level,completion_level;
  logic[31:0] macro_errors;
  integer seed,cycles,accepted,success_events,error_events;
  command_event_frontend_sram dut(.clk_i(clk),.rst_ni(rst_n),
    .host_cmd_valid_i(host_valid),.host_cmd_ready_o(host_ready),.host_cmd_data_i(host_data),
    .runnable_cmd_valid_o(run_valid),.runnable_cmd_ready_i(run_ready),.runnable_cmd_data_o(run_data),
    .completion_valid_i(completion_valid),.completion_ready_o(completion_ready),
    .completion_data_i(completion_data),.init_done_o(init_done),
    .command_level_o(command_level),.completion_level_o(completion_level),
    .macro_error_count_o(macro_errors));
  always @(posedge clk)cycles<=cycles+1;

  task automatic pulse_completion(input logic[15:0] event_id,input logic[7:0] status);
    logic fire;
    begin
      @(negedge clk);completion_data={event_id,status,3'd2,29'd1};completion_valid=1;fire=0;
      while(!fire)begin #1;fire=completion_valid&&completion_ready;@(posedge clk);if(!fire)@(negedge clk);end
      if(status==0)success_events=success_events+1;else error_events=error_events+1;
      @(negedge clk);completion_valid=0;
    end
  endtask

  task automatic run_epoch(input integer count);
    integer index;
    logic[15:0] previous_event,current_event;
    logic fire;
    begin
      wait(init_done);previous_event=0;
      for(index=1;index<=count;index++)begin
        current_event=index;
        @(negedge clk);host_data='0;host_data[39:24]=previous_event;
        host_data[55:40]=current_event;host_data[10:8]=index%6;host_valid=1;
        fire=0;
        while(!fire)begin #1;fire=host_valid&&host_ready;@(posedge clk);if(!fire)@(negedge clk);end
        accepted=accepted+1;@(negedge clk);host_valid=0;
        if(previous_event!=0)begin
          run_ready=1;#1;if(run_valid)$fatal(1,"dependency released early");
          if((index%4096)==0)begin
            pulse_completion(previous_event,8'd1);#1;
            if(run_valid)$fatal(1,"error completion released dependency");
          end
          pulse_completion(previous_event,8'd0);
        end
        fire=0;
        while(!fire)begin
          run_ready=($urandom(seed)%4)!=0;#1;
          if(run_valid&&run_data!==host_data)$fatal(1,"payload mismatch");
          fire=run_valid&&run_ready;@(posedge clk);if(!fire)@(negedge clk);
        end
        @(negedge clk);run_ready=0;previous_event=current_event;
      end
      pulse_completion(previous_event,8'd0);
    end
  endtask

  initial begin
    host_valid=0;host_data=0;run_ready=0;completion_valid=0;completion_data=0;
    seed=32'h10293847;cycles=0;accepted=0;success_events=0;error_events=0;
    repeat(4)@(posedge clk);rst_n=1;run_epoch(65535);
    @(negedge clk);rst_n=0;repeat(3)@(posedge clk);@(negedge clk);rst_n=1;run_epoch(34465);
    if(accepted!=100000||success_events!=100000||error_events==0||macro_errors!=0)$fatal(1,"accounting mismatch");
    $display("COMMAND_EVENT_SCOREBOARD_SRAM_100K_PASS commands=%0d success=%0d errors=%0d cycles=%0d",
      accepted,success_events,error_events,cycles);$finish;
  end
  initial begin repeat(3000000)@(posedge clk);$fatal(1,"timeout");end
endmodule
