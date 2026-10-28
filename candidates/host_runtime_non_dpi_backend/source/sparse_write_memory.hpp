// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "affine_readonly_memory.hpp"
#include <array>
#include <map>
namespace stimulus {
// AXI memory only. commitBeat must be called after the corresponding real B handshake.
// The caller owns transaction/ACK identity; this class does not emulate a producer.
class SparseWrites {
 struct Range{uint64_t base,end;};
 struct Beat{std::array<uint8_t,64> bytes{};uint64_t valid=0;};
 std::vector<Range> ranges;std::map<uint64_t,Beat> beats;size_t maxBeats;
 bool admitted(uint64_t address,uint64_t bytes)const{for(const auto& r:ranges)if(address>=r.base&&address<r.end&&bytes<=r.end-address)return true;return false;}
 public:
 explicit SparseWrites(size_t limit):maxBeats(limit){require(limit>0&&limit<=8388608,"sparse budget");}
 void addRange(uint64_t base,uint64_t bytes){require(base%64==0&&bytes>0&&bytes%64==0,"RW range alignment");auto end=add(base,bytes);for(const auto& r:ranges)require(end<=r.base||base>=r.end,"RW overlap; merge only independently verified aliases first");ranges.push_back({base,end});}
 void commitBeat(uint64_t address,const uint8_t* data,uint64_t strobe){require(data&&address%64==0&&admitted(address,64),"RW B ACK range");if(!strobe)return;auto it=beats.find(address);if(it==beats.end()){require(beats.size()<maxBeats,"RW memory budget exceeded");it=beats.emplace(address,Beat{}).first;}for(unsigned i=0;i<64;++i)if((strobe>>i)&1){it->second.bytes[i]=data[i];it->second.valid|=uint64_t(1)<<i;}}
 uint8_t byte(uint64_t address)const{require(admitted(address,1),"RW guard/unmapped byte");auto it=beats.find(address&~uint64_t(63));auto bit=address&63;require(it!=beats.end()&&((it->second.valid>>bit)&1),"RW read before actual producer B ACK");return it->second.bytes[bit];}
 void read(uint64_t address,uint8_t* out,size_t n)const{require(out&&n>0&&n<=4096,"bounded RW read");add(address,n);for(size_t i=0;i<n;++i)out[i]=byte(address+i);}
 size_t allocatedBeats()const{return beats.size();}
};
}
