// SPDX-License-Identifier: Apache-2.0
// Test-only AXI service/driver. Same physical Matrix4096/iDMA DUT throughout.
#define main original_host_block_main
#include "host_block_commands.cpp"
#undef main

static void prepareNext(Test& t,const std::filesystem::path& fixture,
                        const std::filesystem::path& output,bool reset,
                        unsigned inputSalt,unsigned weightSalt){
  check(!t.pending.valid&&!t.aw.valid&&!t.w.valid,"memory service not drained");
  check(!t.arHeld&&!t.awHeld&&!t.wHeld,"request offer still active");
  t.running=false;t.d.io_launch_valid=0;t.d.io_result_ready=0;t.d.io_completion_ready=0;
  if(reset){t.d.reset=1;for(unsigned i=0;i<6;i++)t.step();t.d.reset=0;for(unsigned i=0;i<4;i++)t.step();}
  check(!t.d.reset&&!t.d.io_resetRequired&&t.d.io_launch_ready,"DUT is not ready for a new cold request");
  t.reads=t.writes=t.ackReads=t.ackWrites=t.metadata=t.stalls=t.delays=t.checked=t.cycles=0;
  t.completions=t.successful=0;t.published.fill(false);t.writeBytes.fill(0);t.readBeats.fill(0);
  for(size_t i=t.pos(SCRATCH);i<t.mem.size();i++){t.mem[i]=0x7fc00001;t.initialized[i]=0;}
  t.mode="pass";t.errorPc=-1;t.injected=false;t.requestEpoch=2;t.inputSalt=inputSalt;t.weightSalt=weightSalt;t.rng=9090801;
  t.out=output;std::filesystem::create_directories(output);t.initialize(fixture);
}
int main(int argc,char**argv){try{
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  check(argc==5,"FIXTURE NEW_OUTPUT MODE PC");
  check(OWNER_MATRIX_MACS==4096&&OWNER_WEIGHT_READ_BEATS==16&&H==64&&F==128&&TOKENS==16&&LAYERS==2,"fixed burst tiny16 two-layer scope");
  const std::filesystem::path fixture=argv[1],out=argv[2];const std::string mode=argv[3];unsigned pc=std::stoul(argv[4]);
  check(!std::filesystem::exists(out),"preserve prior evidence");
  check(mode=="repeat"||mode=="descriptor-read-error"||mode=="read-error"||mode=="weight-mid-error"||mode=="weight-last-error"||mode=="last-write-error","unsupported lifecycle mode");
  check(pc>=21&&pc<42,"second-layer fault target");
  auto instance=std::make_unique<Test>(mode=="repeat"?"pass":mode,out/"first");Test&t=*instance;
  t.faultTargetPc=pc;t.initialize(fixture);t.launch();
  const auto firstTransfers=t.d.io_idmaTransfers;const auto firstX=t.hashRange(A_X,uint64_t(TOKENS)*H*4);
  const auto firstW=t.hashRange(A_WQ,uint64_t(H)*H*4);
  if(mode=="repeat"){
    check(t.checked==39936&&t.completions==42&&t.successful==42,"incomplete first request");
    const auto firstY=t.hashRange(OUTPUTS.back().address,uint64_t(TOKENS)*H*4);
    prepareNext(t,fixture,out/"second",false,5,11);
    check(t.d.io_idmaTransfers==firstTransfers&&!t.d.reset,"DUT reset or reconstructed between requests");
    check(t.hashRange(A_X,uint64_t(TOKENS)*H*4)!=firstX&&t.hashRange(A_WQ,uint64_t(H)*H*4)!=firstW,"cold request did not change inputs and weights");
    t.launch();
    check(t.d.io_idmaTransfers>firstTransfers&&t.checked==39936&&t.successful==42&&t.completions==42&&t.d.io_issuedJobs==38,"second graph incomplete");
    check(t.d.io_result_bits_epoch==2&&t.d.io_launch_ready&&!t.d.io_resetRequired,"second request state");
    check(t.hashRange(OUTPUTS.back().address,uint64_t(TOKENS)*H*4)!=firstY,"second request reused cached old result");
    std::cout<<"WEIGHT_BURST_REPEAT_PASS requests=2 commands=84 checked_fp32=79872 bit_differences=0 same_dut=1 reset_between_requests=0 changed_weights=1 changed_input=1 mailbox_bytes=1024"<<std::endl;
  }else{
    unsigned prior=(pc%21>=10&&pc%21<=12)?pc-pc%21+10:pc;
    check(t.injected&&t.successful==prior&&t.completions==prior+1&&t.d.io_resetRequired&&!t.d.io_launch_ready,"failed producer published or escaped quarantine");
    prepareNext(t,fixture,out/"recovered",true,0,0);t.launch();
    check(t.checked==39936&&t.completions==42&&t.successful==42&&t.d.io_issuedJobs==38&&!t.d.io_resetRequired,"incomplete recovered graph");
    std::cout<<"WEIGHT_BURST_RECOVERY_PASS mode="<<mode<<" pc="<<pc<<" prior="<<prior<<" commands=42 checked_fp32=39936 bit_differences=0 same_dut=1 reset_after_error=1"<<std::endl;
  }
  return 0;
}catch(const std::exception&e){std::cerr<<"WEIGHT_BURST_LIFECYCLE_FAIL: "<<e.what()<<std::endl;return 1;}}
