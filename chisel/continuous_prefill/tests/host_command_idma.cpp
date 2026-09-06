// SPDX-License-Identifier: Apache-2.0
#include "VHostResidualIdmaTop.h"
#include "verilated.h"
#include "host_command_axi_service.h"

static void one(size_t count,unsigned dtype,unsigned fault=0) {
  const uint64_t base=0x100000000ULL;
  const unsigned bytes=dtype==5?2:4;
  const uint64_t span=HostTables::align64(count*bytes);
  HostTables tab;tab.dtype=dtype;tab.width=unsigned(count);tab.rows=1;tab.span=span;
  tab.sourceA=base;tab.sourceB=base+span;
  tab.inputBase=base;tab.inputLimit=base+2*span;
  tab.commandBase=tab.inputLimit;tab.descriptorBase=tab.commandBase+64;
  tab.tableLimit=tab.commandBase+4096;tab.outputBase=tab.tableLimit;tab.outputLimit=tab.outputBase+3*span;
  std::vector<uint32_t> memory((tab.outputLimit-base)/4+16,0xa5a5a5a5U);
  std::vector<uint8_t> initialized(memory.size(),0);
  std::vector<float> x(count),b(count);
  auto store=[&](uint64_t address,uint32_t bits,unsigned n){for(unsigned j=0;j<n;j++){
    uint64_t off=address-base+j;auto& word=memory[off/4];unsigned shift=(off%4)*8;
    word=(word&~(255U<<shift))|(uint32_t((bits>>(j*8))&255)<<shift);initialized[off/4]=1;
  }};
  for(size_t j=0;j<count;j++){
    x[j]=float(int(j%61)-30)/128.0f;b[j]=float(int(j%29)-14)/512.0f;
    if(dtype==5){x[j]=hfloat(uint32_t(hbf(x[j]))<<16);b[j]=hfloat(uint32_t(hbf(b[j]))<<16);}
    store(tab.sourceA+j*bytes,dtype==5?hbf(x[j]):hbits(x[j]),bytes);
    store(tab.sourceB+j*bytes,dtype==5?hbf(b[j]):hbits(b[j]),bytes);
  }
  // Read beats may include unused padding. Padding is initialized poison, never
  // legal payload, and must remain poison after masked stores.
  for(unsigned n=0;n<2;n++)for(uint64_t a=base+n*span+count*bytes;a<base+(n+1)*span;a+=1)initialized[(a-base)/4]=1;
  for(unsigned n=0;n<3;n++)for(uint64_t a=tab.outputBase+n*span+count*bytes;a<tab.outputBase+(n+1)*span;a++)initialized[(a-base)/4]=1;
  tab.populate(memory,initialized,base);
  if(fault==4)memory[(tab.commandBase-base)/4]^=1; // Unsupported opcode.
  if(fault==5)memory[(tab.descriptorBase-base)/4+3]|=1U<<8; // Illegal memory space.
  if(fault==6)memory[(tab.descriptorBase-base)/4+3]&=~(15U<<20); // Illegal rank.
  if(fault==7)memory[(tab.commandBase-base)/4]|=1U<<11; // Unsupported flags.
  if(fault==8)memory[(tab.commandBase-base)/4]|=7U<<24; // Unsatisfied event.
  auto dut=std::make_unique<VHostResidualIdmaTop>();auto& d=*dut;
  d.io_launch_valid=0;d.io_result_ready=0;d.io_completion_ready=0;d.io_axi_ar_ready=0;d.io_axi_aw_ready=0;d.io_axi_w_ready=0;d.io_axi_r_valid=0;d.io_axi_b_valid=0;
  d.reset=1;for(int k=0;k<4;k++){d.clock=0;d.eval();d.clock=1;d.eval();}d.reset=0;d.clock=0;d.eval();
  HostAxiService<VHostResidualIdmaTop> service(d,memory,initialized,base,tab);
  service.injectWrite=fault==1;service.injectRead=fault==2||fault==3;service.badId=fault==3;
  service.golden.resize(3);
  for(unsigned n=0;n<3;n++){service.golden[n].resize(count);for(size_t j=0;j<count;j++){
    float y=x[j]+b[j];uint32_t bits=dtype==5?hbf(y):hbits(y);service.golden[n][j]=bits;
    x[j]=dtype==5?hfloat(bits<<16):y;
  }}
  service.run(fault!=0);
}
int main(int argc,char**argv){
  Verilated::commandArgs(argc,argv);unsigned cases=0;
  try {
    for(unsigned dtype:{5U,7U})for(size_t n:std::vector<size_t>{1,15,16,17,31,32,33,1023,1024,1025,24576}){one(n,dtype);cases++;}
    for(unsigned fault=1;fault<=8;fault++){one(33,7,fault);cases++;}
    std::cout<<"HOST_COMMAND_IDMA_SUITE_PASS cases="<<cases<<" original_idma=1 command128=1 actual_sfu=1 arithmetic_stub=0\n";return 0;
  }catch(const std::exception&e){std::cerr<<"HOST_COMMAND_FAIL after_cases="<<cases<<" reason="<<e.what()<<"\n";return 1;}
}
