#include "affine_readonly_memory.hpp"
#include <fstream>
#include <iostream>
using namespace stimulus;
template<class F> void rejects(F f){bool fail=false;try{f();}catch(const std::exception&){fail=true;}require(fail,"negative did not reject");}
int main(int argc,char**argv){require(argc==2,"test bytes file");auto f=std::make_shared<File>(argv[1],512);ReadOnly r;View v;v.address=4096;v.allocationBase=4096;v.allocationBytes=4096;v.sourceElementBytes=2;v.destinationElementBytes=2;v.shape={4,8};v.destinationStrides={32,2};v.sourceStrides={2,8};v.source=f;r.addView(v);unsigned checked=0;
 for(unsigned row=0;row<4;++row)for(unsigned col=0;col<8;++col)for(unsigned b=0;b<2;++b){require(r.byte(4096+row*32+col*2+b)==uint8_t(row*2+col*8+b),"transpose");++checked;}
 rejects([&]{r.byte(4096+16);});rejects([&]{r.byte(4095);});
 View z=v;z.address=4096+16;z.shape={4,8};z.transform=Transform::Zero;z.source.reset();r.addView(z);for(unsigned i=0;i<128;++i){uint8_t out[1];r.read(4096+i,out,1);++checked;}
 View e=v;e.address=8192;e.allocationBase=8192;e.destinationElementBytes=4;e.transform=Transform::Bf16ToFp32Bits;e.shape={1,16};e.destinationStrides={64,4};e.sourceStrides={32,2};r.addView(e);for(unsigned i=0;i<16;++i){require(r.byte(8192+4*i)==0&&r.byte(8192+4*i+1)==0&&r.byte(8192+4*i+2)==2*i&&r.byte(8192+4*i+3)==2*i+1,"expansion");++checked;}
 rejects([&]{auto a=v;a.destinationStrides={2,2};a.validate();});rejects([&]{auto a=v;a.sourceOffset=510;a.validate();});rejects([&]{auto a=v;a.address=UINT64_MAX-1;a.validate();});rejects([&]{auto a=v;a.sourceElementBytes=4;a.validate();});rejects([&]{auto a=v;a.transform=static_cast<Transform>(99);a.sourceElementBytes=0;a.sourceOffset=511;a.validate();});r.addView(v);rejects([&]{r.byte(4096);});
 std::cout<<"PASS_BYTE_MAPPER_ONLY checks="<<checked<<" negatives=8\n";
}
