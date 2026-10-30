#include "../driver/moe_raw_score_observation.hpp"
#include <cassert>
using namespace moe_raw_score_observation;
template<class F> void rejects(F f){bool threw=false;try{f();}catch(const std::runtime_error&){threw=true;}assert(threw);}
Beat beat(unsigned p,unsigned t,unsigned e,unsigned k=0,unsigned rank=0){Beat b;b.profile=p;b.transactionId=99;b.ownerSequence=7;b.token=t;b.expert=e;b.score=0x3f000000-e*1024;b.kind=k;b.rank=rank;b.last=k&&rank==7;return b;}
void input(Collector& c,unsigned p,unsigned t){for(unsigned e=0;e<256;e++)c.capture(beat(p,t,e),true,false);}
int main(int argc,char** argv){
 assert(argc==2);std::filesystem::path dir=argv[1];
 for(unsigned p=0;p<5;p++){
  Collector c(p);
  if(p<3){rejects([&]{c.capture(beat(p,0,0),true,false);});c.close(true);continue;}
  rejects([&]{c.capture(beat(p,0,0),false,false);});rejects([&]{c.capture(beat(p,0,0),true,true);});
  for(unsigned t=0;t<128;t++){
   input(c,p,t);rejects([&]{c.close(true);});
   for(unsigned rank=0;rank<8;rank++)c.capture(beat(p,t,rank,1,rank),true,false);
  }
  assert(c.count()==32768&&c.selectedCount()==1024);c.close(true);
  rejects([&]{c.capture(beat(p,127,7,1,7),true,false);});
  auto out=dir/std::to_string(p);std::filesystem::create_directory(out);c.write(out);
  assert(std::filesystem::file_size(out/"router_selection_scores.fp32.actual.bin")==131072);
  assert(std::filesystem::file_size(out/"router_selected_scores.fp32.actual.bin")==4096);
  assert(std::filesystem::file_size(out/"router_selected_ids.u32.actual.bin")==4096);
  rejects([&]{c.write(out);});
 }
 Collector c(3);input(c,3,0);
 auto b=beat(3,0,0,1,0);
 b=beat(3,0,0,1,0);b.last=1;rejects([&]{c.capture(b,true,false);});
 b=beat(3,0,0,1,0);b.rank=1;rejects([&]{c.capture(b,true,false);});
 b=beat(3,0,0,1,0);b.transactionId++;rejects([&]{c.capture(b,true,false);});
 b=beat(3,0,0,1,0);b.kind=2;rejects([&]{c.capture(b,true,false);});

 c.capture(beat(3,0,0,1,0),true,false);b=beat(3,0,0,1,1);rejects([&]{c.capture(b,true,false);});
 rejects([&]{c.capture(beat(3,1,0),true,false);});
 // Clean complete protocol with numerically wrong actual output MUST dump it.
 Collector wrong(3);
 const uint32_t errors[]={0x3e800000,0x7fc00001,0x7f800000,0xbf800000,0x80000000,0x00000000};
 for(unsigned t=0;t<128;t++){
  input(wrong,3,t);
  for(unsigned rank=0;rank<8;rank++){
   b=beat(3,t,rank,1,rank);
   if(t==0&&rank<6)b.score=errors[rank]; // preserve arbitrary actual bits
   wrong.capture(b,true,false);
  }
 }
 assert(wrong.inputMismatches()==6&&wrong.nonfiniteScores()==2&&wrong.negativeScores()==1&&wrong.negativeZeroScores()==1);wrong.close(true);
 auto wdir=dir/"numeric_mismatch";std::filesystem::create_directory(wdir);wrong.write(wdir);
 std::ifstream f(wdir/"router_selected_scores.fp32.actual.bin",std::ios::binary);
 for(auto expected:errors){
  uint32_t actual=0;for(unsigned i=0;i<4;i++)actual|=uint32_t(uint8_t(f.get()))<<(8*i);
  assert(actual==expected); // no input-score backfill or NaN/Inf/negative filtering
 }
 // Arbitrary INPUT score bits likewise remain observation payload.
 Collector rawInput(3);b=beat(3,0,0);b.score=0x7fc00001;rawInput.capture(b,true,false);
 b=beat(3,0,1);b.score=0xff800000;rawInput.capture(b,true,false);assert(rawInput.nonfiniteScores()==2);
 // Tied scores with non-small-ID order remain observed, not rewritten/rejected.
 Collector ties(4);for(unsigned e=0;e<256;e++){b=beat(4,0,e);b.score=0x3f000000;ties.capture(b,true,false);}
 for(unsigned rank=0;rank<8;rank++){b=beat(4,0,100-rank,1,rank);b.score=0x3f000000;ties.capture(b,true,false);}
}
