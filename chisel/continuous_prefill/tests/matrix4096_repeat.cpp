// SPDX-License-Identifier: Apache-2.0
// Test-only driver: two cold two-layer requests on ONE real 4096-MAC/iDMA DUT.
#define main retained_single_request_main
#include "host_block_commands.cpp"
#undef main
int main(int argc,char**argv){try{
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  check(argc==3,"FIXTURE NEW_OUTPUT");
  check(OWNER_MATRIX_MACS==4096&&H==64&&F==128&&TOKENS==16&&LAYERS==2,"fixed tiny16 two-layer repeat scope");
  const std::filesystem::path fixture=argv[1],out=argv[2];
  check(!std::filesystem::exists(out),"preserve old output");
  auto object=std::make_unique<Test>("pass",out/"first");auto& t=*object;
  t.initialize(fixture);t.launch();
  check(t.checked==39936&&t.successful==42&&t.completions==42,"first request incomplete");
  const auto oldDma=t.d.io_idmaTransfers;
  const auto x0=t.hashRange(A_X,uint64_t(TOKENS)*H*4);
  const auto y0=t.hashRange(OUTPUTS.back().address,uint64_t(TOKENS)*H*4);
  const auto wq0=t.hashRange(A_WQ,uint64_t(H)*H*4);
  check(!t.pending.valid&&!t.aw.valid&&!t.w.valid,"previous request not drained");
  check(t.d.io_launch_ready&&!t.d.io_resetRequired&&!t.d.reset,"DUT not idle after success");
  // Clear only the HOST memory service accounting, and poison the next cold
  // request's scratch. No reset, internal register pokes, or golden DDR writes.
  t.running=false;t.reads=t.writes=t.ackReads=t.ackWrites=t.metadata=t.stalls=t.delays=t.checked=t.cycles=0;
  t.completions=t.successful=0;t.published.fill(false);t.writeBytes.fill(0);t.readBeats.fill(0);
  for(size_t i=t.pos(SCRATCH);i<t.mem.size();i++){t.mem[i]=0x7fc00001;t.initialized[i]=0;}
  t.requestEpoch=2;t.inputSalt=5;t.weightSalt=11;t.rng=9090711;
  t.out=out/"second";std::filesystem::create_directories(t.out);t.initialize(fixture);
  check(t.hashRange(A_X,uint64_t(TOKENS)*H*4)!=x0,"unchanged second input");
  check(t.hashRange(A_WQ,uint64_t(H)*H*4)!=wq0,"unchanged second weight");
  check(t.d.io_idmaTransfers==oldDma&&!t.d.reset,"DUT recreated or reset at request boundary");
  t.launch();
  check(!t.d.reset&&!t.d.io_resetRequired&&t.d.io_launch_ready,"second request not clean");
  check(t.d.io_idmaTransfers>oldDma&&t.d.io_result_bits_epoch==2,"counter or epoch not preserved");
  check(t.checked==39936&&t.successful==42&&t.completions==42&&t.d.io_issuedJobs==38,"second request incomplete");
  const auto y1=t.hashRange(OUTPUTS.back().address,uint64_t(TOKENS)*H*4);
  check(y0!=y1,"second request did not transform changed stimulus");
  std::cout<<"MATRIX4096_REPEAT_PASS requests=2 tokens=16 layers_per_request=2 commands=84 checked_fp32=79872 bit_differences=0 same_dut=1 reset_between_requests=0 changed_input=1 changed_weights=1 legacy_block_launch=0 first_output="<<std::hex<<y0<<" second_output="<<y1<<std::dec<<std::endl;
  return 0;
}catch(const std::exception& e){std::cerr<<"MATRIX4096_REPEAT_FAIL: "<<e.what()<<std::endl;return 1;}}
