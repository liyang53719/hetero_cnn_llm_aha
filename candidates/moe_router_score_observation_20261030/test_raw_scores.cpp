#include "driver/moe_raw_score_observation.hpp"
#include <cassert>
using namespace moe_raw_score_observation;
template<class F> void rejects(F f){bool threw=false;try{f();}catch(const std::runtime_error&){threw=true;}assert(threw);}
int main(){
 for(unsigned p=0;p<5;p++){
  Collector c(p);Beat b;b.profile=p;b.transactionId=999;b.ownerSequence=7;b.score=0x3b800000;
  if(p<3){rejects([&]{c.capture(b,true,false);});c.close(true);continue;}
  rejects([&]{c.close(true);});rejects([&]{c.capture(b,false,false);});rejects([&]{c.capture(b,true,true);});
  for(unsigned i=0;i<32768;i++){b.token=i/256;b.expert=i%256;c.capture(b,true,false);}
  rejects([&]{c.capture(b,true,false);});assert(c.count()==32768);c.close(true);rejects([&]{c.capture(b,true,false);});
 }
 Collector c(3);Beat b;b.profile=3;b.score=0x3b800000;c.capture(b,true,false);
 rejects([&]{c.capture(b,true,false);});b.expert=1;b.transactionId=4;rejects([&]{c.capture(b,true,false);});
 b.transactionId=0;b.score=0x7fc00000;rejects([&]{c.capture(b,true,false);});
}
