// SPDX-License-Identifier: Apache-2.0
// Command-owned Qwen3.5 all-Q8/all-K2 tensor -> Norm256 -> SharedL2 -> RoPE.
// Raw source BF16 inputs and weights are DMA-loaded. There are no arithmetic
// stubs, hierarchical accumulator writes, or projected/native output injection.
// All expected arithmetic is supplied by a separate source-derived oracle.
// +vectors=DIR contains case0..case39, each with activation.memh (1024 BF16),
// weight.memh (1024*512 Q / 1024*256 K BF16, K-major), norm_weight.memh
// (256 BF16), trig.memh (cos32,sin32 BF16), projected_fp32.memh,
// projected.memh, norm.memh, and rope.memh. Only transient fixtures contain data.
// +suite=main|negative|fault|reset|boundary|all; +trace=accepted_events.jsonl.
`timescale 1ns/1ps
module tb_qwen35_matrix_norm_rope_tensor;
  localparam integer L2_BEATS=24576, L2_BYTES=1572864;
  localparam logic [63:0] ACT=64'h10000, WGT=64'h20000,
    PACKED=64'h40000, NORM=64'h60000, ROPE=64'h80000,
    GAMMA=64'h2000, TRIG=64'h3000;
  localparam logic [63:0] DDR_ACT=64'h100000000,
    DDR_WGT=64'h200000000, DDR_OUT=64'h300000000,
    DDR_NORM=64'h400000000, DDR_ROPE=64'h500000000;
  logic clk=0, rst_n=0, start=0;
  always #5 clk=~clk;
  logic [127:0] command, records[0:6];
  logic [31:0] token_i;
  logic [63:0] act_i,wgt_i,packed_i,norm_i,rope_i,gamma_i,trig_i;
  logic [1:0] role_i;
  logic [15:0] head_i;
  logic [7:0] policy_i,token_count_i,total_tiles,completed_tokens;
  logic tensor_i;
  logic [15:0] completed_heads;
  logic [63:0] norm_ddr_i,rope_ddr_i;
  logic [63:0] norm_ddr_base=DDR_NORM,rope_ddr_base=DDR_ROPE;
  logic dqv,dqr,dsv,dsr,dse;
  logic [23:0] dqi;
  logic [127:0] dsd;
  logic av,ar,asv,asr,ase;
  logic [1:0] ak;
  logic [63:0] as,ad;
  logic [31:0] ab,an,ass,ads;
  logic rv,rr,rsv,rsr,rse,wv,wr,wsv,wsr,wse;
  logic [14:0] ra,wa;
  logic [511:0] rd,wd;
  logic [63:0] be;
  logic ready,done;
  logic [7:0] status;
  logic [17:0] cols;
  logic [5:0] tiles;
  logic [31:0] steps,mean_eps,inv;
  logic [63:0] dr,dw;
  logic [4:0] flags;
  logic [3:0] norm_status;

  qwen2_projection_tile16_controller #(
    .ADDR_W(15),.EXPERIMENTAL_QK_NORM_ROPE(1),
    .CANDIDATE_L2_BEATS(L2_BEATS)
  ) dut (
    .clk_i(clk),.rst_ni(rst_n),.start_i(start),.command_i(command),
    .token_base_i(token_i),.activation_local_i(act_i),
    .weight_local_i(wgt_i),.output_local_i(packed_i),
    .descriptor_req_valid_o(dqv),.descriptor_req_ready_i(dqr),
    .descriptor_req_index_o(dqi),.descriptor_rsp_valid_i(dsv),
    .descriptor_rsp_ready_o(dsr),.descriptor_rsp_data_i(dsd),
    .descriptor_rsp_error_i(dse),.dma_req_valid_o(av),.dma_req_ready_i(ar),
    .dma_req_kind_o(ak),.dma_src_addr_o(as),.dma_dst_addr_o(ad),
    .dma_row_bytes_o(ab),.dma_rows_o(an),.dma_src_stride_o(ass),
    .dma_dst_stride_o(ads),.dma_rsp_valid_i(asv),.dma_rsp_ready_o(asr),
    .dma_rsp_error_i(ase),.l2_rd_valid_o(rv),.l2_rd_ready_i(rr),
    .l2_rd_addr_o(ra),.l2_rsp_valid_i(rsv),.l2_rsp_ready_o(rsr),
    .l2_rsp_data_i(rd),.l2_wr_valid_o(wv),.l2_wr_ready_i(wr),
    .l2_wr_addr_o(wa),.l2_wr_data_o(wd),.l2_wr_be_o(be),
    .done_o(done),.status_o(status),.output_columns_o(cols),
    .column_tiles_o(tiles),.matrix_steps_o(steps),
    .ddr_read_bytes_o(dr),.ddr_write_bytes_o(dw),
    .candidate_role_i(role_i),.candidate_head_i(head_i),
    .candidate_tensor_i(tensor_i),.candidate_token_count_i(token_count_i),
    .candidate_norm_output_ddr_i(norm_ddr_i),.candidate_rope_output_ddr_i(rope_ddr_i),
    .candidate_total_column_tiles_o(total_tiles),.candidate_completed_heads_o(completed_heads),
    .candidate_completed_tokens_o(completed_tokens),
    .candidate_policy_i(policy_i),.candidate_norm_weight_local_i(gamma_i),
    .candidate_norm_output_local_i(norm_i),.candidate_rope_output_local_i(rope_i),
    .candidate_trig_local_i(trig_i),.candidate_l2_rsp_error_i(rse),
    .candidate_l2_wr_rsp_valid_i(wsv),.candidate_l2_wr_rsp_error_i(wse),
    .candidate_l2_wr_rsp_ready_o(wsr),.ready_o(ready),
    .candidate_exception_flags_o(flags),.candidate_norm_status_o(norm_status),
    .candidate_mean_eps_o(mean_eps),.candidate_inv_o(inv)
  );

  // These are observation-only probes of actual production endpoint handshakes.
`define CHAIN dut.g_qk_candidate.candidate
  wire matrix_accept=`CHAIN.mpv && `CHAIN.mpr;
  wire matrix_output=`CHAIN.mov && `CHAIN.mor;
  wire matrix_last=`CHAIN.mol;
  wire [2:0] matrix_context=`CHAIN.moctx;
  wire [16383:0] matrix_acc=`CHAIN.macc;

  byte unsigned mem[0:L2_BYTES-1];
  byte unsigned expected_memory[0:L2_BYTES-1];
  logic [15:0] activation[0:1023],weight[0:524287],gamma[0:255],trig[0:63];
  logic [15:0] expected_projected[0:511],expected_norm[0:255],expected_rope[0:255];
  logic [31:0] expected_fp32[0:511],expected_steps[0:524287];
  logic [31:0] lfsr=32'h4816ac1d;
  logic dp=0,ap=0,rp=0,wp=0;
  logic [127:0] dpdata;
  logic [23:0] dpindex;
  logic [511:0] rpdata;
  logic dperror,aperror,rperror,wperror;
  integer ddelay=0,adelay=0,rdelay=0,wdelay=0;
  integer pending_read_addr=0,pending_write_addr=0;
  integer cycle=0,transaction=0,case_id=0,selected_head=0,selected_token=0;
  integer selected_columns=512,full_columns=4096,role=0;
  integer command_id=0,start_token=0,token_count=2,head_count=8,head_ordinal=0;
  integer finished_heads=0,command_matrix_inputs=0,command_matrix_outputs=0;
  integer command_write_requests=0,command_write_acks=0,head_dma_start=0;
  integer norm_stores=0,rope_stores=0,same_cycle_ack_count=0,engine_reset_clocks=0;
  bit head_active=0,same_cycle_acks=1;
  integer packed_base,norm_base,rope_base,act_base,wgt_base,gamma_base,trig_base;
  integer descriptor_count=0,dma_count=0,dma_acks=0,activation_loads=0;
  integer weight_loads=0,stores=0,read_requests=0,read_responses=0;
  integer write_requests=0,write_acks=0,matrix_inputs=0,matrix_outputs=0;
  integer final_outputs=0,packed_writes=0,norm_writes=0,rope_writes=0;
  integer norm_reads=0,rope_reads=0,done_count=0,txn_cycles=0;
  integer trace_fd=0,success_count=0,reject_count=0,fault_count=0,reset_count=0;
  integer total_matrix_inputs=0,total_matrix_outputs=0,total_write_acks=0;
  integer read_stalls=0,write_stalls=0,dma_stalls=0,ack_delayed_cycles=0;
  integer force_read_block=0,force_write_block=0,force_dma_block=0;
  integer fault_dma=-1,fault_read_region=-1,fault_write_region=-1;
  bit fault_descriptor=0,fault_injected=0,active=0,expect_reject=0;
  bit checking=1,random_stalls=1,held_read=0,held_write=0,held_dma=0;
  logic [14:0] old_ra,old_wa;
  logic [511:0] old_wd;
  logic [63:0] old_be,old_as,old_ad;
  logic [1:0] old_ak;
  logic [31:0] old_ab,old_an,old_ass,old_ads;
  string vectors,suite,trace_path,test_name;

  logic host_mode=1,hwv=0,hrv=0,hrsr=0;
  logic [14:0] hwa=0,hra=0;
  logic [511:0] hwd=0;
  logic [1:0] frv,frr,frsv,frsr;
  logic [29:0] fra;
  logic [1023:0] frd;
  logic fwv,fwr;
  logic [14:0] fwa;
  logic [511:0] fwd;
  logic [63:0] fbe,fabric_reads,fabric_writes;
  logic request_gate,response_gate,write_gate;
  logic dma_transfer_done=0,dma_activation_q=0,dma_store_q=0,dma_read_requested=0;
  integer dma_index=0,dma_tile_q=0,dma_store_addr=0,dma_packet_index=0,dma_rows_q=0;
  logic[63:0] dma_store_destination;
  wire instant_ack=wv&&wr&&same_cycle_acks&&lfsr[5]&&fault_write_region<0;
  logic dma_write_valid,dma_read_valid;
  logic [511:0] dma_write_data;
  logic [14:0] dma_write_addr;
  bit touched[0:L2_BEATS-1];
  longint unsigned model_fabric_reads=0,model_fabric_writes=0,readback_bytes=0;
  shared_l2_fabric #(.ADDR_W(15),.ROWS_PER_BANK(6144)) fabric(
    .clk_i(clk),.rst_ni(rst_n),.rd_valid_i(frv),.rd_ready_o(frr),
    .rd_addr_i(fra),.rd_resp_valid_o(frsv),.rd_resp_ready_i(frsr),.rd_data_o(frd),
    .wr_valid_i(fwv),.wr_ready_o(fwr),.wr_addr_i(fwa),.wr_data_i(fwd),.wr_be_i(fbe),
    .cycle_count_o(),.read_count_o(fabric_reads),.write_count_o(fabric_writes),
    .bank_conflict_count_o(),.read_stall_count_o(),.write_stall_count_o());
  assign request_gate=rst_n&&!rp&&force_read_block==0&&(!random_stalls||lfsr[2]||lfsr[9]);
  assign response_gate=rst_n&&rp&&rdelay==0;
  assign write_gate=rst_n&&!wp&&force_write_block==0&&(!random_stalls||lfsr[3]||lfsr[10]);
  assign dma_write_valid=ap&&!dma_transfer_done&&!dma_store_q;
  assign dma_read_valid=ap&&!dma_transfer_done&&dma_store_q&&!dma_read_requested;
  always_comb begin
    dma_write_data='0;
    dma_write_addr=15'((dma_activation_q?act_base:wgt_base)/64+dma_index);
    if(dma_activation_q)dma_write_data[15:0]=activation[dma_index];
    else for(integer lane=0;lane<32;lane++)
      dma_write_data[lane*16+:16]=weight[dma_index*selected_columns+dma_tile_q*32+lane];
    frv='0;fra='0;frsr='0;
    frv[0]=!host_mode&&rv&&request_gate;fra[14:0]=ra;frsr[0]=!host_mode&&rsr&&response_gate;
    frv[1]=host_mode?hrv:dma_read_valid;
    fra[29:15]=host_mode?hra:15'(dma_store_addr/64+dma_index);
    frsr[1]=host_mode?hrsr:dma_read_requested;
    fwv=host_mode?hwv:(dma_write_valid?1'b1:(wv&&write_gate));
    fwa=host_mode?hwa:(dma_write_valid?dma_write_addr:wa);
    fwd=host_mode?hwd:(dma_write_valid?dma_write_data:wd);
    fbe=host_mode||dma_write_valid?'1:be;
  end
  assign dqr=rst_n&&!dp&&(!random_stalls||lfsr[0]||lfsr[7]);
  assign dsv=rst_n&&dp&&ddelay==0;
  assign dsd=dpdata;
  assign dse=dperror;
  assign ar=rst_n&&!ap&&force_dma_block==0&&(!random_stalls||lfsr[1]||lfsr[8]);
  assign asv=rst_n&&ap&&dma_transfer_done&&adelay==0;
  assign ase=aperror;
  assign rr=!host_mode&&request_gate&&frr[0];
  assign rsv=!host_mode&&response_gate&&frsv[0];
  assign rd=frd[511:0];
  assign rse=rperror;
  assign wr=!host_mode&&!dma_write_valid&&write_gate&&fwr;
  assign wsv=rst_n&&((wp&&wdelay==0)||instant_ack);
  assign wse=wperror;

  function automatic logic [127:0] root_record(input integer shape_index,input logic [63:0] base);
    logic [127:0] r;
    r='0; r[7:0]=8'h01; r[55:32]=24'(shape_index);
    r[103:56]=base[47:0];r[127:120]=base[55:48];r[111:108]=4'd5;
    return r;
  endfunction
  function automatic logic [127:0] shape_record(input integer rows,input integer columns);
    logic [127:0] r;
    r='0;r[7:0]=8'h02;r[73:56]=18'(rows);r[91:74]=18'(columns);
    return r;
  endfunction
  function automatic integer region(input integer addr);
    if(addr>=packed_base && addr<packed_base+selected_columns*2)return 0;
    if(addr>=norm_base && addr<norm_base+512)return 1;
    if(addr>=rope_base && addr<rope_base+512)return 2;
    if(addr>=gamma_base && addr<gamma_base+512)return 3;
    if(addr>=trig_base && addr<trig_base+128)return 4;
    if(addr>=act_base && addr<act_base+65536)return 5;
    if(addr>=wgt_base && addr<wgt_base+65536)return 6;
    return -1;
  endfunction
  function automatic logic [15:0] expected_word(input integer regid,input integer index);
    case(regid)
      0:return expected_projected[index];
      1:return expected_norm[index];
      2:return expected_rope[index];
      default:return 16'hxxxx;
    endcase
  endfunction

  // Single in-flight read model and explicit, delayed write acknowledgments.
  // DMA transfers load selected raw source tiles, never oracle outputs.
  always @(posedge clk) begin : transport
    integer addr,regid,index,tile,relative,expected_addr;
    logic [15:0] word_value;
    if(!rst_n) begin
      dp<=0;ap<=0;rp<=0;wp<=0;ddelay<=0;adelay<=0;rdelay<=0;wdelay<=0;
      dperror<=0;aperror<=0;rperror<=0;wperror<=0;
      held_read=0;held_write=0;held_dma=0;
      dma_transfer_done<=0;dma_index<=0;dma_read_requested<=0;
      model_fabric_reads=0;model_fabric_writes=0;
    end else begin
      if(fabric_reads!==model_fabric_reads||fabric_writes!==model_fabric_writes)
        $fatal(1,"actual fabric handshake counters differ");
      model_fabric_reads=model_fabric_reads+(frv[0]&&frr[0])+(frv[1]&&frr[1]);
      model_fabric_writes=model_fabric_writes+(fwv&&fwr);
      if(!host_mode&&dma_write_valid&&fwr)begin
        touched[dma_write_addr]=1;
        if(dma_index==1023)dma_transfer_done<=1;
        else dma_index<=dma_index+1;
      end
      if(!host_mode&&dma_read_valid&&frr[1])dma_read_requested<=1;
      if(!host_mode&&frsv[1]&&frsr[1])begin
        $fdisplay(trace_fd,"{\"event\":\"dma_data\",\"transaction\":%0d,\"cycle\":%0d,\"index\":%0d,\"source\":\"%016h\",\"destination\":\"%016h\",\"data\":\"%0128h\"}",transaction,cycle+1,dma_packet_index,64'(dma_store_addr+dma_index*64),dma_store_destination+64'(dma_index*64),frd[1023:512]);
        for(integer b=0;b<64;b++)if(frd[512+b*8+:8]!==expected_memory[dma_store_addr+dma_index*64+b])
          $fatal(1,"DDR store actual fabric read mismatch byte=%h",dma_store_addr+dma_index*64+b);
        if(dma_index+1==dma_rows_q)dma_transfer_done<=1;
        else dma_index<=dma_index+1;
        dma_read_requested<=0;
      end
      cycle=cycle+1;lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
      if(force_read_block>0)force_read_block<=force_read_block-1;
      if(force_write_block>0)force_write_block<=force_write_block-1;
      if(force_dma_block>0)force_dma_block<=force_dma_block-1;
      if(active) begin
        txn_cycles=txn_cycles+1;
        if(head_active&&!`CHAIN.engine_rst_n)engine_reset_clocks=engine_reset_clocks+1;
        if(ap&&dma_store_q&&dma_store_addr==rope_base&&completed_heads!=finished_heads)
          $fatal(1,"head advanced before final RoPE store ACK");
        if(txn_cycles>12000000)$fatal(1,"transaction timeout %s state=%0d",test_name,dut.st);
        if(held_read&&(!rv||ra!==old_ra))$fatal(1,"read changed under stall %s",test_name);
        if(held_write&&(!wv||wa!==old_wa||wd!==old_wd||be!==old_be))$fatal(1,"write changed under stall %s",test_name);
        if(held_dma&&(!av||as!==old_as||ad!==old_ad||ak!==old_ak||ab!==old_ab||an!==old_an||ass!==old_ass||ads!==old_ads))$fatal(1,"DMA changed under stall %s",test_name);
        held_read=rv&&!rr;held_write=wv&&!wr;held_dma=av&&!ar;
        if(held_read)begin old_ra=ra;read_stalls=read_stalls+1;end
        if(held_write)begin old_wa=wa;old_wd=wd;old_be=be;write_stalls=write_stalls+1;end
        if(held_dma)begin old_as=as;old_ad=ad;old_ak=ak;old_ab=ab;old_an=an;old_ass=ass;old_ads=ads;dma_stalls=dma_stalls+1;end
      end else if(rv||wv||av||dqv||done||matrix_accept||matrix_output)
        $fatal(1,"unexpected bus/arithmetic activity outside transaction state=%0d",dut.st);

      if(dsv&&dsr)begin
        $fdisplay(trace_fd,"{\"event\":\"descriptor\",\"transaction\":%0d,\"cycle\":%0d,\"index\":%0d,\"data\":\"%032h\",\"error\":%0d}",transaction,cycle,dpindex,dpdata,dperror);
        dp<=0;dperror<=0;dpdata<=~dpdata;
      end
      else if(dp&&ddelay>0)ddelay<=ddelay-1;
      if(dqv&&dqr)begin
        $fdisplay(trace_fd,"{\"event\":\"descriptor_request\",\"transaction\":%0d,\"cycle\":%0d,\"index\":%0d}",transaction,cycle,dqi);
        if(expect_reject&&dqi>6)$fatal(1,"bad descriptor index escaped snapshot");
        if(dqi<1||dqi>6)$fatal(1,"descriptor index=%0d",dqi);
        dp<=1;dpindex<=dqi;dpdata<=records[dqi];ddelay<=random_stalls?integer'(lfsr[13:11])+1:1;
        dperror<=fault_descriptor&&!fault_injected;
        if(fault_descriptor&&!fault_injected)fault_injected=1;
        descriptor_count=descriptor_count+1;
      end
      if(asv&&asr)begin
        $fdisplay(trace_fd,"{\"event\":\"dma_ack\",\"transaction\":%0d,\"cycle\":%0d,\"index\":%0d,\"error\":%0d}",transaction,cycle,dma_acks,aperror);
        ap<=0;aperror<=0;dma_acks=dma_acks+1;
      end else if(ap&&adelay>0)adelay<=adelay-1;
      if(av&&ar)begin
        if(expect_reject)$fatal(1,"rejected descriptor issued DMA");
        if(ap)$fatal(1,"more than one pending DMA");
        dma_transfer_done<=0;dma_index<=0;dma_read_requested<=0;
        dma_activation_q<=ab==2;dma_store_q<=ak==3;
        dma_packet_index<=dma_count;dma_store_destination<=ad;dma_rows_q<=an;
        if(ab==2)begin
          if(head_active)begin
            if(engine_reset_clocks<2)$fatal(1,"Matrix endpoint not reset for two clocks between heads");
            finish_head();
          end
          engine_reset_clocks=0;
          load_head(head_ordinal);
          head_dma_start=dma_count;head_active=1;
          $fdisplay(trace_fd,"{\"event\":\"head_begin\",\"transaction\":%0d,\"cycle\":%0d,\"case\":%0d,\"head\":%0d,\"token\":%0d}",transaction,cycle,case_id,selected_head,selected_token);
        end
        dma_tile_q<=weight_loads;dma_store_addr<=integer'(as);
        aperror<=dma_count==fault_dma;
        if(dma_count==fault_dma)fault_injected=1;
        $fdisplay(trace_fd,"{\"event\":\"dma\",\"transaction\":%0d,\"cycle\":%0d,\"index\":%0d,\"kind\":%0d,\"source\":\"%016h\",\"destination\":\"%016h\",\"row_bytes\":%0d,\"rows\":%0d,\"source_stride\":%0d,\"destination_stride\":%0d}",transaction,cycle,dma_count,ak,as,ad,ab,an,ass,ads);
        if(ab==2)begin
          if(as!==DDR_ACT+64'(selected_token)*2048||ad!==64'(act_base)||ab!=2||an!=1024||ass!=2||ads!=64)$fatal(1,"activation DMA geometry");
          for(integer k=0;k<1024;k++)begin
            for(integer b=0;b<64;b++)begin mem[act_base+k*64+b]=0;expected_memory[act_base+k*64+b]=0;end
            mem[act_base+k*64]=activation[k][7:0];mem[act_base+k*64+1]=activation[k][15:8];
            expected_memory[act_base+k*64]=activation[k][7:0];expected_memory[act_base+k*64+1]=activation[k][15:8];
          end
          activation_loads=activation_loads+1;
        end else if(ak==1)begin
          tile=weight_loads;
          if(as!==DDR_WGT+64'(selected_head)*selected_columns*2+64'(tile)*64||ad!==64'(wgt_base)||ab!=64||an!=1024||ass!=full_columns*2||ads!=64)$fatal(1,"weight DMA geometry tile=%0d src=%h",tile,as);
          for(integer k=0;k<1024;k++)for(integer lane=0;lane<32;lane++)begin
            word_value=weight[k*selected_columns+tile*32+lane];
            addr=wgt_base+k*64+lane*2;
            mem[addr]=word_value[7:0];mem[addr+1]=word_value[15:8];
            expected_memory[addr]=word_value[7:0];expected_memory[addr+1]=word_value[15:8];
          end
          weight_loads=weight_loads+1;
        end else if(ak==3)begin
          regid=region(integer'(as));
          tile=regid==0?stores:(regid==1?norm_stores:rope_stores);
          expected_addr=(regid==0?packed_base:(regid==1?norm_base:rope_base))+tile*64;
          if(regid<0||regid>2||as!==64'(expected_addr)||ab!=64||an!=(regid==0?1:8)||ass!=64||ads!=64)
            $fatal(1,"store DMA source geometry region=%0d tile=%0d src=%h",regid,tile,as);
          if(ad!==(regid==0?DDR_OUT:(regid==1?norm_ddr_base:rope_ddr_base))+
              64'(selected_token)*(regid==0?full_columns*2:(role==0?4096:1024))+
              64'(selected_head)*(regid==0?selected_columns*2:512)+64'(tile)*64)
            $fatal(1,"store DMA destination geometry region=%0d tile=%0d dst=%h",regid,tile,ad);
          if(wp||write_acks<(regid==0?tile+1:(regid==1?selected_columns/32+8:selected_columns/32+16)))
            $fatal(1,"DDR store before producer write ACK");
          for(integer lane=0;lane<(regid==0?32:256);lane++)if({mem[expected_addr+lane*2+1],mem[expected_addr+lane*2]}!==expected_word(regid,tile*32+lane))
            $fatal(1,"DDR raw actual output mismatch region=%0d tile=%0d lane=%0d",regid,tile,lane);
          if(regid==0)stores=stores+1;
          if(regid==1)norm_stores=norm_stores+8;
          if(regid==2)rope_stores=rope_stores+8;
        end else $fatal(1,"unexpected DMA kind=%0d",ak);
        ap<=1;adelay<=(ak==3&&regid==2)?512:(random_stalls?integer'(lfsr[18:15])+3:3);dma_count=dma_count+1;
      end
      if(rsv&&rsr)begin
        $fdisplay(trace_fd,"{\"event\":\"l2_response\",\"transaction\":%0d,\"cycle\":%0d,\"byte_address\":%0d,\"error\":%0d,\"data\":\"%0128h\"}",transaction,cycle,pending_read_addr,rperror,rd);
        for(integer b=0;b<64;b++)if(rd[b*8+:8]!==expected_memory[pending_read_addr+b])
          $fatal(1,"actual fabric read differs from accepted writes byte=%h",pending_read_addr+b);
        rp<=0;rperror<=0;read_responses=read_responses+1;
      end else if(rp&&rdelay>0)rdelay<=rdelay-1;
      if(rv&&rr)begin
        if(expect_reject||rp)$fatal(1,"unexpected/duplicate read");
        addr=integer'(ra)*64;
        if(addr<0||addr+64>L2_BYTES)$fatal(1,"L2 read exceeds implemented1.5MiB");
        if(wp)$fatal(1,"consumer read before prior write ACK");
        regid=region(addr);
        if(regid<0)$fatal(1,"L2 read outside selected tensor regions addr=%h",addr);
        if(regid==0)begin
          if(stores!=selected_columns/32)$fatal(1,"Norm read before all projection stores completed");
          norm_reads=norm_reads+1;
        end
        if(regid==1||regid==4)begin
          if(norm_writes!=8||write_acks<selected_columns/32+8)$fatal(1,"RoPE read before acknowledged Norm producer");
          rope_reads=rope_reads+1;
        end
        rperror<=!fault_injected&&fault_read_region==regid;
        if(!fault_injected&&fault_read_region==regid)fault_injected=1;
        rp<=1;pending_read_addr=addr;rdelay<=random_stalls?integer'(lfsr[22:20])+1:1;
        read_requests=read_requests+1;
        $fdisplay(trace_fd,"{\"event\":\"l2_read\",\"transaction\":%0d,\"cycle\":%0d,\"byte_address\":%0d,\"region\":%0d}",transaction,cycle,addr,regid);
      end
      if(wp&&wsv&&wsr)begin
        $fdisplay(trace_fd,"{\"event\":\"l2_ack\",\"transaction\":%0d,\"cycle\":%0d,\"byte_address\":%0d,\"error\":%0d}",transaction,cycle,pending_write_addr,wperror);
        wp<=0;wperror<=0;write_acks=write_acks+1;total_write_acks=total_write_acks+1;
      end else if(wp&&wdelay>0)begin wdelay<=wdelay-1;ack_delayed_cycles=ack_delayed_cycles+1;end
      if(wv&&wr)begin
        if(expect_reject||wp)$fatal(1,"unexpected/duplicate write");
        addr=integer'(wa)*64;
        if(addr<0||addr+64>L2_BYTES)$fatal(1,"L2 write exceeds implemented1.5MiB");
        touched[wa]=1;regid=region(addr);
        if(regid<0||regid>2)$fatal(1,"write outside packed/norm/rope ranges addr=%h",addr);
        if(be!==64'hffffffffffffffff)$fatal(1,"unexpected nonfull BF16 write mask");
        relative=regid==0?addr-packed_base:(regid==1?addr-norm_base:addr-rope_base);
        if(relative!=(regid==0?packed_writes:(regid==1?norm_writes:rope_writes))*64)$fatal(1,"write order/duplicate addr=%h region=%0d",addr,regid);
        if(regid==0 && final_outputs!=packed_writes+1)$fatal(1,"projection write without accepted final Matrix output");
        if(regid==1 && norm_reads!=selected_columns/32)$fatal(1,"Norm write before complete packed input");
        if(regid==2 && rope_reads!=10)$fatal(1,"RoPE write before all acknowledged Norm/trig reads");
        for(integer lane=0;lane<32;lane++)begin
          index=relative/2+lane;word_value=expected_word(regid,index);
          if(checking&&wd[lane*16+:16]!==word_value)$fatal(1,"independent arithmetic mismatch case=%0d region=%0d lane=%0d got=%h expected=%h",case_id,regid,index,wd[lane*16+:16],word_value);
        end
        wperror<=!fault_injected&&fault_write_region==regid;
        if(!fault_injected&&fault_write_region==regid)fault_injected=1;
        for(integer b=0;b<64;b++)if(be[b])begin mem[addr+b]=wd[b*8+:8];expected_memory[addr+b]=wd[b*8+:8];end
        if(regid==0)packed_writes=packed_writes+1;
        if(regid==1)norm_writes=norm_writes+1;
        if(regid==2)rope_writes=rope_writes+1;
        wp<=!instant_ack;pending_write_addr=addr;wdelay<=11+integer'(lfsr[26:23]);write_requests=write_requests+1;
        $fdisplay(trace_fd,"{\"event\":\"l2_write\",\"transaction\":%0d,\"cycle\":%0d,\"byte_address\":%0d,\"region\":%0d,\"mask\":\"%016h\",\"data\":\"%0128h\"}",transaction,cycle,addr,regid,be,wd);
        if(instant_ack)begin
          if(!wsr)$fatal(1,"same-cycle ACK not accepted");
          write_acks=write_acks+1;total_write_acks=total_write_acks+1;same_cycle_ack_count=same_cycle_ack_count+1;
          $fdisplay(trace_fd,"{\"event\":\"l2_ack\",\"transaction\":%0d,\"cycle\":%0d,\"byte_address\":%0d,\"error\":0}",transaction,cycle,addr);
        end
      end
      if(matrix_accept)begin
        if(expect_reject)$fatal(1,"rejected descriptor issued Matrix step");
        matrix_inputs=matrix_inputs+1;total_matrix_inputs=total_matrix_inputs+1;
      end
      if(matrix_output)begin
        for(integer lane=0;lane<32;lane++)if(checking&&matrix_acc[lane*32+:32]!==expected_steps[matrix_outputs*32+lane])
          $fatal(1,"independent per-step Matrix mismatch case=%0d step=%0d lane=%0d got=%h expected=%h",case_id,matrix_outputs,lane,matrix_acc[lane*32+:32],expected_steps[matrix_outputs*32+lane]);
        if(matrix_outputs>=matrix_inputs||matrix_context!=0)$fatal(1,"unexpected Matrix output identity");
        if(matrix_last!==((matrix_outputs%1024)==1023))$fatal(1,"Matrix last misaligned output=%0d",matrix_outputs);
        for(integer lane=32;lane<512;lane++)if(matrix_acc[lane*32+:32]!==32'd0)$fatal(1,"inactive Matrix row nonzero lane=%0d",lane);
        if(matrix_last)begin
          for(integer lane=0;lane<32;lane++)if(checking&&matrix_acc[lane*32+:32]!==expected_fp32[final_outputs*32+lane])$fatal(1,"independent projected FP32 mismatch case=%0d tile=%0d lane=%0d got=%h expected=%h",case_id,final_outputs,lane,matrix_acc[lane*32+:32],expected_fp32[final_outputs*32+lane]);
          final_outputs=final_outputs+1;
        end
        $fdisplay(trace_fd,"{\"event\":\"matrix\",\"transaction\":%0d,\"case\":%0d,\"cycle\":%0d,\"index\":%0d,\"last\":%0d,\"context\":%0d,\"fp32_row0\":\"%0256h\"}",transaction,case_id,cycle,matrix_outputs,matrix_last,matrix_context,matrix_acc[1023:0]);
        matrix_outputs=matrix_outputs+1;total_matrix_outputs=total_matrix_outputs+1;
      end
      if(done)begin
        if(status==0)finish_head();
        $fdisplay(trace_fd,"{\"event\":\"done\",\"transaction\":%0d,\"cycle\":%0d,\"status\":%0d}",transaction,cycle,status);
        if(wp||rp||ap||dp||write_requests!=write_acks||read_requests!=read_responses||dma_count!=dma_acks)$fatal(1,"completion before outstanding response/ACK");
        done_count=done_count+1;
        if(done_count!=1)$fatal(1,"duplicate terminal completion");
      end
    end
  end

  always @(posedge clk) if(rst_n&&active)begin : norm_boundary_scoreboard
    if(`CHAIN.niv&&`CHAIN.nir)begin
      if(wp||stores!=selected_columns/32||packed_writes!=selected_columns/32)$fatal(1,"Norm start precedes packed projection ACKs");
      for(integer lane=0;lane<selected_columns;lane++)if(`CHAIN.packed_head_q[lane*16+:16]!==expected_projected[lane])$fatal(1,"Norm consumes wrong packed value lane=%0d",lane);
      for(integer lane=0;lane<256;lane++)if(`CHAIN.gamma_head_q[lane*16+:16]!==gamma[lane])$fatal(1,"Norm consumes wrong gamma lane=%0d",lane);
    end
    if(`CHAIN.nov&&`CHAIN.norm_out_ready)begin
      if(`CHAIN.nstatus!=0)$fatal(1,"unexpected Norm arithmetic status=%0d",`CHAIN.nstatus);
      for(integer lane=0;lane<256;lane++)begin
        if(`CHAIN.norm_result[lane*16+:16]!==expected_norm[lane])$fatal(1,"independent Norm mismatch lane=%0d",lane);
        if(`CHAIN.gate_result[lane*16+:16]!==(role==0?expected_projected[256+lane]:16'd0))$fatal(1,"raw gate not preserved by Norm lane=%0d",lane);
      end
      $fdisplay(trace_fd,"{\"event\":\"norm\",\"transaction\":%0d,\"cycle\":%0d,\"status\":%0d,\"mean_eps\":\"%08h\",\"inv\":\"%08h\",\"flags\":%0d,\"norm\":\"%01024h\",\"gate\":\"%01024h\"}",transaction,cycle,`CHAIN.nstatus,`CHAIN.nmean,`CHAIN.ninv,`CHAIN.nflags,`CHAIN.norm_result,`CHAIN.gate_result);
    end
  end

  function automatic logic[511:0] pack_gamma(input integer beat);
    logic[511:0] value;
    for(integer lane=0;lane<32;lane++)value[lane*16+:16]=gamma[beat*32+lane];
    return value;
  endfunction
  function automatic logic[511:0] pack_trig(input integer beat);
    logic[511:0] value;
    for(integer lane=0;lane<32;lane++)value[lane*16+:16]=trig[beat*32+lane];
    return value;
  endfunction
  task automatic host_write(input integer address,input logic[511:0] value);
    if(!host_mode||!ready||active)$fatal(1,"host initialization requires idle owner");
    @(negedge clk);hwa=15'(address);hwd=value;hwv=1;
    do @(posedge clk);while(!fwr);
    @(negedge clk);hwv=0;
    for(integer b=0;b<64;b++)begin
      mem[address*64+b]=value[b*8+:8];expected_memory[address*64+b]=value[b*8+:8];
    end
    touched[address]=1;
  endtask
  task automatic host_read(input integer address,output logic[511:0] value);
    if(!host_mode||!ready||active)$fatal(1,"host readback requires idle owner");
    @(negedge clk);hra=15'(address);hrv=1;hrsr=0;
    do @(posedge clk);while(!frr[1]);
    @(negedge clk);hrv=0;hrsr=1;
    do @(posedge clk);while(!frsv[1]);
    value=frd[1023:512];
    @(negedge clk);hrsr=0;
  endtask
  task automatic poison_range(input integer first,input integer last);
    logic[511:0] value;
    for(integer beat=first;beat<=last;beat++)if(beat>=0&&beat<L2_BEATS)begin
      for(integer b=0;b<64;b++)value[b*8+:8]=8'ha5^8'(beat*17+b*13);
      host_write(beat,value);
    end
  endtask
  task automatic readback;
    logic[511:0] value;
    for(integer beat=0;beat<L2_BEATS;beat++)if(touched[beat])begin
      host_read(beat,value);
      for(integer b=0;b<64;b++)if(value[b*8+:8]!==expected_memory[beat*64+b])
        $fatal(1,"actual SharedL2 readback/guard mismatch byte=%h",beat*64+b);
      readback_bytes=readback_bytes+64;
    end
  endtask

  task automatic load_head(input integer ordinal);
    string dir;
    selected_head=ordinal%head_count;selected_token=start_token+ordinal/head_count;
    case_id=(start_token==126?20:0)+(selected_token-start_token)*10+(role==0?0:8)+selected_head;
    trig_base=integer'(TRIG)+selected_token*128;
    dir=$sformatf("%s/case%0d",vectors,case_id);
    $readmemh({dir,"/activation.memh"},activation);
    $readmemh({dir,"/weight.memh"},weight,0,1024*selected_columns-1);
    $readmemh({dir,"/norm_weight.memh"},gamma);
    $readmemh({dir,"/trig.memh"},trig);
    $readmemh({dir,"/projected_fp32.memh"},expected_fp32,0,selected_columns-1);
    $readmemh({dir,"/projected_steps.memh"},expected_steps,0,1024*selected_columns-1);
    $readmemh({dir,"/projected.memh"},expected_projected,0,selected_columns-1);
    $readmemh({dir,"/norm.memh"},expected_norm);
    $readmemh({dir,"/rope.memh"},expected_rope);
    weight_loads=0;stores=0;norm_stores=0;rope_stores=0;
    read_requests=0;read_responses=0;write_requests=0;write_acks=0;
    matrix_inputs=0;matrix_outputs=0;final_outputs=0;
    packed_writes=0;norm_writes=0;rope_writes=0;norm_reads=0;rope_reads=0;
  endtask

  task automatic finish_head;
    if(!head_active||wp||rp||ap||write_requests!=write_acks||read_requests!=read_responses||dma_count!=dma_acks)
      $fatal(1,"head advance before pending actual responses/ACKs completed");
    if(weight_loads!=selected_columns/32||stores!=selected_columns/32||norm_stores!=8||rope_stores!=8)
      $fatal(1,"missing full head DDR outputs");
    if(matrix_inputs!=selected_columns/32*1024||matrix_outputs!=matrix_inputs||final_outputs!=selected_columns/32)
      $fatal(1,"head Matrix accepted step coverage");
    if(packed_writes!=selected_columns/32||norm_writes!=8||rope_writes!=8||write_acks!=selected_columns/32+16)
      $fatal(1,"head producer coverage");
    if(norm_reads!=selected_columns/32||rope_reads!=10||read_requests!=selected_columns/32*2048+selected_columns/32+18)
      $fatal(1,"head consumer coverage");
    if(dma_count-head_dma_start!=1+2*(selected_columns/32)+2)$fatal(1,"head DMA count");
    command_matrix_inputs=command_matrix_inputs+matrix_inputs;command_matrix_outputs=command_matrix_outputs+matrix_outputs;
    command_write_requests=command_write_requests+write_requests;command_write_acks=command_write_acks+write_acks;
    $fdisplay(trace_fd,"{\"event\":\"head_done\",\"transaction\":%0d,\"cycle\":%0d,\"case\":%0d,\"head\":%0d,\"token\":%0d,\"flags\":%0d}",transaction,cycle,case_id,selected_head,selected_token,flags);
    finished_heads=finished_heads+1;head_ordinal=head_ordinal+1;head_active=0;
  endtask

  task automatic setup_case(input integer which,input integer count=2);
    @(negedge clk);
    if(!ready)$fatal(1,"setup while controller unavailable");
    command_id=which;role=which%2;start_token=which>=2?126:0;
    token_count=count;head_count=role==0?8:2;
    selected_columns=role==0?512:256;full_columns=role==0?4096:512;
    head_ordinal=0;finished_heads=0;head_active=0;engine_reset_clocks=0;
    command_matrix_inputs=0;command_matrix_outputs=0;command_write_requests=0;command_write_acks=0;
    for(integer b=0;b<L2_BEATS;b++)touched[b]=0;
    act_i=ACT;wgt_i=WGT;packed_i=PACKED;norm_i=NORM;rope_i=ROPE;gamma_i=GAMMA;trig_i=TRIG;
    norm_ddr_i=DDR_NORM;rope_ddr_i=DDR_ROPE;norm_ddr_base=DDR_NORM;rope_ddr_base=DDR_ROPE;tensor_i=1;token_count_i=8'(count);
    act_base=integer'(ACT);wgt_base=integer'(WGT);gamma_base=integer'(GAMMA);
    packed_base=integer'(PACKED);norm_base=integer'(NORM);rope_base=integer'(ROPE);
    command='0;command[7:0]=8'h20;command[10:8]=3'd2;
    command[55:40]=16'h35c1;command[79:56]=24'd1;command[103:80]=24'd3;command[127:104]=24'd5;
    records[1]=root_record(2,DDR_ACT);records[2]=shape_record(128,1024);
    records[3]=root_record(4,DDR_WGT);records[4]=shape_record(1024,full_columns);
    records[5]=root_record(6,DDR_OUT);records[6]=shape_record(128,full_columns);
    host_mode=1;
    poison_range(packed_base/64-1,packed_base/64+selected_columns/32);
    poison_range(norm_base/64-1,norm_base/64+8);
    poison_range(rope_base/64-1,rope_base/64+8);
    for(integer t=0;t<count;t++)begin
      load_head(t*head_count);
      for(integer beat=0;beat<2;beat++)host_write(trig_base/64+beat,pack_trig(beat));
    end
    load_head(0);
    for(integer beat=0;beat<8;beat++)host_write(gamma_base/64+beat,pack_gamma(beat));
    role_i=2'(role);head_i=0;token_i=32'(start_token);policy_i=8'hc1;
    descriptor_count=0;dma_count=0;dma_acks=0;activation_loads=0;done_count=0;txn_cycles=0;
    held_read=0;held_write=0;held_dma=0;expect_reject=0;checking=1;
    fault_dma=-1;fault_read_region=-1;fault_write_region=-1;fault_descriptor=0;fault_injected=0;
    force_read_block=0;force_write_block=0;force_dma_block=0;
  endtask

  task automatic launch(input string name,input bit mutate);
    string kind;
    if(expect_reject)kind="reject";
    else if(fault_dma>=0||fault_read_region>=0||fault_write_region>=0||fault_descriptor)kind="fault";
    else if(name.substr(0,4)=="reset")kind="reset";
    else if(name=="legal_exact_1p5MiB_end")kind="boundary";
    else if(name=="recovery_after_fault_or_reset")kind="recovery";
    else kind="main";
    test_name=name;transaction=transaction+1;active=1;host_mode=0;
    $fdisplay(trace_fd,"{\"event\":\"begin\",\"transaction\":%0d,\"case\":%0d,\"name\":\"%s\",\"kind\":\"%s\",\"checking\":1,\"role\":%0d,\"start_token\":%0d,\"token_count\":%0d,\"packed_base\":%0d,\"norm_base\":%0d,\"rope_base\":%0d,\"gamma_base\":%0d,\"trig_base\":%0d,\"act_base\":%0d,\"wgt_base\":%0d}",transaction,case_id,name,kind,role,start_token,token_count,packed_base,norm_base,rope_base,gamma_base,trig_base,act_base,wgt_base);
    @(negedge clk);start=1;
    @(negedge clk);start=0;
    if(mutate)begin
      // Only the accepted command and sideband values may govern the work.
      command=128'hffffffffffffffffffffffffffffffff;token_i=32'hffffffff;
      role_i=2'd3;head_i=16'hffff;policy_i=0;
      tensor_i=0;token_count_i=0;norm_ddr_i=0;rope_ddr_i=0;
      act_i=64'hfffffffffffffff0;wgt_i=0;packed_i=0;norm_i=0;rope_i=0;gamma_i=0;trig_i=0;
    end
  endtask

  task automatic wait_terminal(input integer expected_status);
    wait(done);
    @(negedge clk);
    if(status!==8'(expected_status))$fatal(1,"terminal status %s got=%0d expected=%0d",test_name,status,expected_status);
    // Sample the completion edge, then verify sticky status after error pins clear.
    @(negedge clk);
    if(done_count!=1)$fatal(1,"missing completion event %s",test_name);
    wait(ready);
    @(negedge clk);active=0;
    repeat(3)begin @(negedge clk);if(status!==8'(expected_status))$fatal(1,"terminal status not latched %s",test_name);end
    $fdisplay(trace_fd,"{\"event\":\"terminal\",\"transaction\":%0d,\"status\":%0d,\"matrix_inputs\":%0d,\"matrix_outputs\":%0d,\"dma_count\":%0d,\"write_requests\":%0d,\"write_acks\":%0d,\"completed_heads\":%0d,\"completed_tokens\":%0d,\"total_tiles\":%0d,\"flags\":%0d}",transaction,status,command_matrix_inputs+(head_active?matrix_inputs:0),command_matrix_outputs+(head_active?matrix_outputs:0),dma_count,command_write_requests+(head_active?write_requests:0),command_write_acks+(head_active?write_acks:0),completed_heads,completed_tokens,total_tiles,flags);
    host_mode=1;readback();
  endtask

  task automatic check_success;
    if(descriptor_count!=6||dma_count!=head_count*token_count*(1+selected_columns/16+2)||activation_loads!=head_count*token_count)
      $fatal(1,"successful tensor DMA/descriptor count mismatch");
    if(command_matrix_inputs!=head_count*token_count*selected_columns/32*1024||command_matrix_outputs!=command_matrix_inputs||steps!=command_matrix_inputs)
      $fatal(1,"successful tensor actual Matrix counts mismatch");
    if(cols!=full_columns||tiles!=selected_columns/32||total_tiles!=head_count*selected_columns/32)
      $fatal(1,"reported shape/tile counts mismatch");
    if(completed_heads!=head_count*token_count||completed_tokens!=token_count||finished_heads!=head_count*token_count)
      $fatal(1,"reported tensor completion count mismatch");
    if(dr!=64'(head_count*token_count)*(2048+64'(selected_columns/32)*65536)||dw!=64'(head_count*token_count)*(selected_columns*2+1024))
      $fatal(1,"reported DDR byte counts mismatch read=%0d write=%0d",dr,dw);
    if(norm_status!=0||flags[4:1]!=0)$fatal(1,"candidate arithmetic flags/status=%h/%h",flags,norm_status);
    success_count=success_count+1;
    $display("QWEN35_MATRIX_NORM_ROPE_TENSOR_CASE_PASS command=%0d test=%s heads=%0d tokens=%0d matrix_steps=%0d dma_requests=%0d cycles=%0d",command_id,test_name,finished_heads,completed_tokens,command_matrix_inputs,dma_count,txn_cycles);
  endtask

  task automatic good_case(input integer which,input bit boundary,input bit recovery=0);
    setup_case(which,boundary||recovery?1:2);
    if(boundary)begin
      packed_i=L2_BYTES-512;packed_base=L2_BYTES-512;
      norm_i=L2_BYTES-1536;norm_base=L2_BYTES-1536;
      rope_i=L2_BYTES-1024;rope_base=L2_BYTES-1024;
      poison_range((L2_BYTES-1536)/64-1,L2_BEATS-1);
      norm_ddr_i=64'h00fffffffffff800;norm_ddr_base=norm_ddr_i;
      rope_ddr_i=64'h00fffffffffffc00;rope_ddr_base=rope_ddr_i;
    end
    force_dma_block=23;force_read_block=41;force_write_block=67;
    launch(boundary?"legal_exact_1p5MiB_end":(recovery?"recovery_after_fault_or_reset":(which==0?"cold_Q":(which==1?"cold_K":(which==2?"carried_Q":"carried_K")))),1);
    wait_terminal(0);check_success();
  endtask

  task automatic rejected_case(input integer which);
    setup_case(1,1);expect_reject=1;
    case(which)
      0:begin command[7:0]=8'h99;test_name="bad_command";end
      1:begin records[4]=shape_record(1000,512);test_name="bad_depth_shape";end
      2:begin role_i=2;test_name="unsupported_role";end
      3:begin head_i=1;test_name="tensor_nonzero_head";end
      4:begin token_i=128;test_name="token_out_of_bounds";end
      5:begin policy_i=8'hc0;test_name="unsupported_policy";end
      6:begin act_i=L2_BYTES-64;test_name="activation_1p5MiB_bounds";end
      7:begin wgt_i=64'hffffffffffff0000;test_name="weight_high_wrap";end
      8:begin packed_i=L2_BYTES-64;test_name="packed_1p5MiB_bounds";end
      9:begin norm_i=64'hfffffffffffffe00;test_name="norm_high_wrap";end
      10:begin rope_i=L2_BYTES;test_name="rope_1p5MiB_bounds";end
      11:begin trig_i=L2_BYTES-64;test_name="trig_1p5MiB_bounds";end
      12:begin gamma_i=L2_BYTES-64;test_name="gamma_1p5MiB_bounds";end
      13:begin packed_i=PACKED+2;test_name="packed_alignment";end
      14:begin norm_i=PACKED;test_name="active_region_overlap";end
      15:begin records[3]=root_record(4,64'h00ffffffffffffc0);test_name="DDR_extent_overflow";end
      16:begin records[1][31:8]=1;test_name="malformed_descriptor";end
      17:begin records[5][111:108]=7;test_name="unsupported_FP32_output";end
      18:begin token_i=127;token_count_i=2;test_name="token_end_overflow";end
      19:begin records[2]=shape_record(129,1024);records[6]=shape_record(129,512);test_name="token_extent_over128";end
      20:begin records[5]=root_record(6,DDR_WGT+64);test_name="DDR_output_weight_alias";end
      21:begin token_count_i=0;test_name="zero_token_count";end
      22:begin token_count_i=129;test_name="token_count_over128";end
      23:begin norm_ddr_i=DDR_OUT;test_name="DDR_norm_alias";end
      24:begin rope_ddr_i=DDR_NORM;test_name="DDR_rope_alias";end
      25:begin norm_ddr_i=64'hfffffffffffffe00;test_name="DDR_norm_wrap";end
      26:begin rope_ddr_i=64'h00fffffffffffe00;test_name="DDR_rope_wrap";end
      27:begin norm_ddr_i=DDR_NORM+2;test_name="DDR_norm_alignment";end
      28:begin norm_ddr_i=DDR_OUT+512;test_name="DDR_norm_future_head_alias";end
      29:begin rope_ddr_i=DDR_OUT+1024;token_count_i=2;test_name="DDR_rope_future_token_alias";end

    endcase
    launch(test_name,0);
    wait_terminal(which==0||which==16?2:((which>=6&&which<=15)||which==20||which>=23?5:4));
    if(dma_count||read_requests||write_requests||matrix_inputs)$fatal(1,"rejection had side effects");
    reject_count=reject_count+1;
    $display("QWEN35_MATRIX_NORM_ROPE_REJECT_PASS case=%s status=%0d no_dma=1 no_l2=1 no_matrix=1",test_name,status);
  endtask

  task automatic failed_case(input integer which);
    setup_case(1,1);
    if(which==0)begin fault_dma=2*(1+16+2)-1;test_name="final_output_DMA_error";end
    else begin token_count=128;token_count_i=128;fault_dma=0;test_name="token_count128_admitted";end
    launch(test_name,1);wait_terminal(6);
    if(!fault_injected||completed_heads!=(which==0?1:0)||completed_tokens!=0)$fatal(1,"final output fault completed failed head/token");
    fault_count=fault_count+1;
    $display("QWEN35_MATRIX_NORM_ROPE_TENSOR_FAULT_PASS case=%s status=%0d",test_name,status);
  endtask

  task automatic reset_case(input integer which);
    setup_case(1,2);launch(which==0?"reset_late_head":"reset_late_token",1);
    if(which==0)wait(head_ordinal==1&&rope_stores==8&&ap);
    else wait(head_ordinal==3&&rope_stores==8&&ap);
    @(negedge clk);rst_n=0;start=0;
    repeat(4)@(negedge clk);
    active=0;rst_n=1;
    repeat(12)@(negedge clk);
    if(!ready||done||rv||wv||av||dqv||dp||ap||rp||wp||completed_heads||completed_tokens)
      $fatal(1,"reset did not flush tensor/fabric/engines stage=%0d",which);
    host_mode=1;
    $fdisplay(trace_fd,"{\"event\":\"reset_flush\",\"transaction\":%0d,\"stage\":%0d}",transaction,which);
    reset_count=reset_count+1;
    $display("QWEN35_MATRIX_NORM_ROPE_TENSOR_RESET_PASS stage=%0d no_late_completion=1 old_responses_flushed=1",which);
  endtask

  initial begin
    if(!$value$plusargs("vectors=%s",vectors))$fatal(1,"+vectors=DIR required");
    if(!$value$plusargs("suite=%s",suite))suite="all";
    if(!$value$plusargs("trace=%s",trace_path))trace_path={vectors,"/tensor_trace_",suite,".jsonl"};
    trace_fd=$fopen(trace_path,"w");if(!trace_fd)$fatal(1,"cannot open trace file");
    repeat(5)@(negedge clk);rst_n=1;repeat(3)@(negedge clk);
    for(integer b=0;b<L2_BYTES;b++)begin mem[b]=8'hA5^8'(b*13);expected_memory[b]=mem[b];end
    for(integer beat=0;beat<L2_BEATS;beat++)begin
      logic[511:0] value;
      for(integer b=0;b<64;b++)value[b*8+:8]=mem[beat*64+b];
      host_write(beat,value);
    end
    if(suite=="main"||suite=="all")for(integer c=0;c<4;c++)good_case(c,0);
    if(suite=="negative"||suite=="all")for(integer c=0;c<30;c++)rejected_case(c);
    if(suite=="fault"||suite=="all")begin
      failed_case(0);failed_case(1);
      good_case(1,0,1); // Recovery after a late write fault, without external reset.
    end
    if(suite=="reset"||suite=="all")begin
      for(integer c=0;c<2;c++)reset_case(c);
      good_case(1,0,1); // Fully observed actual Matrix/Norm/RoPE reset recovery.
    end
    if(suite=="boundary"||suite=="all")good_case(1,1);
    if(success_count+reject_count+fault_count+reset_count==0)$fatal(1,"unknown/empty suite");
    $display("QWEN35_MATRIX_NORM_ROPE_TENSOR_PASS suite=%s successes=%0d rejects=%0d faults=%0d resets=%0d actual_matrix_inputs=%0d actual_matrix_outputs=%0d explicit_write_acks=%0d read_stall_cycles=%0d write_stall_cycles=%0d dma_stall_cycles=%0d delayed_ACK_cycles=%0d same_cycle_ACKs=%0d capacity_bytes=1572864 source_injection=0",suite,success_count,reject_count,fault_count,reset_count,total_matrix_inputs,total_matrix_outputs,total_write_acks,read_stalls,write_stalls,dma_stalls,ack_delayed_cycles,same_cycle_ack_count);
    $fclose(trace_fd);$finish;
  end
  initial begin repeat(150000000)@(posedge clk);$fatal(1,"global timeout");end
`undef CHAIN
endmodule
