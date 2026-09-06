// SPDX-License-Identifier: Apache-2.0
// Adversarial execution on the SAME generated HostResidualIdmaTop used by the
// numerical suite. No owner/completion stubs and no replacement DMA model.
#include "VHostResidualIdmaTop.h"
#include "verilated.h"
#include "host_command_axi_service.h"
#include <cfenv>

struct Fixture {
  static constexpr uint64_t base=0x100000000ULL;
  HostTables table;
  std::vector<uint32_t> memory;
  std::vector<uint8_t> initialized;
  std::vector<std::vector<uint32_t>> golden;
  Fixture() {
    table.rows=1;table.width=33;table.dtype=7;table.span=192;
    table.sourceA=base;table.sourceB=base+table.span;
    table.inputBase=base;table.inputLimit=base+2*table.span;
    table.commandBase=table.inputLimit;table.descriptorBase=table.commandBase+64;
    table.tableLimit=table.commandBase+4096;
    table.outputBase=table.tableLimit;table.outputLimit=table.outputBase+3*table.span;
    memory.resize((table.outputLimit-base)/4+16,0xa5a5a5a5U);
    initialized.resize(memory.size(),0);
    golden.assign(3,std::vector<uint32_t>(33));
    for(unsigned j=0;j<33;j++) {
      float a=float(int(j)-17)/32.0f,b=float(int(j%9)-4)/128.0f;
      memory[j]=hbits(a);memory[table.span/4+j]=hbits(b);
      for(unsigned pc=0;pc<3;pc++){a=a+b;golden[pc][j]=hbits(a);}
    }
    for(uint64_t p=base;p<table.inputLimit;p+=4)initialized[(p-base)/4]=1;
    for(unsigned pc=0;pc<3;pc++)
      for(uint64_t p=table.outputBase+pc*table.span+132;p<table.outputBase+(pc+1)*table.span;p+=4)
        initialized[(p-base)/4]=1;
    table.populate(memory,initialized,base);
  }
};

static void reset(VHostResidualIdmaTop& d) {
  d.io_launch_valid=0;d.io_result_ready=0;d.io_completion_ready=0;
  d.io_axi_ar_ready=0;d.io_axi_aw_ready=0;d.io_axi_w_ready=0;
  d.io_axi_r_valid=0;d.io_axi_b_valid=0;d.reset=1;
  for(int i=0;i<4;i++){d.clock=0;d.eval();d.clock=1;d.eval();}
  d.reset=0;d.clock=0;d.eval();
}

static void runCase(unsigned pc,unsigned fault) {
  auto dut=std::make_unique<VHostResidualIdmaTop>();auto& d=*dut;
  reset(d);Fixture f;
  HostAxiService<VHostResidualIdmaTop> bus(d,f.memory,f.initialized,Fixture::base,f.table);
  bus.golden=f.golden;bus.configure(300+pc*4+fault);d.eval();
  hcheck(d.io_launch_ready,"not ready after reset");d.io_launch_valid=1;bus.step();d.io_launch_valid=0;
  unsigned hold=0;uint64_t errorCompletions=0,heldWord=0;bool held=false;
  while(!d.io_result_valid&&bus.cycles<100000) {
    if(bus.completed==pc&&!bus.injected) {
      // Trigger faults at four different boundaries of each command. For the
      // last-write case 128 bytes of that tensor are visible but unpublished.
      if(fault==0)bus.injectRead=true;
      if(fault==1&&bus.metadataReads>=11*(pc+1))bus.injectRead=true;
      if(fault==2)bus.injectWrite=true;
      if(fault==3&&bus.writeAcks>=pc*3+2)bus.injectWrite=true;
    }
    d.io_completion_ready=d.io_completion_valid&&hold++>4;
    if(!d.io_completion_valid)hold=0;
    if(d.io_completion_valid) {
      uint64_t word=d.io_completion_bits;
      if(held)hcheck(word==heldWord,"completion changed under backpressure");
      heldWord=word;held=!d.io_completion_ready;
      if(d.io_completion_ready&&((word>>32)&255)) {
        errorCompletions++;
        hcheck(((word>>32)&255)==3,"I/O error not preserved in completion");
        // A failed command-record fetch has no trustworthy signal-event field.
        hcheck((word>>40)==(fault==0?0:pc+1),"error completion wrong event");
      }
    }else hcheck(!held,"completion withdrawn under backpressure");
    bus.step();
  }
  hcheck(d.io_result_valid&&bus.injected,"fault was not exercised/completed");
  hcheck(d.io_result_bits_status==3&&d.io_result_bits_failedPc==pc,"wrong failing command or status");
  hcheck(errorCompletions==1&&d.io_result_bits_completed==pc&&bus.completed==pc,"failure retired as success");
  for(unsigned i=0;i<3;i++)hcheck(bus.published[i]==(i<pc),"failed/dependent tensor published");
  hcheck(bus.visibleBytes==uint64_t(pc)*132+(fault==3?128:0),"partial visibility accounting");
  hcheck(d.io_idmaTransfers==bus.readAcks+bus.writeAcks,"DMA conservation failure");
  hcheck(d.io_memoryAccepted_0==bus.metadataReads&&d.io_memoryReturned_0==bus.metadataReads,"metadata bypassed arbiter");
  hcheck(d.io_memoryAccepted_1==bus.payloadReads+bus.writeAcks&&d.io_memoryReturned_1==bus.payloadReads+bus.writeAcks,"payload bypassed arbiter");
  const auto status=d.io_result_bits_status;const auto done=d.io_result_bits_completed;
  const auto failed=d.io_result_bits_failedPc;const auto epoch=d.io_result_bits_epoch;
  for(unsigned i=0;i<7;i++){bus.step();hcheck(d.io_result_valid&&d.io_result_bits_status==status&&d.io_result_bits_completed==done&&d.io_result_bits_failedPc==failed&&d.io_result_bits_epoch==epoch,"unstable aggregate completion");}
  d.io_result_ready=1;bus.step();d.io_result_ready=0;
  const uint64_t transfers=d.io_idmaTransfers;d.io_launch_valid=1;
  for(unsigned i=0;i<8;i++){hcheck(!d.io_launch_ready&&d.io_resetRequired,"failed request escaped quarantine");bus.step();}
  hcheck(d.io_idmaTransfers==transfers,"new transfer after failed request");d.io_launch_valid=0;
  std::cout<<"HOST_PARTIAL_FAILURE_PASS pc="<<pc<<" fault="<<fault<<" status=3 successful_commands="<<pc
    <<" current_visible_bytes="<<(fault==3?128:0)<<" dependent_commands=0 error_completions=1 original_idma=1\n";
  // Only an explicit reset permits a new request. A fresh host input allocation
  // is legal after reset; no input or output is rewritten during an active job.
  reset(d);Fixture fresh;
  HostAxiService<VHostResidualIdmaTop> recovery(d,fresh.memory,fresh.initialized,Fixture::base,fresh.table);
  recovery.golden=fresh.golden;recovery.run();
  hcheck(!d.io_resetRequired,"recovery remained poisoned");
  std::cout<<"HOST_RESET_RECOVERY_PASS pc="<<pc<<" fault="<<fault<<" checked_fp32=99 commands=3\n";
}

int main(int argc,char**argv) {
  Verilated::commandArgs(argc,argv);std::fesetround(FE_TONEAREST);
  try {
    for(unsigned pc=0;pc<3;pc++)for(unsigned fault=0;fault<4;fault++)runCase(pc,fault);
    std::cout<<"HOST_PARTIAL_FAILURE_SUITE_PASS fault_cases=12 reset_recoveries=12 original_idma=1 arithmetic_stub=0\n";
    return 0;
  }catch(const std::exception& e){std::cerr<<"HOST_PARTIAL_FAILURE_FAIL: "<<e.what()<<"\n";return 1;}
}
