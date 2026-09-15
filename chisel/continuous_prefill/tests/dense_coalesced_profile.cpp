// SPDX-License-Identifier: Apache-2.0
// Reuse the exact arithmetic oracle, AXI backpressure and error injector.
// This measures the actual production owner plus retained Matrix and iDMA.
#define main existing_burst_dense_test_main
#include "burst_write_dense.cpp"
#undef main
int main(int argc,char**argv){try{
 std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
 ck(argc==2,"NEW_OUTPUT");std::filesystem::path out(argv[1]);
 ck(!std::filesystem::exists(out),"preserve old outputs");std::filesystem::create_directories(out);
 auto t=std::make_unique<Test>(out);uint64_t checked=0;unsigned cases=0;
 auto run=[&](unsigned m,unsigned n,unsigned k,unsigned seed,int fault,bool native){
   checked+=t->run(m,n,k,seed,fault,native);cases++;
   auto& d=t->d;
   const uint64_t sum=d.io_profile_other+d.io_profile_activationFetch+d.io_profile_setup+d.io_profile_issue+d.io_profile_writeback+d.io_profile_weightWait+d.io_profile_matrixBackpressure;
   // The underlying test resets a failed DUT before returning; profile is then
   // intentionally zero. Success snapshots must account EVERY owner cycle.
   if(!fault){
    ck(sum==d.io_done_bits_cycles,"incomplete cycle profile");
    std::cout<<"DENSE_PROFILE m="<<m<<" n="<<n<<" k="<<k<<" native="<<native
      <<" hw_cycles="<<sum<<" useful="<<d.io_done_bits_usefulMacs
      <<" issue="<<d.io_profile_issue<<" weight_wait="<<d.io_profile_weightWait
      <<" matrix_wait="<<d.io_profile_matrixBackpressure<<" writeback="<<d.io_profile_writeback
      <<" a_fetch="<<d.io_profile_activationFetch<<" setup="<<d.io_profile_setup
      <<" other="<<d.io_profile_other<<" read_bursts="<<t->readBursts<<" read_beats="<<t->reads
      <<" write_bursts="<<t->writeBursts<<" write_beats="<<t->writes<<std::endl;
   }
 };
 run(16,1536,64,1,0,false);run(16,1536,64,1,0,true);
 run(80,256,128,2,0,false);run(80,256,128,2,0,true);
 run(81,256,128,3,0,true);run(33,544,64,4,0,true);
 run(32,1536,64,5,0,true);run(17,528,128,6,0,false);
 run(1,16,16,7,0,false);
 run(80,256,64,8,1,true);run(80,256,64,9,0,true);
 run(16,544,32,10,2,true);run(16,544,32,11,0,true);
 t->actual.flush();t->reference.flush();ck(t->actual.good()&&t->reference.good(),"output write failure");
 std::cout<<"DENSE_COALESCED_PROFILE_PASS cases="<<cases<<" numeric_cases=11 fault_resets=2 checked_fp32="<<checked
   <<" bit_differences=0 real_idma=1 physical_mac=4096 same_dut=1\n";
 return 0;
}catch(const std::exception&e){std::cerr<<"DENSE_COALESCED_PROFILE_FAIL: "<<e.what()<<std::endl;return 1;}}
