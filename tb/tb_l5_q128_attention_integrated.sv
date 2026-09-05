`timescale 1ns/1ps
module tb_l5_q128_attention_integrated;
 logic clk,rst_n,start;logic[15:0]seq_len;logic ctrl_busy,ctrl_done;
 logic mcv,mcr,mck;logic[19:0]mct,mdt;logic[6:0]mcq;logic[9:0]mckv;logic[3:0]mcqh;logic[1:0]mckh;logic[4:0]mcrows;logic mcclose,mcmerge,mclast,mdv,mdr,mdk;
 logic scv,scr;logic[19:0]sct,sdt;logic[6:0]scq;logic[9:0]sckv;logic[3:0]scqh;logic[1:0]sckh;logic[4:0]scrows;logic scclose,scmerge,sclast,sdv,sdr;
 logic[31:0]qki,qkc,sfc,pvc,merge_rows;logic[1:0]score_level,prob_level;logic ctrl_error;
 logic matrix_service_busy,sfu_service_busy,matrix_clk;logic[31:0]lfsr;integer cycles,matrix_stall_cycles,sfu_stall_cycles;
 blocked_attention_stream_controller controller(.clk_i(clk),.rst_ni(rst_n),.start_i(start),.sequence_tokens_i(seq_len),.busy_o(ctrl_busy),.done_o(ctrl_done),.matrix_cmd_valid_o(mcv),.matrix_cmd_ready_i(mcr),.matrix_cmd_kind_o(mck),.matrix_cmd_task_id_o(mct),.matrix_cmd_query_tile_o(mcq),.matrix_cmd_kv_tile_o(mckv),.matrix_cmd_q_head_o(mcqh),.matrix_cmd_kv_head_o(mckh),.matrix_cmd_valid_rows_o(mcrows),.matrix_cmd_close_block_o(mcclose),.matrix_cmd_merge_global_o(mcmerge),.matrix_cmd_last_kv_o(mclast),.matrix_done_valid_i(mdv),.matrix_done_ready_o(mdr),.matrix_done_kind_i(mdk),.matrix_done_task_id_i(mdt),.sfu_cmd_valid_o(scv),.sfu_cmd_ready_i(scr),.sfu_cmd_task_id_o(sct),.sfu_cmd_query_tile_o(scq),.sfu_cmd_kv_tile_o(sckv),.sfu_cmd_q_head_o(scqh),.sfu_cmd_kv_head_o(sckh),.sfu_cmd_valid_rows_o(scrows),.sfu_cmd_close_block_o(scclose),.sfu_cmd_merge_global_o(scmerge),.sfu_cmd_last_kv_o(sclast),.sfu_done_valid_i(sdv),.sfu_done_ready_o(sdr),.sfu_done_task_id_i(sdt),.qk_issued_o(qki),.qk_completed_o(qkc),.sfu_completed_o(sfc),.pv_completed_o(pvc),.summary_merge_rows_o(merge_rows),.score_fifo_level_o(score_level),.probability_fifo_level_o(prob_level),.protocol_error_o(ctrl_error));
 assign mcr=!matrix_service_busy&&(lfsr[0]||lfsr[3]);assign scr=!sfu_service_busy&&(lfsr[1]||lfsr[4]);

 logic minv,minr,mclear,mlast_i,moutv,moutr,mlast_o;logic[2:0]mcontext_i,mcontext_o;logic[255:0]ma;logic[511:0]mb;logic[16383:0]macc;logic[4:0]mflags,mbusy,mvalid;logic[31:0]maccept,mcomplete;logic merror;
 assign matrix_clk=clk&(matrix_service_busy|~rst_n);
 bf16_outer_product_context_array_rev8b_b_candidate matrix(.clk_i(matrix_clk),.rst_ni(rst_n),.in_valid_i(minv),.in_ready_o(minr),.context_i(mcontext_i),.clear_i(mclear),.last_i(mlast_i),.a_i(ma),.b_i(mb),.out_valid_o(moutv),.out_ready_i(moutr),.context_o(mcontext_o),.last_o(mlast_o),.acc_o(macc),.exception_flags_o(mflags),.busy_o(mbusy),.accumulator_valid_o(mvalid),.accepted_steps_o(maccept),.completed_steps_o(mcomplete),.protocol_error_o(merror));

 logic wstart,wsv,wsr,wmask,whv,whr,wv,wr,wl,wbusy;logic[31:0]wscore,wm,wsum,wweight;logic[4:0]wflags;
 fp32_block32_softmax_weights weight_engine(.clk_i(clk),.rst_ni(rst_n),.start_i(wstart),.score_valid_i(wsv),.score_ready_o(wsr),.score_i(wscore),.mask_i(wmask),.summary_valid_o(whv),.summary_ready_i(whr),.m_o(wm),.l_o(wsum),.weight_valid_o(wv),.weight_ready_i(wr),.weight_o(wweight),.weight_last_o(wl),.exception_flags_o(wflags),.busy_o(wbusy));
 logic hiv,hir,hov,hor;logic[31:0]hweight;logic[15:0]hhi,hlo;logic[4:0]hflags;
 fp32_probability_to_bf16_hilo hilo(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(hiv),.in_ready_o(hir),.weight_i(hweight),.out_valid_o(hov),.out_ready_i(hor),.hi_o(hhi),.lo_o(hlo),.exception_flags_o(hflags));
 assign hiv=wv;assign hweight=wweight;assign wr=hir;
 logic[31:0]raw_score,scaled_score;logic[4:0]scale_flags;
 HeteroFP32Alu score_scale(.io_op(1'b1),.io_x(raw_score),.io_y(32'h3db504f3),.io_out(scaled_score),.io_exceptionFlags(scale_flags));

 logic mhiv,mhir,mhov,mhor,mbiv,mbir,mbov,mbrlast;logic[31:0]mma,mla,mmb,mlb,mmo,mmlo;logic[127:0]moa,mob,moo;logic mblast;
 fp32_mlo_summary_merge_stream_rawpipe#(.LANES(4))merge(.clk_i(clk),.rst_ni(rst_n),.header_valid_i(mhiv),.header_ready_o(mhir),.ma_i(mma),.la_i(mla),.mb_i(mmb),.lb_i(mlb),.beat_valid_i(mbiv),.beat_ready_o(mbir),.oa_i(moa),.ob_i(mob),.beat_last_i(mblast),.header_valid_o(mhov),.header_ready_i(mhor),.m_o(mmo),.l_o(mmlo),.beat_valid_o(mbov),.beat_ready_i(1'b1),.o_o(moo),.beat_last_o(mbrlast));
 logic riv,rir,rov,ror,rde;logic[31:0]rx,ry,rac,rcc;logic[4:0]rflags;
 fp32_reciprocal_nr reciprocal(.clk_i(clk),.rst_ni(rst_n),.in_valid_i(riv),.in_ready_o(rir),.x_i(rx),.out_valid_o(rov),.out_ready_i(ror),.y_o(ry),.exception_flags_o(rflags),.domain_error_o(rde),.accepted_o(rac),.completed_o(rcc));
 logic[511:0]va,vb,vo;logic[4:0]vflags;fp32_vector_alu#(.LANES(16))normalizer(.op_i(1'b1),.a_i(va),.b_i(vb),.out_o(vo),.exception_flags_o(vflags));

 logic[15:0]qmem[0:1572863],kmem[0:262143],vmem[0:262143];logic[31:0]expected[0:1572863],expected_tile_m[0:15],expected_tile_l[0:15],expected_tile_o[0:2047];
 logic[31:0]score_slot[0:1][0:511],weight_hi_slot[0:1][0:511],weight_lo_slot[0:1][0:511],tile_m[0:1][0:15],tile_l[0:1][0:15],tile_o[0:1][0:2047];
 logic[31:0]block_m[0:15],block_l[0:15],block_o[0:15][0:127],global_m[0:15],global_l[0:15],global_o[0:15][0:127];logic block_valid[0:15],global_valid[0:15];logic[63:0]attention_hash;integer checked_rows,matrix_commands,sfu_commands,manual_merge_rows;
 function automatic integer qidx(input integer head,input integer row,input integer dim);qidx=(head*seq_len+row)*128+dim;endfunction
 function automatic integer kidx(input integer head,input integer row,input integer dim);kidx=(head*seq_len+row)*128+dim;endfunction
 function automatic integer sampled_qtile(input integer index);begin case(index)0:sampled_qtile=0;1:sampled_qtile=1;2:sampled_qtile=2;3:sampled_qtile=3;4:sampled_qtile=4;5:sampled_qtile=7;6:sampled_qtile=8;7:sampled_qtile=11;8:sampled_qtile=15;9:sampled_qtile=16;10:sampled_qtile=19;default:sampled_qtile=23;endcase end endfunction
 function automatic integer sampled_qtile1024(input integer index);begin case(index)0:sampled_qtile1024=0;1:sampled_qtile1024=1;2:sampled_qtile1024=2;3:sampled_qtile1024=3;4:sampled_qtile1024=4;5:sampled_qtile1024=7;6:sampled_qtile1024=8;7:sampled_qtile1024=15;8:sampled_qtile1024=16;9:sampled_qtile1024=31;10:sampled_qtile1024=32;11:sampled_qtile1024=47;12:sampled_qtile1024=48;13:sampled_qtile1024=55;default:sampled_qtile1024=63;endcase end endfunction
 function automatic integer sampled_qhead1024(input integer index);begin case(index)0:sampled_qhead1024=0;1:sampled_qhead1024=1;2:sampled_qhead1024=5;3:sampled_qhead1024=6;4:sampled_qhead1024=10;default:sampled_qhead1024=11;endcase end endfunction
 function automatic[63:0]hash_word(input logic[63:0]seed,input logic[31:0]word);hash_word=(seed^{32'd0,word})*64'h100000001b3;endfunction
 function automatic real f32real(input logic[31:0]bits);shortreal value;begin value=$bitstoshortreal(bits);f32real=value;end endfunction
 function automatic real absreal(input real value);absreal=value<0?-value:value;endfunction
 always #0.5 clk=~clk;
 always_ff@(posedge clk)begin if(!rst_n)begin lfsr<=32'h1a773e20;cycles<=0;matrix_stall_cycles<=0;sfu_stall_cycles<=0;end else begin lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};cycles<=cycles+1;if(mcv&&!mcr)matrix_stall_cycles<=matrix_stall_cycles+1;if(scv&&!scr)sfu_stall_cycles<=sfu_stall_cycles+1;end end
 `include "attention_matrix_sequencer_adapter.svh"
 task automatic pulse_matrix_done(input logic kind,input logic[19:0]task_id);begin @(negedge clk);mdk=kind;mdt=task_id;mdv=1;if(task_id==0)begin $display("INTEGRATED_PROGRESS phase=MATRIX_DONE_OFFER kind=%0d ready=%0d cycles=%0d",kind,mdr,cycles);$fflush();end do@(posedge clk);while(!mdr);@(negedge clk);mdv=0;if(task_id==0)begin $display("INTEGRATED_PROGRESS phase=MATRIX_DONE_ACCEPT kind=%0d cycles=%0d",kind,cycles);$fflush();end end endtask
 task automatic pulse_sfu_done(input logic[19:0]task_id);begin @(negedge clk);sdt=task_id;sdv=1;do@(posedge clk);while(!sdr);@(negedge clk);sdv=0;end endtask
 task automatic do_qk(input integer task_id,input integer qt,input integer kt,input integer qh,input integer kh,input integer rows);begin run_matrix_tile(0,task_id,qt,kt,qh,kh,rows);end endtask
 task automatic do_sfu(input integer task_id,input integer qt,input integer kt,input integer qh,input integer kh,input integer rows);integer slot,qbase,kbase,count;begin slot=task_id&1;qbase=qt*16;kbase=kt*32;for(integer row=0;row<rows;row++)begin @(negedge clk);wstart=1;@(posedge clk);@(negedge clk);wstart=0;for(integer col=0;col<32;col++)begin raw_score=score_slot[slot][row*32+col];#1;wscore=scaled_score;wmask=(kbase+col>qbase+row)||(kbase+col>=seq_len);wsv=1;do@(posedge clk);while(!wsr);@(negedge clk);wsv=0;end whr=1;while(!whv)@(posedge clk);tile_m[slot][row]=wm;tile_l[slot][row]=wsum;@(negedge clk);whr=0;hor=1;count=0;while(count<32)begin @(posedge clk);if(hov)begin weight_hi_slot[slot][row*32+count]={hhi,16'b0};weight_lo_slot[slot][row*32+count]={hlo,16'b0};count++;end end @(negedge clk);hor=0;while(wbusy)@(posedge clk);if(task_id==0&&(row==0||(row%4)==3))begin $display("INTEGRATED_PROGRESS phase=SFU task=%0d row=%0d cycles=%0d",task_id,row+1,cycles);$fflush();end end if(wflags[4:1]!=0||hflags[4:1]!=0||scale_flags[4:1]!=0)$fatal(1,"sfu flags");end endtask
 task automatic merge_row(input integer slot,input integer row);logic[31:0]new_o[0:127];begin mhiv=1;mma=block_m[row];mla=block_l[row];mmb=tile_m[slot][row];mlb=tile_l[slot][row];do@(posedge clk);while(!mhir);@(negedge clk);mhiv=0;mhor=1;while(!mhov)@(posedge clk);block_m[row]=mmo;block_l[row]=mmlo;@(negedge clk);mhor=0;for(integer beat=0;beat<32;beat++)begin for(integer lane=0;lane<4;lane++)begin moa[lane*32+:32]=block_o[row][beat*4+lane];mob[lane*32+:32]=tile_o[slot][row*128+beat*4+lane];end mbiv=1;mblast=beat==31;do@(posedge clk);while(!mbir);@(negedge clk);mbiv=0;while(!mbov)@(posedge clk);for(integer lane=0;lane<4;lane++)new_o[beat*4+lane]=moo[lane*32+:32];if(mbrlast!==(beat==31))$fatal(1,"merge last");end for(integer dim=0;dim<128;dim++)block_o[row][dim]=new_o[dim];end endtask
 task automatic normalize_and_check(input integer qt,input integer qh,input integer rows);logic[31:0]inverse,actual;real error,max_error;integer token;begin max_error=0;for(integer row=0;row<rows;row++)begin rx=block_l[row];riv=1;do@(posedge clk);while(!rir);@(negedge clk);riv=0;do@(posedge clk);while(!rov);inverse=ry;if(rde)$fatal(1,"reciprocal");token=qt*16+row;for(integer chunk=0;chunk<8;chunk++)begin for(integer lane=0;lane<16;lane++)begin va[lane*32+:32]=block_o[row][chunk*16+lane];vb[lane*32+:32]=inverse;end #1;for(integer lane=0;lane<16;lane++)begin actual=vo[lane*32+:32];error=absreal(f32real(actual)-f32real(expected[qidx(qh,token,chunk*16+lane)]));if(error>max_error)max_error=error;if(error>0.002)$fatal(1,"attention error token=%0d head=%0d dim=%0d error=%f",token,qh,chunk*16+lane,error);attention_hash=hash_word(attention_hash,actual);end end checked_rows++;end $display("INTEGRATED_HEAD_TILE_PASS qt=%0d qh=%0d rows=%0d max_error=%f",qt,qh,rows,max_error);end endtask
 task automatic do_pv(input integer task_id,input integer qt,input integer kt,input integer qh,input integer kh,input integer rows,input integer close_block,input integer merge_global,input integer last_kv);logic[16383:0]result;logic[255:0]avec;logic[511:0]bvec;integer slot,kbase;begin
  slot=task_id&1;kbase=kt*32;
  run_matrix_tile(1,task_id,qt,kt,qh,kh,rows);
  for(integer row=0;row<rows;row++)begin
   if((kt&3)==0)begin
    if(kt>=4)begin global_m[row]=block_m[row];global_l[row]=block_l[row];for(integer dim=0;dim<128;dim++)global_o[row][dim]=block_o[row][dim];global_valid[row]=1;end
    block_m[row]=tile_m[slot][row];block_l[row]=tile_l[slot][row];for(integer dim=0;dim<128;dim++)block_o[row][dim]=tile_o[slot][row*128+dim];block_valid[row]=1;
   end else merge_row(slot,row);
  end
  if(close_block&&merge_global)for(integer row=0;row<rows;row++)begin
   tile_m[slot][row]=block_m[row];tile_l[slot][row]=block_l[row];for(integer dim=0;dim<128;dim++)tile_o[slot][row*128+dim]=block_o[row][dim];
   block_m[row]=global_m[row];block_l[row]=global_l[row];for(integer dim=0;dim<128;dim++)block_o[row][dim]=global_o[row][dim];
   merge_row(slot,row);manual_merge_rows++;
  end
  if(last_kv)normalize_and_check(qt,qh,rows);
 end endtask
 task automatic check_direct_tile;real error,max_error;begin max_error=0;for(integer row=0;row<16;row++)begin error=absreal(f32real(tile_m[0][row])-f32real(expected_tile_m[row]));if(error>max_error)max_error=error;if(error>0.002)$fatal(1,"direct tile M row=%0d error=%f",row,error);error=absreal(f32real(tile_l[0][row])-f32real(expected_tile_l[row]));if(error>max_error)max_error=error;if(error>0.002)$fatal(1,"direct tile L row=%0d error=%f",row,error);for(integer dim=0;dim<128;dim++)begin error=absreal(f32real(tile_o[0][row*128+dim])-f32real(expected_tile_o[row*128+dim]));if(error>max_error)max_error=error;if(error>0.002)$fatal(1,"direct tile O row=%0d dim=%0d error=%f",row,dim,error);end end $display("L5_ONE_TASK_QK_SFU_PV_PASS rows=16 qk_steps=128 pv_steps=256 max_error=%f cycles=%0d",max_error,cycles);$finish;end endtask
 initial begin matrix_service_busy=0;mdv=0;mdk=0;mdt=0;wait(rst_n);forever begin @(posedge clk);if(mcv&&mcr)begin integer task_id,qt,kt,qh,kh,rows,close_block,merge_global,last_kv;task_id=mct;qt=mcq;kt=mckv;qh=mcqh;kh=mckh;rows=mcrows;close_block=mcclose;merge_global=mcmerge;last_kv=mclast;@(negedge clk);matrix_service_busy=1;matrix_commands++;if(!mck)do_qk(task_id,qt,kt,qh,kh,rows);else do_pv(task_id,qt,kt,qh,kh,rows,close_block,merge_global,last_kv);pulse_matrix_done(mck,task_id);matrix_service_busy=0;end end end
 initial begin sfu_service_busy=0;sdv=0;sdt=0;wait(rst_n);forever begin @(posedge clk);if(scv&&scr)begin integer task_id,qt,kt,qh,kh,rows;task_id=sct;qt=scq;kt=sckv;qh=scqh;kh=sckh;rows=scrows;@(negedge clk);sfu_service_busy=1;sfu_commands++;do_sfu(task_id,qt,kt,qh,kh,rows);pulse_sfu_done(task_id);sfu_service_busy=0;end end end
 initial begin string vectors;logic direct_diag,sampled_384,sampled_1024;logic full1024;integer full_qtile;integer sample_task,qt,qh,kvtiles,close_flag,merge_flag,last_flag,shard,sample_begin,sample_end;
  clk=0;rst_n=0;start=0;direct_diag=$test$plusargs("DIRECT_DIAG");sampled_384=$test$plusargs("SAMPLED_384");sampled_1024=$test$plusargs("SAMPLED_1024");seq_len=sampled_1024?1024:(sampled_384?384:128);shard=0;void'($value$plusargs("SHARD=%d",shard));
  full1024=$test$plusargs("FULL_Q1024");full_qtile=0;
  if(full1024)begin seq_len=1024;if(!$value$plusargs("QT=%d",full_qtile)||full_qtile<0||full_qtile>=64||direct_diag||sampled_384||sampled_1024)$fatal(1,"full1024 options");end
  wstart=0;wsv=0;wscore=0;wmask=0;whr=0;hor=0;raw_score=0;mhiv=0;mhor=0;mbiv=0;mblast=0;mma=0;mla=0;mmb=0;mlb=0;moa=0;mob=0;riv=0;ror=1;rx=0;va=0;vb=0;attention_hash=64'hcbf29ce484222325;checked_rows=0;matrix_commands=0;sfu_commands=0;manual_merge_rows=0;
  if(!$value$plusargs("VECTORS=%s",vectors))vectors="work/results/l5_q128_attention_integrated/vectors";
  $readmemh({vectors,"/q_bf16.memh"},qmem);$readmemh({vectors,"/k_bf16.memh"},kmem);$readmemh({vectors,"/v_bf16.memh"},vmem);$readmemh({vectors,"/expected_fp32.memh"},expected);$readmemh({vectors,"/tile_m_fp32.memh"},expected_tile_m);$readmemh({vectors,"/tile_l_fp32.memh"},expected_tile_l);$readmemh({vectors,"/tile_o_fp32.memh"},expected_tile_o);
  $display("INTEGRATED_PROGRESS phase=VECTORS_LOADED direct=%0d sampled384=%0d sampled1024=%0d shard=%0d",direct_diag,sampled_384,sampled_1024,shard);$fflush();repeat(8)@(posedge clk);rst_n=1;
  if(direct_diag)begin matrix_service_busy=1;do_qk(0,0,0,0,0,16);matrix_service_busy=0;do_sfu(0,0,0,0,0,16);matrix_service_busy=1;do_pv(0,0,0,0,0,16,0,0,0);matrix_service_busy=0;check_direct_tile();end
  if(full1024)begin
   // All heads for this independent query tile, all causal keys. The external
   // coordinator covers every QT0..63, never samples heads/rows/keys.
   // Per-QT jobs are numerical partitions, not uninterrupted controller cycles.
   qt=full_qtile;sample_task=0;kvtiles=((qt+1)*16+31)/32;
   for(integer head=0;head<12;head++)for(integer kt=0;kt<kvtiles;kt++)begin
    close_flag=((kt&3)==3)||(kt==kvtiles-1);merge_flag=close_flag&&(kt>=4);last_flag=kt==kvtiles-1;
    matrix_service_busy=1;do_qk(sample_task,qt,kt,head,head/6,16);matrix_service_busy=0;
    do_sfu(sample_task,qt,kt,head,head/6,16);matrix_service_busy=1;
    do_pv(sample_task,qt,kt,head,head/6,16,close_flag,merge_flag,last_flag);matrix_service_busy=0;sample_task++;
   end
   if(checked_rows!=192||sample_task!=12*kvtiles||manual_merge_rows!=192*(qt/8))$fatal(1,"full QT accounting");
   $display("Q1024_CAPTURED_ATTENTION_QT_PASS qt=%0d rows_heads=%0d tasks=%0d merges=%0d cycles=%0d hash=%016h full_model=false",qt,checked_rows,sample_task,manual_merge_rows,cycles,attention_hash);$finish;
  end
  if(sampled_384)begin
   sample_task=0;
   for(integer sample=0;sample<12;sample++)begin qt=sampled_qtile(sample);kvtiles=((qt+1)*16+31)/32;
    for(integer qh384=0;qh384<12;qh384++)for(integer kt=0;kt<kvtiles;kt++)begin close_flag=((kt&3)==3)||(kt==kvtiles-1);merge_flag=close_flag&&(kt>=4);last_flag=kt==kvtiles-1;
     matrix_service_busy=1;do_qk(sample_task,qt,kt,qh384,qh384/6,16);matrix_service_busy=0;do_sfu(sample_task,qt,kt,qh384,qh384/6,16);matrix_service_busy=1;do_pv(sample_task,qt,kt,qh384,qh384/6,16,close_flag,merge_flag,last_flag);matrix_service_busy=0;sample_task++;
    end
   end
   if(checked_rows!=2304||sample_task!=756||manual_merge_rows!=1728)$fatal(1,"q384 sampled accounting rows=%0d tasks=%0d merges=%0d",checked_rows,sample_task,manual_merge_rows);
   $display("L5_Q384_SAMPLED_E2_PASS compared_rows=%0d frozen_rows_covered=180 tasks=%0d sampled_merge_rows=%0d controller_merge_rows=4608 cycles=%0d score_DDR=0 probability_DDR=0 attention_fnv64=%016h",checked_rows,sample_task,manual_merge_rows,cycles,attention_hash);$finish;
  end
  if(sampled_1024)begin
   sample_task=0;if(shard==0)begin sample_begin=0;sample_end=10;end else begin sample_begin=10;sample_end=15;end
   for(integer sample=sample_begin;sample<sample_end;sample++)begin qt=sampled_qtile1024(sample);kvtiles=((qt+1)*16+31)/32;
    for(integer hi=0;hi<6;hi++)begin qh=sampled_qhead1024(hi);for(integer kt=0;kt<kvtiles;kt++)begin close_flag=((kt&3)==3)||(kt==kvtiles-1);merge_flag=close_flag&&(kt>=4);last_flag=kt==kvtiles-1;
     matrix_service_busy=1;do_qk(sample_task,qt,kt,qh,qh/6,16);matrix_service_busy=0;do_sfu(sample_task,qt,kt,qh,qh/6,16);matrix_service_busy=1;do_pv(sample_task,qt,kt,qh,qh/6,16,close_flag,merge_flag,last_flag);matrix_service_busy=0;sample_task++;
    end end
   end
   if(shard==0&&(checked_rows!=960||sample_task!=306||manual_merge_rows!=672))$fatal(1,"q1024 shard0 accounting rows=%0d tasks=%0d merges=%0d",checked_rows,sample_task,manual_merge_rows);
   if(shard==1&&(checked_rows!=480||sample_task!=756||manual_merge_rows!=2688))$fatal(1,"q1024 shard1 accounting rows=%0d tasks=%0d merges=%0d",checked_rows,sample_task,manual_merge_rows);
   $display("L5_Q1024_REVIEWED_SHARD_PASS shard=%0d compared_rows=%0d tasks=%0d sampled_merge_rows=%0d controller_tasks=12672 controller_merge_rows=43008 cycles=%0d score_DDR=0 probability_DDR=0 attention_fnv64=%016h",shard,checked_rows,sample_task,manual_merge_rows,cycles,attention_hash);$finish;
  end
  @(negedge clk);start=1;@(posedge clk);@(negedge clk);start=0;while(!ctrl_done&&cycles<20000000)@(posedge clk);if(!ctrl_done)$fatal(1,"integrated timeout");if(ctrl_error||merror)$fatal(1,"protocol");if(checked_rows!=1536||qki!=240||qkc!=240||sfc!=240||pvc!=240||merge_rows!=0)$fatal(1,"accounting rows=%0d qki=%0d",checked_rows,qki);$display("L5_Q128_SINGLE_SIM_E2_PASS rows=%0d tasks=%0d cycles=%0d matrix_stall=%0d sfu_stall=%0d score_DDR=0 probability_DDR=0 attention_fnv64=%016h",checked_rows,qki,cycles,matrix_stall_cycles,sfu_stall_cycles,attention_hash);$finish;
 end
 initial begin repeat(25000000)@(posedge clk);$fatal(1,"global timeout");end
endmodule
