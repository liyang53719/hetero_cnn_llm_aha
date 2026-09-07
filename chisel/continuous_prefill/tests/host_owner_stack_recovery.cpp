// SPDX-License-Identifier: Apache-2.0
// Cross-layer fault/recovery on ONE unchanged HostBlockTop instance.
#define main retained_single_request_main
#include "host_block_commands.cpp"
#undef main

int main(int argc,char**argv) {
 try {
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  check(argc==6,"FIXTURE NEW_OUTPUT MODE GLOBAL_PC SEED");
  const std::filesystem::path fixture=argv[1],out=argv[2];
  const std::string mode=argv[3];const unsigned pc=std::stoul(argv[4]);
  const uint32_t seed=uint32_t(std::stoul(argv[5]));
  check(H==64&&F==128&&LAYERS==3&&TOKENS==33,"frozen three-layer tiny33 scope");
  check(pc>=21&&pc<COMMANDS,"fault must be after layer zero");
  check(mode=="descriptor-read-error"||mode=="read-error"||mode=="last-write-error","unsupported fault mode");
  check(!std::filesystem::exists(out),"preserve old recovery evidence");
  auto object=std::make_unique<Test>(mode,out/"failed");auto& t=*object;
  t.faultTargetPc=pc;t.rng=seed;t.initialize(fixture);
  std::cout<<"STACK_FAULT_BEGIN global_pc="<<pc<<" mode="<<mode<<std::endl;
  t.launch(); // Includes exact prior-completion prefix and reset-required lockout.
  const unsigned local=pc%21,prior=(local>=10&&local<=12)?pc-local+10:pc;
  check(t.successful==prior&&t.completions==prior+1&&t.injected,"fault not exercised at requested boundary");
  check(t.d.io_resetRequired&&!t.d.io_launch_ready,"missing error lockout");
  check(!t.pending.valid&&!t.aw.valid&&!t.w.valid,"fault left external response pending");

  // Reset the ACTUAL DUT; do not rebuild it or edit generated state. The next
  // request starts from external input/weights only, never an intermediate Y.
  t.running=false;t.d.io_launch_valid=0;t.d.io_result_ready=0;t.d.io_completion_ready=0;
  t.d.reset=1;for(unsigned i=0;i<6;i++)t.step();t.d.reset=0;
  for(unsigned i=0;i<4;i++)t.step();
  t.pending={};t.aw={};t.w={};
  t.reads=t.writes=t.ackReads=t.ackWrites=t.metadata=t.stalls=t.delays=t.checked=t.cycles=0;
  t.completions=t.successful=0;t.published.fill(false);t.writeBytes.fill(0);t.readBeats.fill(0);
  for(size_t i=t.pos(SCRATCH);i<t.mem.size();i++){t.mem[i]=0x7fc00001;t.initialized[i]=0;}
  t.mode="pass";t.errorPc=-1;t.injected=false;t.requestEpoch=2;t.rng=seed+1;
  t.inputSalt=0;t.weightSalt=0;t.out=out/"recovered";
  std::filesystem::create_directories(t.out);t.initialize(fixture);
  std::cout<<"STACK_RECOVERY_BEGIN epoch=2 layers="<<LAYERS<<std::endl;
  t.launch();
  check(t.successful==COMMANDS&&t.completions==COMMANDS,"incomplete recovery graph");
  check(t.d.io_issuedJobs==19*LAYERS&&t.checked==123552,"incomplete recovery numerical work");
  check(!t.d.io_resetRequired&&t.d.io_launch_ready,"DUT did not return to ready");
  std::cout<<"HOST_STACK_RECOVERY_PASS mode="<<mode<<" global_pc="<<pc
   <<" prior_completed="<<prior<<" layers="<<LAYERS<<" tokens="<<TOKENS
   <<" recovered_commands="<<COMMANDS<<" recovered_jobs="<<19*LAYERS
   <<" recovered_values="<<t.checked<<" reset_between_requests=1 same_dut=1 host_intermediate_writes=0"<<std::endl;
  return 0;
 } catch(const std::exception&e){std::cerr<<"HOST_STACK_RECOVERY_FAIL: "<<e.what()<<std::endl;return 1;}
}
