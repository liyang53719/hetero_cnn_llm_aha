#include "sparse_memory.hpp"
#include <cassert>
#include <iostream>
template<class F>void rejects(F f){bool caught=false;try{f();}catch(const std::exception&){caught=true;}if(!caught)throw std::runtime_error("expected rejection");}
int main(){
 SparseHostMemory m;const uint64_t high=uint64_t(1)<<37;std::array<uint8_t,64>d{};d.fill(0x25);
 rejects([&]{m.read64(high);});if(m.page_count()!=0)return 1;
 m.write64(high,d,~uint64_t(0));if(m.read64(high)!=d||m.page_count()!=1)return 2;
 m.write64(high+64,d,1);rejects([&]{m.read64(high+64);});
 m.load_readonly(0x10000,std::vector<uint8_t>(64,0x3a));
 rejects([&]{m.write64(0x10000,d,1);});if(m.read64(0x10000)[0]!=0x3a)return 3;
 rejects([&]{m.load_readonly(0x10000,std::vector<uint8_t>(64));});
 rejects([&]{m.load_readonly(UINT64_MAX-1,std::vector<uint8_t>(64));});
 rejects([&]{m.read64(high+1);});m.write64(high+4096,d,0);if(m.page_count()!=2)return 4;
 std::cout<<"PASS sparse memory host-only: high-address, uninitialized read, byte mask, readonly, overflow, alignment\n";
}
