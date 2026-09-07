// SPDX-License-Identifier: Apache-2.0
// Test harness only. Arithmetic/transport is the unchanged Chisel-emitted DUT.
#define main retained_single_request_main
#include "host_block_commands.cpp"
#undef main

int main(int argc, char** argv) {
 try {
  std::fesetround(FE_TONEAREST); Verilated::commandArgs(argc,argv);
  check(argc==6,"FIXTURE NEW_OUTPUT MODE GLOBAL_PC SEED");
  check(OWNER_MATRIX_MACS==4096 && H==64 && F==128 && TOKENS==16 && LAYERS==2,"fixed Matrix4096 tiny16 two-layer scope");
  const std::filesystem::path fixture=argv[1], out=argv[2];
  const std::string mode=argv[3]; const unsigned pc=std::stoul(argv[4]);
  const auto seed=std::stoull(argv[5]);
  check(seed>0&&seed<0xffffffffULL,"nonzero bounded seed");
  check(pc>=21&&pc<COMMANDS,"target second layer");
  check(mode=="descriptor-read-error"||mode=="read-error"||mode=="last-write-error","unsupported mode");
  check(!std::filesystem::exists(out),"preserve existing evidence");
  auto object=std::make_unique<Test>(mode,out/"failed"); auto& t=*object;
  t.faultTargetPc=pc;t.rng=uint32_t(seed);t.initialize(fixture);t.launch();
  const unsigned prior=(pc%21>=10&&pc%21<=12)?pc-pc%21+10:pc;
  check(t.injected&&t.successful==prior&&t.completions==prior+1,"exact fault prefix");
  check(t.d.io_resetRequired&&!t.d.io_launch_ready,"fault must lock out new work");
  check(!t.pending.valid&&!t.aw.valid&&!t.w.valid,"all external responses drained");
  t.running=false;t.d.io_launch_valid=0;t.d.io_result_ready=0;t.d.io_completion_ready=0;
  t.d.reset=1;for(unsigned i=0;i<6;i++)t.step();t.d.reset=0;for(unsigned i=0;i<4;i++)t.step();
  t.reads=t.writes=t.ackReads=t.ackWrites=t.metadata=t.stalls=t.delays=t.checked=t.cycles=0;
  t.completions=t.successful=0;t.published.fill(false);t.writeBytes.fill(0);t.readBeats.fill(0);
  // Legal HOST preparation after reset: poison scratch, restore external inputs.
  // No register pokes, intermediate tensors, oracle values, or DUT reconstruction.
  for(size_t i=t.pos(SCRATCH);i<t.mem.size();i++){t.mem[i]=0x7fc00001;t.initialized[i]=0;}
  t.mode="pass";t.errorPc=-1;t.injected=false;t.requestEpoch=2;t.rng=uint32_t(seed)+1;
  t.out=out/"recovered";std::filesystem::create_directories(t.out);t.initialize(fixture);t.launch();
  check(t.checked==39936&&t.successful==42&&t.completions==42&&t.d.io_issuedJobs==38,"complete recovered numerical graph");
  check(t.d.io_launch_ready&&!t.d.io_resetRequired,"ready after recovery");
  std::cout<<"MATRIX4096_RECOVERY_PASS mode="<<mode<<" pc="<<pc<<" prior="<<prior
   <<" matrix_macs=4096 tokens=16 layers=2 commands=42 owner_jobs=38 checked_fp32=39936 bit_differences=0 same_dut=1 reset_after_error=1 legacy_block_launch=0"<<std::endl;
  return 0;
 }catch(const std::exception& e){std::cerr<<"MATRIX4096_RECOVERY_FAIL: "<<e.what()<<std::endl;return 1;}
}
