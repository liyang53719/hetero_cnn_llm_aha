// SOURCE-ONLY normal_m1 translation of frozen OrderedQkBehaviorSpec r3.
// Direct top ports only. Matrix and external memory are scripted endpoints,
// not FMA models; actual ALUs/Scalar/SRAM/PackedClient stay inside unchanged SV.
#include "generated_abi.hpp"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
using U=std::uint64_t;
static void need(bool ok,const char* why) {if(!ok) throw std::runtime_error(why);}
static const char* tf(bool b) {return b?"true":"false";}
struct Reply {U tag,due;};
struct Bench {
  abi::D& d; VerilatedContext& ctx;
  static constexpr U cap=99997,q=0x100000,k=0x200000,v=0x300000,dst=0x400000;
  U cycles=0,physicalSteps=0,clockEdges=0,memAccepted=0,memReturned=0,writeBytes=0;
  U pvDue=0,pvRequests=0,pvReturns=0,steps=0,qkSteps=0,groups=0,results=0,dones=0;
  U ownerAccepts=0,allWrites=0,observations=0,targetToken=0,targetHead=0;
  bool pvPending=false,resultPending=false,donePending=false,terminal=false,jobAccepted=false,sawResultHeld=false;
  std::optional<Reply> mem;std::optional<U> group;std::set<U> stored;
  std::array<std::optional<std::vector<U>>,4> held;
  std::array<U,4> holds{{0,0,0,0}}; // memory,group,step,pv
  std::array<std::uint32_t*,4096> tile;
  Bench(abi::D& top,VerilatedContext& context):d(top),ctx(context),tile(abi::qk_tile(d)) {}
  void settle(){d.eval();need(!ctx.gotFinish(),"unexpected HDL finish/fatal");}
  void clock(){
    d.clock=0;settle();ctx.timeInc(1);
    d.clock=1;settle();++clockEdges;ctx.timeInc(1);
    d.clock=0;settle();
  }
  void hold(unsigned n,bool valid,bool ready,std::vector<U> now){
    if(held[n]) {need(valid && *held[n]==now,"stalled request changed/dropped");++holds[n];}
    if(valid && !ready)held[n]=std::move(now);else held[n].reset();
  }
  void offerTile(){
    d.io_packedQk_result_bits_context=0;d.io_packedQk_result_bits_last=1;d.io_packedQk_result_bits_error=0;
    for(unsigned row=0;row<16;++row)for(unsigned col=0;col<256;++col)
      *tile[row*256+col]=(col/16>targetToken || col%16!=row)?0x7fc00000u:0u;
  }
  void step(){
    need(cycles<cap,"100000 total-clock cap");settle();
    const U phase=d.observation_vectorPhase,selected=d.observation_selected;
    d.io_memory_ready=!mem && cycles%5!=0 && !terminal;
    d.io_response_valid=mem && mem->due<=cycles;
    if(mem){d.io_response_bits_tag=mem->tag;for(unsigned i=0;i<16;++i)d.io_response_bits_data[i]=0;d.io_response_bits_error=0;}
    d.io_matrixRequest_ready=!pvPending && cycles%3!=0 && !terminal;
    d.io_matrixResult_valid=pvPending && cycles>=pvDue;d.io_matrixResult_bits_error=0;
    d.io_matrixAcceptedSteps=physicalSteps;
    d.io_packedQk_group_ready=!group && cycles%3!=0 && !terminal;
    d.io_packedQk_step_ready=group && !resultPending && !donePending && cycles%4!=0;
    d.io_packedQk_result_valid=resultPending;d.io_packedQk_done_valid=donePending;
    d.io_packedQk_done_bits_tag=group.value_or(0);d.io_packedQk_done_bits_error=0;
    d.io_packedQkStepsDrained=steps==8;settle();
    const bool gf=d.io_packedQk_group_valid && d.io_packedQk_group_ready;
    const bool sf=d.io_packedQk_step_valid && d.io_packedQk_step_ready;
    const bool rf=d.io_packedQk_result_valid && d.io_packedQk_result_ready;
    const bool df=d.io_packedQk_done_valid && d.io_packedQk_done_ready;
    const bool mf=d.io_memory_valid && d.io_memory_ready,mr=d.io_response_valid && d.io_response_ready;
    const bool pf=d.io_matrixRequest_valid && d.io_matrixRequest_ready,pr=d.io_matrixResult_valid && d.io_matrixResult_ready;
    hold(0,d.io_memory_valid,d.io_memory_ready,abi::snapshot_memory(d));
    hold(1,d.io_packedQk_group_valid,d.io_packedQk_group_ready,abi::snapshot_group(d));
    hold(2,d.io_packedQk_step_valid,d.io_packedQk_step_ready,abi::snapshot_step(d));
    hold(3,d.io_matrixRequest_valid,d.io_matrixRequest_ready,abi::snapshot_pv(d));
    if(d.io_ownerJob_valid && d.io_ownerJob_ready){need(!jobAccepted,"duplicate owner accept");jobAccepted=true;++ownerAccepts;}
    std::optional<Reply> nextMem;std::optional<U> nextGroup;
    if(mf){
      need(!mem,"one memory debt");const U at=d.io_memory_bits_address;need(at%64==0,"aligned external memory request");
      if(d.io_memory_bits_write){
        need(at>=dst && at<=dst+6144-64,"output address");need(abi::memory_data_zero(d),"nonzero output beat");
        need(d.io_memory_bits_mask==~U(0),"full output mask");need(stored.insert(at).second,"duplicate output beat");writeBytes+=64;
      }else need((at>=q && at<=q+6144-64)||(at>=k && at<=k+1024-64)||(at>=v && at<=v+1024-64),"input address");
      nextMem=Reply{d.io_memory_bits_tag,cycles+2+cycles%3};
    }
    if(gf){need(!group,"one group debt");need(d.io_packedQk_group_bits_opcode==0x23 && d.io_packedQk_group_bits_sliceMask==255,"QK descriptor");need(d.io_packedQk_group_bits_tag>0,"nonzero QK tag");nextGroup=d.io_packedQk_group_bits_tag;}
    if(sf){need(group && steps<8,"QK step ownership/count");need(d.io_packedQk_step_bits_context==0,"QK context");
      need(bool(d.io_packedQk_step_bits_clear)==(steps==0),"QK clear");
      need(bool(d.io_packedQk_step_bits_last)==(steps==7)&&bool(d.io_packedQk_step_bits_finish)==(steps==7)&&bool(d.io_packedQk_step_bits_emit)==(steps==7),"QK last/finish/emit");need(abi::qk_operands_zero(d),"zero scripted QK operands");}
    if(pf)need(d.io_matrixRequest_bits_opcode==0x24 && d.io_matrixRequest_bits_sliceMask==1,"PV descriptor");
    if(phase){
      need(resultPending,"held real Matrix result head");
      if(!d.io_packedQk_abort){need(!d.io_packedQk_result_ready,"no early Matrix result release");sawResultHeld=true;}else need(!d.testScoreWrite_valid,"no write while abort");
      need(!d.observation_committed && !d.observation_scalarIssue,"vector commit/scalar exclusion");
      ++observations;
      std::cout<<"OBS cycle="<<cycles<<" token="<<U(d.observation_token)<<" head="<<U(d.observation_head)<<" phase="<<phase<<" lane="<<U(d.observation_lane)<<" selected="<<selected<<" faults="<<U(d.observation_faults)<<" scoreWrite="<<tf(d.testScoreWrite_valid)<<" scoreIndex="<<U(d.testScoreWrite_bits_index)<<" scoreData="<<U(d.testScoreWrite_bits_data)<<" max="<<U(d.observation_maxScore)<<" resultReady="<<tf(d.io_packedQk_result_ready)<<'\n';
    }
    if(d.testScoreWrite_valid){need(d.testScoreWrite_bits_index<=d.observation_token,"score causal index");need(d.testScoreWrite_bits_data==0,"zero expected score write");++allWrites;}
    if(terminal)need(!gf&&!sf&&!rf&&!df&&!mf&&!mr&&!pf&&!pr,"traffic after terminal");
    clock();++cycles;
    if(mr){mem.reset();++memReturned;}if(mf){mem=nextMem;++memAccepted;}
    if(pr){pvPending=false;++pvReturns;}
    if(pf){need(!pvPending,"one PV debt");pvPending=true;pvDue=cycles+2;++pvRequests;++physicalSteps;}
    if(gf){group=nextGroup;steps=0;++groups;targetToken=d.observation_token;targetHead=d.observation_head;}
    if(sf){++steps;++qkSteps;physicalSteps+=8;if(steps==8){resultPending=true;offerTile();}}
    if(rf){resultPending=false;++results;donePending=true;}
    if(df){donePending=false;group.reset();++dones;}
    settle();
  }
  void run(){
    abi::zero_inputs(d);d.reset=1;
    // Explicit replacement of framework reset1 + original explicit reset2.
    clock();clock();clock();d.reset=0;settle();
    std::cout<<"VERILATOR_CORE_SIM_READY case=normal_m1 m=1 scripted_matrix=true reset_clocks=3\n";
    step();need(d.io_ownerJob_ready,"owner ready after idle step");
    d.io_ownerJob_bits_kind=4;d.io_ownerJob_bits_m=1;d.io_ownerJob_bits_n=1536;d.io_ownerJob_bits_k=128;
    d.io_ownerJob_bits_a=q;d.io_ownerJob_bits_b=k;d.io_ownerJob_bits_c=v;d.io_ownerJob_bits_dst=dst;
    d.io_ownerJob_bits_writeBytes=6144;d.io_ownerJob_bits_tag=0x7000c;d.io_ownerJob_valid=1;
    while(!jobAccepted)step();d.io_ownerJob_valid=0;settle();
    while(!d.io_result_valid)step();
    need(!mem && memAccepted==memReturned && !pvPending && pvRequests==pvReturns,"endpoint debts at result");
    need(!group && !resultPending && !donePending && groups==dones,"packed debts at result");
    need(!d.observation_owned && !d.observation_memoryDebt && !d.observation_localDebt && !d.observation_scalarDebt,"core debts at result");
    need(d.io_result_bits_status==0 && !d.io_resetRequired,"normal result status");
    need(groups==12 && results==groups && qkSteps==96 && pvRequests==96,"M1 independent endpoint counts");
    need(holds[0]+holds[1]+holds[2]+holds[3]>0,"some actual request hold evidence");for(const auto& x:held)need(!x,"no outstanding stalled request");
    need(allWrites==12 && writeBytes==6144 && stored.size()==96 && d.io_acknowledgedWriteBytes==6144,"M1 score/output counts");
    need(memAccepted==384 && observations==408,"independent M1 memory/vector counts");
    need(sawResultHeld && jobAccepted && ownerAccepts==1,"owner/result held evidence");terminal=true;
    const auto result=abi::snapshot_result(d);
    for(unsigned i=0;i<8;++i){need(d.io_result_valid && abi::snapshot_result(d)==result,"terminal payload hold");step();}
    d.io_result_ready=1;step();d.io_result_ready=0;settle();
    for(unsigned i=0;i<3;++i){need(!d.io_result_valid,"post-terminal quiet valid");step();}
    need(clockEdges==cycles+3 && clockEdges<=100000,"physical clock edge accounting");
    std::cout<<"VERILATOR_CORE_CASE_PASS case=normal_m1 m=1 cycles="<<cycles<<" groups="<<groups<<" qkAcceptedSteps="<<qkSteps<<" accounting512Steps="<<physicalSteps<<" results="<<results<<" dones="<<dones<<" scoreWrites="<<allWrites<<" targetPrefix= ownerAccepts="<<ownerAccepts<<" pvRequests="<<pvRequests<<" pvReturns="<<pvReturns<<" requestHoldChecks="<<(holds[0]+holds[1]+holds[2]+holds[3])<<" holdChecksByPort=(group,"<<holds[1]<<"),(memory,"<<holds[0]<<"),(pv,"<<holds[3]<<"),(step,"<<holds[2]<<") memoryAccepted="<<memAccepted<<" memoryReturned="<<memReturned<<" outputBytes="<<writeBytes<<" numerical_matrix_verified=false\n";
  }
};
int main(int argc,char** argv){
  try{
    need(argc==1,"no runtime case/parameter override");
    std::cout.setf(std::ios::unitbuf); // retain phase evidence promptly; no new stimulus
    auto ctx=std::make_unique<VerilatedContext>();ctx->threads(1);ctx->randReset(0);
    auto d=std::make_unique<abi::D>(ctx.get());
    U totalEdges=0;{Bench bench(*d,*ctx);bench.run();totalEdges=bench.clockEdges;}
    d->final();need(!ctx->gotFinish(),"unexpected HDL final finish");d.reset();
    std::cout<<"VERILATOR_CORE_DONE case=normal_m1 completed=true total_rising_edges="<<totalEdges<<" reset_clocks=3\n";return 0;
  }catch(const std::exception& e){std::cerr<<"VERILATOR_CORE_FAIL "<<e.what()<<'\n';return 1;}
}
