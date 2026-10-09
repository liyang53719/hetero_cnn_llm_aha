// SPDX-License-Identifier: Apache-2.0
// Bounded unit-test mock only. Never a production model or numerical evidence.
#include "VHostBlockTop.h" // Generated minimal declarations in the test tempdir.
#include "host_attention_block_prefix.h"
#include <iostream>
#include <thread>
static constexpr uint64_t base=0x100000000ULL;
struct SyntheticDut:VHostBlockTop {
  unsigned stage=0,sent=0,received=0,cycles=0,evaluations=0;
  bool previousClock=false,addressAccepted=false,enabled=false,readPerturb=false,writePerturb=false,slow=false,failLow=false;
  void eval() {
    ++evaluations;
    if(slow)std::this_thread::sleep_for(std::chrono::microseconds(10));
    if(failLow&&evaluations==111*3)throw std::runtime_error("synthetic final low eval failure");
    const bool rising=clock&&!previousClock;previousClock=bool(clock);
    if(rising){
      ++cycles;
      if(enabled){
        if(stage==0&&io_axi_ar_valid&&io_axi_ar_ready)stage=1;
        else if(stage==1&&io_axi_r_valid&&io_axi_r_ready){
          for(unsigned i=0;i<16;i++)host_test::require(io_axi_r_bits_data[i]==((0x1000+received*16+i)^unsigned(readPerturb&&received==0&&i==0)),"actual R payload");
          ++received;if(io_axi_r_bits_last){host_test::require(received==2,"RLAST");stage=2;}
        }else if(stage==2){
          if(io_axi_aw_valid&&io_axi_aw_ready)addressAccepted=true;
          if(io_axi_w_valid&&io_axi_w_ready)++sent;
          if(addressAccepted&&sent==2)stage=3;
        }else if(stage==3&&io_axi_b_valid&&io_axi_b_ready)stage=4;
      }
    }
    io_launch_ready=1;
    io_axi_ar_valid=enabled&&stage==0;io_axi_ar_bits_addr=base;
    io_axi_ar_bits_len=1;io_axi_ar_bits_size=6;io_axi_ar_bits_burst=1;io_axi_ar_bits_id=7;
    io_axi_r_ready=stage==1&&cycles>=50; // Force held R payloads.
    io_axi_aw_valid=stage==2&&!addressAccepted;io_axi_aw_bits_addr=base+128;
    io_axi_aw_bits_len=1;io_axi_aw_bits_size=6;io_axi_aw_bits_burst=1;io_axi_aw_bits_id=9;
    io_axi_w_valid=stage==2&&sent<2;io_axi_w_bits_last=sent==1;io_axi_w_bits_strb=~uint64_t(0);
    for(unsigned i=0;i<16;i++)io_axi_w_bits_data[i]=(0x9000+sent*16+i)^unsigned(writePerturb&&sent==0&&i==0);
    io_axi_b_ready=stage==3&&cycles>=110; // Final B ACK at exactly cycle 111.
  }
};
struct SyntheticPolicy {
  unsigned run=0,completions=0,successful=0,inferredCommittedLength=0,inferredCommittedGeneration=0;
  bool running=false,constructed=false;
  uint64_t metadata=0,ackBytes=0,physicalBytes=0;
  unsigned reads=0,writes=0,readResponses=0,writeResponses=0;
  host_test::PhysicalMemory& mem;
  attention_block_prefix::Recorder prefix;
  host_test::PhysicalAxi<SyntheticDut,SyntheticPolicy>* bus=nullptr;
  SyntheticPolicy(host_test::PhysicalMemory& memory,uint64_t limit):mem(memory),prefix(limit){}
  void drive(){}
  void traffic(bool){prefix.capture(*bus);}
  void readCheck(const host_test::Beat& b){host_test::require(b.address==base&&b.total==2,"read geometry");++reads;}
  void writeCheck(const host_test::Beat& b){host_test::require(b.address>=base+128&&b.address<base+256,"write geometry");++writes;}
  void request(host_test::Beat&){}
  void observe(){}
  void readAcknowledged(const host_test::Beat&){++readResponses;}
  void acknowledged(const host_test::Beat& b){
    host_test::require(b.total==2&&!b.error&&bus->committing.size()==2,"B ACK geometry");
    for(unsigned i=0;i<32;i++)host_test::require(mem.words[mem.index(base+128)+i]==((0x9000+i)^unsigned(bus->d.writePerturb&&i==0)),"store before ACK callback");
    ++writeResponses;ackBytes+=128;physicalBytes+=128;
  }
};
int main(int argc,char** argv){try{
  host_test::require(argc==4,"OUTPUT LIMIT VARIANT");
  const uint64_t limit=std::string(argv[2])=="0"?0:attention_block_prefix::cycleLimit(argv[2]);
  const std::string variant=argv[3];
  host_test::require(!std::filesystem::exists(argv[1]),"fresh mock output");std::filesystem::create_directories(argv[1]);
  SyntheticDut d;d.readPerturb=variant=="read";d.writePerturb=variant=="write";d.slow=variant=="slow";d.failLow=variant=="fail-low";
  host_test::PhysicalMemory mem(base,base+256);for(unsigned i=0;i<32;i++)mem.words[i]=(0x1000+i)^unsigned(d.readPerturb&&i==0);
  SyntheticPolicy policy(mem,limit);host_test::PhysicalAxi<SyntheticDut,SyntheticPolicy> bus(d,policy,mem);policy.bus=&bus;
  bool stopped=false;
  try{
    d.reset=1;for(unsigned i=0;i<6;i++)policy.prefix.step(bus,argv[1]);
    d.reset=0;for(unsigned i=0;i<30;i++)policy.prefix.step(bus,argv[1]);
    host_test::require(policy.prefix.memoryBytesHashed()==0,"no constructor memory traversal");
    policy.constructed=true;policy.running=true;d.enabled=true;
    for(unsigned i=36;i<(limit?limit:111);i++){
      policy.prefix.step(bus,argv[1]);
      host_test::require(policy.prefix.memoryBytesHashed()==0,"no per-cycle memory traversal");
    }
  }catch(const attention_block_prefix::PrefixStop&){stopped=true;}
  host_test::require(stopped==bool(limit)&&policy.constructed&&d.clock==0&&d.evaluations==bus.ticks*3,"stop after final low eval and construction");
  host_test::require(policy.prefix.memoryBytesHashed()==(limit?mem.words.size()*4:0),"one cap-only memory traversal; none when disabled");
  if(bus.ticks==111)host_test::require(d.stage==4&&bus.drained()&&bus.readBeats==2&&bus.readAcks==2&&bus.writeBeats==2&&bus.writeAcks==2
    &&policy.reads==1&&policy.writes==2&&policy.readResponses==2&&policy.writeResponses==1,"completed seeded AXI lifecycle");
  uint64_t memoryHash=attention_block_prefix::fnvOffset;
  for(uint32_t word:mem.words)for(unsigned i=0;i<4;i++){memoryHash^=(word>>(i*8))&255U;memoryHash*=attention_block_prefix::fnvPrime;}
  std::cout<<"{\"ticks\":"<<bus.ticks<<",\"rng\":"<<bus.rng<<",\"eval_calls\":"<<d.evaluations
    <<",\"memory_fnv1a64\":"<<memoryHash<<",\"read_beats\":"<<bus.readBeats<<",\"read_acks\":"<<bus.readAcks
    <<",\"write_beats\":"<<bus.writeBeats<<",\"write_acks\":"<<bus.writeAcks<<",\"drained\":"<<bus.drained()<<"}\n";
  return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
