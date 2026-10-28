#include "sparse_write_memory.hpp"
#include <iostream>
using namespace stimulus;
template<class F> void rejects(F f){bool x=false;try{f();}catch(const std::exception&){x=true;}require(x,"negative");}
int main(){SparseWrites m(2);m.addRange(0x100000000ULL,4096);std::array<uint8_t,64>b{};for(unsigned i=0;i<64;++i)b[i]=i;rejects([&]{m.byte(0x100000000ULL);});m.commitBeat(0x100000000ULL,b.data(),1);require(m.byte(0x100000000ULL)==0,"first");rejects([&]{m.byte(0x100000001ULL);});m.commitBeat(0x100000000ULL,b.data(),~uint64_t(0));for(unsigned i=0;i<64;++i)require(m.byte(0x100000000ULL+i)==i,"mask");m.commitBeat(0x100000040ULL,b.data(),~uint64_t(0));uint8_t out[66];m.read(0x10000003fULL,out,65);require(out[0]==63&&out[64]==63,"boundary");rejects([&]{m.commitBeat(0x100000080ULL,b.data(),1);});rejects([&]{m.byte(0x100001000ULL);});rejects([&]{m.addRange(0x100000000ULL,64);});std::cout<<"PASS_SPARSE_RW_BYTES_ONLY\n";}
