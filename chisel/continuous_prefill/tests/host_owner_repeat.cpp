// SPDX-License-Identifier: Apache-2.0
// Additional test harness, not a modification to the generated DUT or its RTL.
#define main preserved_single_owner_test_main
#include "host_block_commands.cpp"
#undef main

static void refresh_reference(Test& t) {
  t.norm(A_X,A_GAMMA0,A_N0);
  t.dense(A_N0,A_WQ,A_QRAW,H,H);t.bias(A_QRAW,A_BQ,A_QR,H);t.rope(A_QR,A_Q,HEADS);
  t.dense(A_N0,A_WK,A_KRAW,H,KV);t.bias(A_KRAW,A_BK,A_KR,KV);t.rope(A_KR,A_K,KVHEADS);
  t.dense(A_N0,A_WV,A_VRAW,H,KV);t.bias(A_VRAW,A_BV,A_V,KV);
  for(size_t i=0;i<size_t(TOKENS)*KV;i++){t.refput(A_CACHE_K,i,t.get(A_K,i));t.refput(A_CACHE_V,i,t.get(A_V,i));}
  t.attention();t.dense(A_ATT,A_WO,A_O,H,H);
  for(size_t i=0;i<size_t(TOKENS)*H;i++)t.refput(A_R,i,add(t.get(A_X,i),t.get(A_O,i)));
  t.norm(A_R,A_GAMMA1,A_N1);t.dense(A_N1,A_WG,A_GATE,H,F);t.dense(A_N1,A_WU,A_UP,H,F);
  for(size_t i=0;i<size_t(TOKENS)*F;i++){
    float g=t.get(A_GATE,i),e=expneg(g),sig=1.0f/add(1.0f,e);
    sig=mul(sig,std::signbit(g)?e:1.0f);t.refput(A_ACT,i,mul(mul(sig,g),t.get(A_UP,i)));
  }
  t.dense(A_ACT,A_WD,A_DOWN,F,H);
  for(size_t i=0;i<size_t(TOKENS)*H;i++)t.refput(A_Y,i,add(t.get(A_R,i),t.get(A_DOWN,i)));
}

int main(int argc,char**argv) {
 try {
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  check(argc==3,"FIXTURE_DIR NEW_OUTPUT_DIR");check(H==64&&F==128&&TOKENS==16,"fixed tiny16 repeat scope");
  const std::filesystem::path fixture=argv[1],out=argv[2];
  check(!std::filesystem::exists(out),"preserve old repeat output");
  auto object=std::make_unique<Test>("pass",out/"first");auto& t=*object;
  t.initialize(fixture);std::cout<<"OWNER_REQUEST_BEGIN index=0 epoch=1\n";t.launch();
  const uint64_t first=t.hashRange(A_Y,TOKENS*H*4);
  check(!t.pending.valid&&!t.aw.valid&&!t.w.valid,"first request not drained");
  check(t.d.io_launch_ready&&!t.d.io_resetRequired&&!t.d.reset,"DUT not quiescent");
  const uint64_t dmaBase=t.d.io_idmaTransfers;
  const uint64_t accepted0=t.d.io_memoryAccepted_0,accepted1=t.d.io_memoryAccepted_1;
  const uint64_t returned0=t.d.io_memoryReturned_0,returned1=t.d.io_memoryReturned_1;
  // Clear HOST bookkeeping and scratch at a legal idle boundary, not DUT state.
  t.running=false;t.reads=t.writes=t.ackReads=t.ackWrites=t.metadata=0;
  t.stalls=t.delays=t.checked=t.cycles=0;t.completions=t.successful=0;
  t.published.fill(false);t.writeBytes.fill(0);t.readBeats.fill(0);
  for(size_t i=t.pos(SCRATCH);i<t.mem.size();i++){t.mem[i]=0x7fc00001;t.initialized[i]=0;}
  t.out=out/"second_preparation";std::filesystem::create_directories(t.out);
  t.initialize(fixture); // Legal external input/weight setup only; scratch remains poisoned.
  for(size_t i=0;i<size_t(TOKENS)*H;i++)t.put(A_X,i,add(t.get(A_X,i),float(int(i%5)-2)*0.125f));
  refresh_reference(t); // Oracle is separate from DDR and runs BEFORE launch.
  t.out=out/"second";std::filesystem::create_directories(t.out);
  t.dump("host_commands.bin",t.mem.data()+t.pos(COMMAND_BASE),COMMAND_LIMIT-COMMAND_BASE);
  t.dump("host_descriptors.bin",t.mem.data()+t.pos(DESC_BASE),DESC_LIMIT-DESC_BASE);
  t.dump("input_x.f32le",t.mem.data()+t.pos(A_X),TOKENS*H*4);
  t.readOnlyHash=t.hashRange(BASE,SCRATCH-BASE);
  for(unsigned i=0;i<30;i++)t.step();
  check(t.reads==0&&t.writes==0,"uncommanded second request");
  check(t.d.io_launch_ready&&!t.d.reset,"second request needs unexpected reset");
  // All launch geometry/table/permission fields are unchanged; only epoch differs.
  t.running=true;t.d.io_launch_bits_epoch=2;t.d.io_launch_valid=1;
  std::cout<<"OWNER_REQUEST_BEGIN index=1 epoch=2\n";t.step();t.d.io_launch_valid=0;
  while(!t.d.io_result_valid&&t.cycles<5000000)t.step();
  check(t.d.io_result_valid&&t.d.io_result_bits_epoch==2,"second epoch or watchdog");
  check(t.d.io_result_bits_status==0&&t.d.io_result_bits_completed==21,"second request failure");
  check(t.successful==21&&t.completions==21&&t.checked==19968&&t.d.io_issuedJobs==19,"second request incomplete");
  check(t.d.io_usefulMacs==607232&&t.d.io_executedMacs==1146880,"second request MAC count");
  check(t.d.io_writeBytes==19968*4,"second request write count");
  check(t.reads==t.ackReads&&t.writes==t.ackWrites&&t.reads+t.writes==t.d.io_idmaTransfers-dmaBase,"second DMA conservation");
  check(t.d.io_memoryAccepted_0-accepted0==t.metadata&&t.d.io_memoryReturned_0-returned0==t.metadata,"second metadata conservation");
  check(t.d.io_memoryAccepted_1-accepted1==t.reads+t.writes-t.metadata&&t.d.io_memoryReturned_1-returned1==t.reads+t.writes-t.metadata,"second payload conservation");
  check(t.metadata==COMMANDS+DESCRIPTORS&&t.hashRange(BASE,SCRATCH-BASE)==t.readOnlyHash,"second readonly or metadata error");
  const auto second=t.hashRange(A_Y,TOKENS*H*4);check(first!=second,"changed input did not affect output");
  check(!t.d.reset&&!t.d.io_resetRequired,"unexpected second reset");
  for(unsigned i=0;i<5;i++){t.step();check(t.d.io_result_valid&&t.d.io_result_bits_status==0,"second result not held");}
  t.d.io_result_ready=1;t.step();t.d.io_result_ready=0;
  std::cout<<"HOST_OWNER_REPEAT_PASS requests=2 epochs=2 host_commands=42 owner_jobs=38 checked_fp32=39936 bit_differences=0 reset_between_requests=0 changed_input=1 first_output="<<std::hex<<first<<" second_output="<<second<<std::dec<<std::endl;
  return 0;
 } catch(const std::exception& e){std::cerr<<"HOST_OWNER_REPEAT_FAIL: "<<e.what()<<std::endl;return 1;}
}
