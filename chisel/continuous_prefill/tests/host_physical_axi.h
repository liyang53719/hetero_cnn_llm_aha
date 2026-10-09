// SPDX-License-Identifier: Apache-2.0
// Burst-capable physical DDR test service. The policy owns address admission;
// only successful AXI B acknowledgements mutate this single physical store.
#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace host_test {
inline void require(bool ok, const std::string& reason) { if (!ok) throw std::runtime_error(reason); }
struct Beat {
  bool valid=false, write=false, error=false, last=true, final=false;
  uint64_t address=0, id=0, mask=0;
  unsigned delay=0, total=1, remaining=1;
  std::array<uint32_t,16> data{};
};
struct PhysicalMemory {
  uint64_t base, limit;
  std::vector<uint32_t> words;
  PhysicalMemory(uint64_t b,uint64_t l):base(b),limit(l) {
    require(b<l && b%64==0 && l%64==0 && l-b<=64*1024*1024,"physical DDR geometry");
    words.assign((l-b)/4,0xa55ac33cU);
  }
  size_t index(uint64_t a) const { require(a>=base && a<limit && a%4==0,"physical DDR address"); return (a-base)/4; }
  uint16_t half(uint64_t a) const { return uint16_t(words[index(a&~uint64_t(3))]>>((a&2)*8)); }
};
template<class DUT,class Policy> class PhysicalAxi {
 public:
  DUT& d; Policy& owner; PhysicalMemory& mem;
  Beat pending, aw, heldAr, heldAw, heldW;
  std::vector<Beat> collected, committing;
  bool arHeld=false,awHeld=false,wHeld=false;
  uint32_t rng=91827;
  uint64_t ticks=0,readBeats=0,readAcks=0,writeBeats=0,writeAcks=0,readBursts=0,writeBursts=0;
  PhysicalAxi(DUT& dut,Policy& policy,PhysicalMemory& memory):d(dut),owner(policy),mem(memory){}
  unsigned random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  static bool equal(const Beat&a,const Beat&b){return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data&&a.total==b.total&&a.last==b.last;}
  bool drained()const{return !pending.valid&&!aw.valid&&collected.empty()&&committing.empty();}
  void clearCounts(){require(drained(),"reset with DDR transaction");readBeats=readAcks=writeBeats=writeAcks=readBursts=writeBursts=0;}
  void step(){
    d.clock=0; owner.drive();
    d.io_axi_ar_ready=!pending.valid&&!aw.valid&&collected.empty()&&random()%4!=0;
    d.io_axi_aw_ready=!pending.valid&&!aw.valid&&random()%3!=0;
    d.io_axi_w_ready=!pending.valid&&collected.size()<16&&random()%4!=0;
    d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;
    d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;
    d.io_axi_r_bits_id=pending.id;d.io_axi_r_bits_resp=pending.error?2:0;d.io_axi_r_bits_last=pending.remaining==1;
    d.io_axi_b_bits_id=pending.id;d.io_axi_b_bits_resp=pending.error?2:0;
    for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];
    d.eval();
    bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
    bool ack=(d.io_axi_r_valid&&d.io_axi_r_ready)||(d.io_axi_b_valid&&d.io_axi_b_ready);
    Beat address,data,read;
    if(d.io_axi_ar_valid){read.valid=true;read.address=d.io_axi_ar_bits_addr;read.id=d.io_axi_ar_bits_id;read.total=read.remaining=d.io_axi_ar_bits_len+1;
      require(read.total<=16&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1&&((read.address&4095)+64*read.total)<=4096,"AR fields");
      if(arHeld)require(equal(read,heldAr),"AR changed while blocked");heldAr=read;arHeld=!ar;
    }else require(!arHeld,"AR withdrawn");
    if(d.io_axi_aw_valid){address.valid=true;address.address=d.io_axi_aw_bits_addr;address.id=d.io_axi_aw_bits_id;address.total=address.remaining=d.io_axi_aw_bits_len+1;
      require(address.total<=16&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1&&((address.address&4095)+64*address.total)<=4096,"AW fields");
      if(awHeld)require(equal(address,heldAw),"AW changed while blocked");heldAw=address;awHeld=!af;
    }else require(!awHeld,"AW withdrawn");
    if(d.io_axi_w_valid){data.valid=true;data.write=true;data.mask=d.io_axi_w_bits_strb;data.last=d.io_axi_w_bits_last;
      for(unsigned i=0;i<16;i++)data.data[i]=d.io_axi_w_bits_data[i];
      if(wHeld)require(equal(data,heldW),"W changed while blocked");heldW=data;wHeld=!wf;
    }else require(!wHeld,"W withdrawn");
    owner.traffic(address.valid||data.valid||read.valid);
    if(af){aw=address;writeBursts++;}if(wf)collected.push_back(data);
    Beat next;
    if(aw.valid&&collected.size()==aw.total){require(!pending.valid&&!ar,"overlapping AXI transactions");next=collected.back();next.address=aw.address;next.id=aw.id;next.total=next.remaining=aw.total;
      for(unsigned i=0;i<aw.total;i++){require(collected[i].last==(i+1==aw.total),"WLAST mismatch");collected[i].address=aw.address+i*64;owner.writeCheck(collected[i]);}
      committing=collected;collected.clear();aw={};writeBeats+=next.total;
    }else if(ar){require(!pending.valid,"overlap AR");next=read;owner.readCheck(next);readBursts++;readBeats+=read.total;}
    if(next.valid){require(next.address%64==0&&next.address>=mem.base&&next.address+next.total*64<=mem.limit,"AXI physical bounds");next.delay=1+random()%7;
      if(!next.write)for(unsigned i=0;i<16;i++)next.data[i]=mem.words[mem.index(next.address)+i];
      owner.request(next);if(next.final)next.delay=53;
    }
    owner.observe();
    d.clock=1;d.eval();ticks++;
    if(ack){
      if(pending.write){writeAcks+=pending.total;
        if(!pending.error)for(const auto&w:committing)for(unsigned i=0;i<16;i++)mem.words[mem.index(w.address)+i]=w.data[i];
        owner.acknowledged(pending);committing.clear();
      }else {readAcks++;owner.readAcknowledged(pending);}
      if(!pending.write&&pending.remaining>1){pending.address+=64;pending.remaining--;pending.delay=1+random()%7;
        for(unsigned i=0;i<16;i++)pending.data[i]=mem.words[mem.index(pending.address)+i];
      }else pending={};
    }
    if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;
    d.clock=0;d.eval();
  }
};
} // namespace host_test
