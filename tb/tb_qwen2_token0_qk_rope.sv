`timescale 1ns/1ps
module tb_qwen2_token0_qk_rope;
 logic clk=0,rst_n=0,iv,ir,ov,orr;always #0.5 clk=~clk;logic[31:0]ei,oi,eo,oo;logic[4:0]flags;logic[31:0]acc,done,lfsr;logic[511:0]q[0:47],k[0:7];logic[15:0]ee[0:895],ex[0:895];integer sent,received;
 fp32_rope_pair dut(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(iv),.in_ready_o(ir),.even_i(ei),.odd_i(oi),.cos_i(32'h3f800000),.sin_i(32'd0),.out_valid_o(ov),.out_ready_i(orr),.even_o(eo),.odd_o(oo),.exception_flags_o(flags),.accepted_pairs_o(acc),.completed_pairs_o(done));
 always_ff@(posedge clk or negedge rst_n)if(!rst_n)lfsr<=32'h519a73cd;else lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};assign orr=lfsr[0]||lfsr[5];
 function automatic[15:0]bf(input[31:0]v);logic[31:0]r;begin r=v+32'h7fff+v[16];return r[31:16];end endfunction
 function automatic[15:0]qv(input integer idx);return q[idx/32][(idx%32)*16+:16];endfunction
 function automatic[15:0]kv(input integer idx);return k[idx/32][(idx%32)*16+:16];endfunction
 task automatic sendpair(input[15:0]a,input[15:0]b);begin @(negedge clk);ei={a,16'd0};oi={b,16'd0};iv=1;do@(posedge clk);while(!ir);@(negedge clk);iv=0;sent++;end endtask
 always_ff@(posedge clk)if(rst_n&&ov&&orr)begin if(bf(eo)!==ee[received]||bf(oo)!==ex[received])$fatal(1,"rope pair=%0d",received);received<=received+1;end
 initial begin iv=0;ei=0;oi=0;sent=0;received=0;$readmemh("work/results/qwen2_shared_l2_tile_payload/q_biased_expected_all_beats.memh",q);$readmemh("work/results/qwen2_kv_projection_vectors/k_biased_expected_beats.memh",k);for(integer h=0;h<12;h++)for(integer p=0;p<64;p++)begin ee[h*64+p]=qv(h*128+p);ex[h*64+p]=qv(h*128+64+p);end for(integer h=0;h<2;h++)for(integer p=0;p<64;p++)begin ee[768+h*64+p]=kv(h*128+p);ex[768+h*64+p]=kv(h*128+64+p);end repeat(6)@(posedge clk);rst_n=1;for(integer i=0;i<896;i++)sendpair(ee[i],ex[i]);wait(received==896);repeat(5)@(posedge clk);if(acc!=896||done!=896||flags[4:1])$fatal(1,"rope counters");$display("QWEN2_TOKEN0_QK_ROPE_PASS Q_pairs=768 K_pairs=128 pairs=896 bf16_bit_exact=1792 position0_identity=1 split_half_layout=1 random_backpressure=1");$finish;end
 initial begin repeat(10000)@(posedge clk);$fatal(1,"timeout sent=%0d received=%0d",sent,received);end
endmodule
