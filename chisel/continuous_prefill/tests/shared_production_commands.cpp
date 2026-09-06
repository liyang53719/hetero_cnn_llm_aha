// SPDX-License-Identifier: Apache-2.0
// The retained block and host commands share the SAME DUT, DDR and original
// iDMA. Only input/weights/tables are preloaded. No intermediate host copies.
#define main retained_block_regression_main
#include "qwen2_block.cpp"
#undef main
#define HOST_WITH_BLOCK
#include "host_command_axi_service.h"

int main(int argc,char**argv){try{
  std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  need(argc==2,"usage: TOKENS");unsigned n=std::stoul(argv[1]);need(n>=1&&n<=MAX_TOKENS,"tokens");
  auto t=std::make_unique<BlockTest>(n,20260906);
  HostTables tab;tab.rows=n;tab.width=H;tab.dtype=7;tab.span=HostTables::align64(size_t(n)*H*4);
  tab.sourceA=t->BASE+OFF_Y;tab.sourceB=t->BASE+OFF_X;
  tab.inputBase=t->BASE;tab.inputLimit=t->BASE+ARENA_BYTES;
  tab.commandBase=tab.inputLimit;tab.descriptorBase=tab.commandBase+64;tab.tableLimit=tab.commandBase+4096;
  tab.outputBase=tab.tableLimit;tab.outputLimit=tab.outputBase+3*tab.span;
  t->memory.resize((tab.outputLimit-t->BASE)/4+16,0xa5a5a5a5U);t->initialized.resize(t->memory.size(),0);
  // Input and metadata initialization is completed before the block's launch.
  t->initialize();tab.populate(t->memory,t->initialized,t->BASE);
  t->dump("host_commands.bin",t->memory.data()+(tab.commandBase-t->BASE)/4,64);
  t->dump("host_descriptors.bin",t->memory.data()+(tab.descriptorBase-t->BASE)/4,HostTables::align64(30*16));
  std::vector<std::vector<uint32_t>> golden(3,std::vector<uint32_t>(size_t(n)*H));
  for(size_t j=0;j<size_t(n)*H;j++){
    float a=t->reference[OFF_Y/4+j],b=t->reference[OFF_X/4+j];
    for(unsigned c=0;c<3;c++){a=add(a,b);golden[c][j]=bits(a);}
  }
  t->run(); // Fifteen stages, every output checked, real original Matrix/iDMA.
  need(t->commits==15&&!t->d.io_resetRequired,"block predecessor did not commit");
  need(t->d.io_memoryAccepted_0==t->reads+t->writes&&t->d.io_memoryReturned_0==t->reads+t->writes,"block bypassed shared arbiter");
  need(t->d.io_memoryAccepted_1==0&&t->d.io_memoryAccepted_2==0,"metadata/owner active before host command launch");
  // No reset and no memory rewrite here. sourceA is the block's actual Y arena.
  HostAxiService<BlockDut> host(t->d,t->memory,t->initialized,t->BASE,tab);host.golden=golden;host.run();
  need(t->d.io_memoryAccepted_1==33&&t->d.io_memoryReturned_1==33,"metadata did not use shared port");
  need(t->d.io_memoryAccepted_2==host.payloadReads+host.writeAcks&&t->d.io_memoryReturned_2==host.payloadReads+host.writeAcks,"host data bypassed arbiter");
  need(t->d.io_idmaTransfers==t->reads+t->writes+host.readAcks+host.writeAcks,"more than one DMA path");
  for(unsigned c=0;c<3;c++){
    t->dump("host_"+std::to_string(c)+"_actual.f32le",t->memory.data()+(tab.outputBase+c*tab.span-t->BASE)/4,tab.count()*4);
    t->dump("host_"+std::to_string(c)+"_reference.f32le",golden[c].data(),tab.count()*4);
  }
  for(size_t i=0;i<16;i++)need(t->memory[(tab.outputLimit-t->BASE)/4+i]==0xa5a5a5a5U,"final guard overwritten");
  std::cout<<"SHARED_PRODUCTION_COMMAND_PASS tokens="<<n<<" hidden="<<H<<" ffn="<<F<<" block_stages=15 host_commands=3 block_checked_fp32="<<t->checked
    <<" host_checked_fp32="<<3*tab.count()<<" bit_diffs=0 original_matrix_instances=1 original_idma_instances=1"
    <<" total_idma_transfers="<<t->d.io_idmaTransfers<<" block_to_command_address="<<std::hex<<tab.sourceA<<std::dec
    <<" host_intermediate_writes=0 reset_between_block_and_commands=0 full_21_command_graph=0 official_weights=0\n";
  return 0;
}catch(const std::exception&e){std::cerr<<"SHARED_PRODUCTION_FAIL: "<<e.what()<<"\n";return 1;}}
