// SPDX-License-Identifier: Apache-2.0
// Reuse the actual AXI-only service and oracle. Never modify the generated DUT.
#define main preserved_single_owner_test_main
#include "host_block_commands.cpp"
#undef main

static void prepare_again(Test& t,const std::filesystem::path& fixture,
                          const std::filesystem::path& out,bool reset,
                          unsigned epoch,unsigned inputSalt,unsigned weightSalt) {
  check(!t.pending.valid&&!t.aw.valid&&!t.w.valid,"previous request not drained");
  t.running=false;
  if(reset){t.d.reset=1;for(unsigned i=0;i<6;i++)t.step();t.d.reset=0;t.step();}
  check(t.d.io_launch_ready&&!t.d.io_resetRequired&&!t.d.reset,"request boundary not ready");
  t.reads=t.writes=t.ackReads=t.ackWrites=t.metadata=0;
  t.stalls=t.delays=t.checked=t.cycles=0;t.completions=t.successful=0;
  t.published.fill(false);t.writeBytes.fill(0);t.readBeats.fill(0);
  t.errorPc=-1;t.injected=false;t.mode="pass";t.requestEpoch=epoch;
  t.inputSalt=inputSalt;t.weightSalt=weightSalt;
  // Only the test memory's allocation state is reinitialized at this legal idle
  // boundary. No hardware register/state or reference tensor is injected.
  for(size_t i=t.pos(SCRATCH);i<t.mem.size();i++){t.mem[i]=0x7fc00001;t.initialized[i]=0;}
  t.out=out;check(!std::filesystem::exists(out),"preserve prior lifecycle outputs");
  std::filesystem::create_directories(out);t.initialize(fixture);
}

int main(int argc,char**argv){try{
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  check(argc>=4,"FIXTURE_DIR NEW_OUTPUT repeat|FAULT [PC] [SEED]");
  const std::filesystem::path fixture=argv[1],out=argv[2];const std::string mode=argv[3];
  check(!std::filesystem::exists(out),"preserve old lifecycle output");
  const bool repeat=mode=="repeat";auto t=std::make_unique<Test>(repeat?"pass":mode,out/"first");
  t->faultTargetPc=argc>4?unsigned(std::stoul(argv[4])):1;
  if(argc>5)t->rng=uint32_t(std::stoul(argv[5]));check(t->rng!=0,"xorshift seed must be nonzero");
  t->initialize(fixture);t->launch();
  const auto firstHash=t->hashRange(A_Y,uint64_t(TOKENS)*H*4);
  const uint64_t firstCount=t->checked,firstTransfers=t->d.io_idmaTransfers;
  if(!repeat)check(t->errorPc>=0&&t->d.io_resetRequired,"fault run did not lock out");
  const auto firstInput=t->hashRange(A_X,uint64_t(TOKENS)*H*4);
  prepare_again(*t,fixture,out/"second",!repeat,2,repeat?1:0,repeat?11:0);
  t->launch();check(!t->d.reset&&!t->d.io_resetRequired,"recovery/repeat not clean");
  const auto secondHash=t->hashRange(A_Y,uint64_t(TOKENS)*H*4);
  check(t->successful==21&&t->completions==21,"second request incomplete");
  if(repeat){check(firstHash!=secondHash,"changed stimulus produced identical final tensor");
    check(firstInput!=t->hashRange(A_X,uint64_t(TOKENS)*H*4),"input did not change");
    check(t->d.io_idmaTransfers>firstTransfers,"DUT transfer counter was reset between cold requests");}
  std::cout<<"HOST_OWNER_LIFECYCLE_PASS mode="<<mode<<" tokens="<<TOKENS<<" hidden="<<H<<" ffn="<<F
    <<" requests=2 second_commands=21 second_owner_jobs=19 first_checked_fp32="<<firstCount
    <<" second_checked_fp32="<<t->checked<<" bit_differences=0 reset_between_requests="<<(!repeat)
    <<" changed_input="<<repeat<<" changed_weights="<<repeat<<" recovered=1 legacy_block_launch=0"
    <<" first_output="<<std::hex<<firstHash<<" second_output="<<secondHash<<std::dec<<std::endl;
  return 0;
 }catch(const std::exception&e){std::cerr<<"HOST_OWNER_LIFECYCLE_FAIL: "<<e.what()<<std::endl;return 1;}}
