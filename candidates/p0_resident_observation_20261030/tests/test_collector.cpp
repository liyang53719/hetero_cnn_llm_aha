#include "../driver/resident_observation.hpp"
#include <iostream>
using namespace resident_observation;
template<class F>void fails(F f){bool bad=false;try{f();}catch(const std::runtime_error&){bad=true;}require(bad,"negative test unexpectedly accepted");}
Beat sample(){Beat b;b.profile=0;b.identity=0x10011;b.gateTag=0x10010;b.upTag=0x10011;b.actTag=0x10012;b.rows=128;b.cols=160;for(auto& v:b.value)v=0x3f800000;return b;}
int main(int argc,char** argv){
 require(argc==2,"test output dir");auto b=sample();
 {Collector c(0,1,21);fails([&]{c.close(true);});fails([&]{c.write(argv[1]);});}
 {Collector c(0,1,21);c.capture(b,18,true,false);fails([&]{c.capture(b,18,true,false);});}
 for(unsigned mode=0;mode<9;mode++){Collector c(0,1,21);auto x=b;
  if(mode==0)x.index=1280;if(mode==1)x.ng=8960;if(mode==2)x.slot=2;if(mode==3)x.profile=1;
  if(mode==4)x.gateTag=0x20010;if(mode==5)x.identity++;if(mode==6)x.cols=32;
  if(mode==7)x.value[0]=0x7f800000;if(mode==8)x.ng=1;
  fails([&]{c.capture(x,18,true,false);});}
 {Collector c(0,1,21);fails([&]{c.capture(b,17,true,false);});fails([&]{c.capture(b,18,false,false);});fails([&]{c.capture(b,18,true,true);});}
 {Collector c(1,1,21);fails([&]{c.capture(b,18,true,false);});c.close(true);}
 Collector c(0,1,21);
 // Synthetic deterministic bit patterns test full bijection, not hardware numerics.
 for(unsigned ng=0;ng<8960;ng+=160)for(unsigned i=0;i<1280;i++)for(unsigned s=0;s<2;s++){
  b.ng=ng;b.index=i;b.slot=s;for(unsigned l=0;l<16;l++)b.value[l]=0x3f000000+(((i/160)*16+l)*8960+ng+i%160)+s*0x200000;
  c.capture(b,18,true,false);
 }
 require(c.count()==143360,"exact beat count");fails([&]{c.close(false);});c.close(true);c.write(argv[1]);fails([&]{c.capture(b,18,true,false);});
 std::cout<<"PASS_SYNTHETIC_COLLECTOR_ONLY_NO_HARDWARE_EXECUTION\n";
}
