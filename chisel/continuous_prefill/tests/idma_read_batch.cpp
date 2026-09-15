// SPDX-License-Identifier: Apache-2.0
// Actual unchanged iDMA backend. Original memory latency and commit-tail checks.
#define main retained_commit_tail_main
#include "idma_commit_tail.cpp"
#undef main
int main(int argc,char**argv){try{
 Verilated::commandArgs(argc,argv);auto t=std::make_unique<Test>();unsigned seed=1;
 for(unsigned n:{1,2,15,16,17,31,32,33,48,63,64})t->stream(n,4096-n*64,seed++);
 for(int f:{1,2,3}){t->stream(64,4096,seed++,f);t->stream(64,4096,seed++);}
 t->legacy();
 // Compare four old-size transactions with one batch, on the same DUT and
 // with the exact same external AXI model. No time or idle cycles are excluded.
 t->rng=512;auto old=t->cycles;
 for(unsigned i=0;i<4;i++)t->stream(16,8192+i*1024,100+i);
 auto oldCycles=t->cycles-old;t->rng=512;auto cur=t->cycles;t->stream(64,8192,104);
 auto newCycles=t->cycles-cur;
 std::cout<<"IDMA_READ_BATCH_PASS stream_cases=22 error_resets=3 legacy_cases=1 real_idma=1 old_transfers=4 batch_transfers=1 old_cycles="<<oldCycles<<" batch_cycles="<<newCycles<<" final_commit_only=1"<<std::endl;
 return 0;
}catch(const std::exception&e){std::cerr<<"IDMA_READ_BATCH_FAIL: "<<e.what()<<std::endl;return 1;}}
