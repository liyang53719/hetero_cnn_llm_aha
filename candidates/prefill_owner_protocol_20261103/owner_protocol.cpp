// Actual emitted DownOwner/banks/credit protocol test. Matrix values below are
// labelled synthetic protocol payloads, NOT arithmetic or full-block numerics.
#include "VTransposedDenseDownOwner.h"
#include "verilated.h"
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <deque>
#include <stdexcept>
#include <string>
#include <algorithm>
static uint64_t ticks=0;static unsigned aversion=0;
static void require(bool v,const char* s){if(!v)throw std::runtime_error(std::string(s)+" tick="+std::to_string(ticks));}
static uint16_t activation_pattern(unsigned m,unsigned k){return 0x3f00+((m*3+k+aversion*5)%64);}
static uint16_t weight_pattern(unsigned k,unsigned n){return 0x4000+((k*7+n)%64);}
static uint32_t result_pattern(unsigned c,unsigned g,unsigned n,unsigned j){return 0x3f000000u+((g*5+c)*4096u+n*256u+j)*128u;}
#include "ports_generated.hpp"
static void edge(VTransposedDenseDownOwner& d){d.clock=1;d.eval();d.clock=0;d.eval();++ticks;require(ticks<=2000000,"global tick bound");require(!Verilated::gotFinish(),"unexpected RTL finish/assertion");}
struct Read {bool active=false;uint64_t address=0,tag=0;unsigned beats=0,index=0;};
struct Write {bool active=false;uint64_t address=0,tag=0;unsigned beats=0,index=0,delay=0;};
struct Stats {unsigned aBeats=0,bBeats=0,requests=0,groups=0,steps=0,writes=0,retired=0,groupDones=0,readReturns=0;bool multi=false,aMulti=false,bMulti=false,prefetch=false;};
struct Config {unsigned n=320,k=128;bool bf16=true;unsigned tag=1,fault=0;bool holdAck=true;};
static constexpr uint64_t A=0x100003c0ull,B=0x20000040ull,Y=0x300003c0ull;
static void quiet(VTransposedDenseDownOwner& d){d.io_job_valid=0;d.io_burst_ready=0;d.io_burstResponse_valid=0;d.io_writeRequest_ready=0;d.io_writeData_ready=0;d.io_writeResponse_valid=0;d.io_matrix_group_ready=0;d.io_matrix_step_ready=0;d.io_matrix_result_valid=0;d.io_matrix_done_valid=0;d.io_done_ready=0;}
static void reset(VTransposedDenseDownOwner& d){zero_inputs(d);d.reset=1;for(int i=0;i<5;i++)edge(d);d.reset=0;edge(d);}
static void snoop(VTransposedDenseDownOwner& d,bool flush){quiet(d);d.io_activationCoherence_flush=flush;d.io_activationCoherence_write_valid=!flush;d.io_activationCoherence_write_bits_address=A;d.io_activationCoherence_write_bits_bytes=64;edge(d);d.io_activationCoherence_flush=0;d.io_activationCoherence_write_valid=0;edge(d);}
static uint32_t memory_word(uint64_t addr,const Config& c){
 if(addr>=A&&addr<A+128ull*c.k*4){unsigned x=(addr-A)/4;return uint32_t(activation_pattern(x/c.k,x%c.k))<<16;}
 unsigned elem=c.bf16?2:4;require(addr>=B&&addr+4<=B+uint64_t(c.k)*c.n*elem,"read outside A/B");unsigned x=(addr-B)/elem;
 if(c.bf16)return weight_pattern(x/c.n,x%c.n)|(uint32_t(weight_pattern((x+1)/c.n,(x+1)%c.n))<<16);
 return uint32_t(weight_pattern(x/c.n,x%c.n))<<16;
}
static Stats run(VTransposedDenseDownOwner& d,const Config& c){
 quiet(d);d.io_prefixWorkspace_valid=1;d.io_prefixWorkspace_base=0x40000000ull;d.io_prefixWorkspace_extent=1<<20;d.io_prefixWorkspace_generation=1;d.io_prefixWorkspace_splitK=2560;
 d.io_job_bits_kind=1;d.io_job_bits_m=128;d.io_job_bits_n=c.n;d.io_job_bits_k=c.k;d.io_job_bits_a=A;d.io_job_bits_b=B;d.io_job_bits_dst=Y;d.io_job_bits_tag=c.tag;d.io_job_bits_weightBf16=c.bf16;d.io_job_bits_activationBf16=0;d.io_job_bits_outputBf16=0;d.io_job_bits_materializeDenseOutput=0;d.io_job_bits_writeBytes=128ull*c.n*4;
 d.io_job_valid=1;d.eval();require(d.io_job_ready,"job not ready");edge(d);d.io_job_valid=0;
 Read r;Write w;Stats st;std::deque<unsigned> results;bool group=false,finished=false,doneSent=false,injected=false;unsigned groupNg=0,contexts=0,ordinal=0,returned=0;uint32_t groupTag=0;unsigned groupIndex=0;uint64_t start=ticks;bool firstAckHeld=false;uint64_t ackBytes=0;
 while(ticks-start<200000){
  // One accepted read descriptor; a single posted write descriptor may wait
  // beside it, but read and external write payload never use the same cycle.
  d.io_burst_ready=!r.active&&!w.active;
  d.io_burstResponse_valid=r.active;d.io_burstResponse_bits_tag=r.tag;d.io_burstResponse_bits_last=r.index+1==r.beats;d.io_burstResponse_bits_error=0;
  if(r.active)for(unsigned i=0;i<16;i++)d.io_burstResponse_bits_data[i]=memory_word(r.address+r.index*64+i*4,c);
  bool badBeat=r.active&&c.fault&&!injected&&r.beats>1&&((c.fault==2)?r.index+1==r.beats:r.index==0);
  if(badBeat){if(c.fault==1)d.io_burstResponse_bits_last=1;if(c.fault==2)d.io_burstResponse_bits_last=0;if(c.fault==3)d.io_burstResponse_bits_tag^=1;if(c.fault==4)d.io_burstResponse_bits_error=1;}
  d.io_writeRequest_ready=!w.active;d.io_writeData_ready=w.active&&!r.active&&w.index<w.beats&&(ticks%5!=0);
  d.io_writeResponse_valid=w.active&&w.index==w.beats&&w.delay==0;d.io_writeResponse_bits_tag=w.tag;d.io_writeResponse_bits_error=0;
  d.io_matrix_group_ready=!group;d.io_matrix_step_ready=group&&!finished&&results.size()<2&&(ticks%7!=0);
  d.io_matrix_result_valid=!results.empty();d.io_matrix_result_bits_context=results.empty()?0:results.front();d.io_matrix_result_bits_last=1;d.io_matrix_result_bits_error=0;
  if(!results.empty())result_values(d,results.front(),groupIndex-1);
  d.io_matrix_done_valid=group&&finished&&results.empty()&&returned==contexts&&!doneSent;d.io_matrix_done_bits_tag=groupTag;d.io_matrix_done_bits_error=0;d.io_done_ready=1;d.eval();
  require(!d.io_memory_valid&&!d.io_matrix_seed_begin_valid&&!d.io_matrix_seed_beat_valid,"unexpected prefix/scalar service");
  bool rf=d.io_burst_valid&&d.io_burst_ready,rr=d.io_burstResponse_valid&&d.io_burstResponse_ready,wf=d.io_writeRequest_valid&&d.io_writeRequest_ready,wd=d.io_writeData_valid&&d.io_writeData_ready,wa=d.io_writeResponse_valid&&d.io_writeResponse_ready,gf=d.io_matrix_group_valid&&d.io_matrix_group_ready,sf=d.io_matrix_step_valid&&d.io_matrix_step_ready,res=d.io_matrix_result_valid&&d.io_matrix_result_ready,md=d.io_matrix_done_valid&&d.io_matrix_done_ready,jobdone=d.io_done_valid&&d.io_done_ready;
  Read nr;Write nw;
  if(rf){require(!injected,"new read accepted after fault");nr={true,d.io_burst_bits_address,d.io_burst_bits_tag,unsigned(d.io_burst_bits_beats),0};require(nr.beats>0&&nr.beats<=16&&(nr.address&63)==0&&((nr.address&1023)+nr.beats*64<=1024)&&((nr.address&4095)+nr.beats*64<=4096),"burst bounds");st.requests++;st.multi|=nr.beats>1;
   if(nr.address>=A&&nr.address<A+128ull*c.k*4){st.aBeats+=nr.beats;st.aMulti|=nr.beats>1;}else{st.bBeats+=nr.beats;st.bMulti|=nr.beats>1;unsigned elem=c.bf16?2:4;unsigned col=((nr.address-B)/elem)%c.n;if(groupIndex==1&&col>=160&&ackBytes<128ull*160*4){if(!st.prefetch)std::printf("EVENT next_N_read_before_old_group_ACK tick=%llu old_ACK_bytes=%llu required=%u pending_write=%u\n",(unsigned long long)ticks,(unsigned long long)ackBytes,128*160*4,w.active);st.prefetch=true;}}
  }
  if(wf){nw={true,d.io_writeRequest_bits_address,d.io_writeRequest_bits_tag,unsigned(d.io_writeRequest_bits_beats),0,0};require(nw.beats>0&&nw.beats<=16&&(nw.address&63)==0&&((nw.address&1023)+nw.beats*64<=1024),"write request bounds");}
  if(wd){require(d.io_writeData_bits_last==(w.index+1==w.beats),"write LAST");uint64_t addr=w.address+w.index*64;require(addr>=Y&&addr+64<=Y+128ull*c.n*4,"write bounds");unsigned x=(addr-Y)/4,row=x/c.n,col=x%c.n;unsigned ng=(col/160)*160,ctx=(col-ng)/32,half=(col%32)/16;for(unsigned i=0;i<16;i++)require(d.io_writeData_bits_data[i]==result_pattern(ctx,ng/160,i,half*128+row),"result write payload/order");}
  if(gf){require(!group&&results.empty(),"group overlap");groupTag=d.io_matrix_group_bits_tag;require(groupTag==c.tag&&d.io_matrix_group_bits_transposedDense&&d.io_matrix_group_bits_sliceMask==255,"group identity");groupNg=st.groups*160;require(ackBytes==128ull*groupNg*4&&!w.active,"next group crossed old write ACK fence");require(!r.active,"next group crossed accepted read debt");contexts=std::min(5u,(c.n-groupNg)/32);ordinal=0;returned=0;finished=false;doneSent=false;group=true;++st.groups;++groupIndex;}
  unsigned push=99;
  if(sf){unsigned cx=ordinal%contexts,k=ordinal/contexts;require(k<c.k&&d.io_matrix_step_bits_context==cx&&bool(d.io_matrix_step_bits_clear)==(k==0)&&bool(d.io_matrix_step_bits_last)==(k+1==c.k)&&bool(d.io_matrix_step_bits_emit)==(k+1==c.k)&&bool(d.io_matrix_step_bits_finish)==(k+1==c.k&&cx+1==contexts),"step identity/order");check_operands(d,k,cx,groupNg);if(d.io_matrix_step_bits_last)push=cx;if(d.io_matrix_step_bits_finish)finished=true;++ordinal;++st.steps;}
  if(res){require(results.front()==returned,"result context order");results.pop_front();++returned;++st.retired;}
  if(md){require(ordinal==contexts*c.k&&returned==contexts,"done before terminal returns");doneSent=true;group=false;++st.groupDones;}
  unsigned status=jobdone?d.io_done_bits_status:0;uint64_t bytes=jobdone?d.io_done_bits_writeBytes:0;
  if(jobdone){require(d.io_done_bits_tag==c.tag,"done tag");require(!r.active&&!w.active&&!group&&results.empty(),"done with protocol debt");if(c.fault){require(injected&&status!=0&&st.groups==0&&st.writes==0,"fault did not drain before finish");}else{require(status==0&&!d.io_resetRequired&&bytes==128ull*c.n*4&&st.steps==c.k*(c.n/32)&&st.groups==(c.n+159)/160&&st.retired==c.n/32&&st.groupDones==st.groups&&st.readReturns==st.aBeats+st.bBeats&&ackBytes==128ull*c.n*4&&st.bBeats==uint64_t(c.k)*c.n*(c.bf16?2:4)/64,"job completion/external byte counts");}}
  edge(d);
  if(rr){++st.readReturns;if(badBeat)injected=true;if(++r.index==r.beats)r.active=false;}
  if(wd){++w.index;if(w.index==w.beats&&c.holdAck&&!firstAckHeld){w.delay=64;firstAckHeld=true;}}
  if(w.delay)w.delay--;
  if(wa){ackBytes+=w.beats*64;w.active=false;++st.writes;}
  if(rf)r=nr;if(wf)w=nw;if(push!=99)results.push_back(push);
  if(jobdone){quiet(d);std::printf("COUNTERS tag=%u accepted_steps=%u retired_results=%u group_done=%u returned_beats=%u write_ACK_count=%u write_ACK_bytes=%llu\n",c.tag,st.steps,st.retired,st.groupDones,st.readReturns,st.writes,(unsigned long long)ackBytes);std::printf("CASE tag=%u N=%u K=%u Bbf16=%u fault=%u ticks=%llu A=%u B=%u requests=%u multi=%u A_multi=%u B_multi=%u groups=%u steps=%u writeACK=%u prefetch=%u PASS_OWNER_PROTOCOL_ONLY\n",c.tag,c.n,c.k,c.bf16,c.fault,(unsigned long long)(ticks-start),st.aBeats,st.bBeats,st.requests,st.multi,st.aMulti,st.bMulti,st.groups,st.steps,st.writes,st.prefetch);return st;}
 }
 throw std::runtime_error("case tick bound");
}
int main(int argc,char** argv){Verilated::commandArgs(argc,argv);try{VTransposedDenseDownOwner d;reset(d);auto a=run(d,{320,128,true,1,0,true});require(a.aBeats==1024&&a.bBeats==1280&&a.aMulti&&a.bMulti&&a.prefetch,"initial full load/prefetch");auto b=run(d,{192,128,true,2,0,true});require(b.aBeats==0&&b.bBeats==768&&!b.aMulti&&b.bMulti&&b.prefetch,"same-A residency/tail prefetch");++aversion;snoop(d,false);auto c=run(d,{192,128,false,3,0,true});require(c.aBeats==1024&&c.bBeats==1536&&c.aMulti&&c.bMulti,"A snoop reload and FP32 B");snoop(d,true);auto e=run(d,{32,128,true,4,0,false});require(e.aBeats==1024&&e.bBeats==128&&e.aMulti&&!e.bMulti,"launch flush reload");for(unsigned f=1;f<=4;f++){reset(d);run(d,{32,128,true,10+f,f,false});}d.final();std::printf("PASS 8 owner protocol cases; synthetic Matrix payload, no DMA/TileSumBridge/arithmetic/full4096 qualification\n");return 0;}catch(const std::exception&e){std::fprintf(stderr,"FAIL owner protocol: %s\n",e.what());return 1;}}
