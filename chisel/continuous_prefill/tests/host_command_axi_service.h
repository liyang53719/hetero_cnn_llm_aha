// SPDX-License-Identifier: Apache-2.0
// Testbench memory service only. No reference value is returned in place of DDR.
#pragma once
#include <array>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <fstream>
#include <memory>
#include <filesystem>

#ifdef HOST_WITH_BLOCK
#define HLAUNCH(field) io_commandLaunch_##field
#define HRESULT(field) io_commandResult_##field
#define HCOMP(field) io_commandCompletion_##field
#else
#define HLAUNCH(field) io_launch_##field
#define HRESULT(field) io_result_##field
#define HCOMP(field) io_completion_##field
#endif
static void hcheck(bool ok,const std::string& what){if(!ok)throw std::runtime_error(what);}
static uint32_t hbits(float v){uint32_t b;std::memcpy(&b,&v,4);return b;}
static float hfloat(uint32_t v){float f;std::memcpy(&f,&v,4);return f;}
static uint16_t hbf(float f){auto u=hbits(f);return uint16_t((u+0x7fff+((u>>16)&1))>>16);}
using RecordWord=unsigned __int128;
static RecordWord hrec(uint8_t type,uint32_t next,RecordWord payload){return RecordWord(type)|(RecordWord(next)<<32)|(payload<<56);}
static RecordWord hbase(uint64_t addr,unsigned dtype,uint32_t next){
  return hrec(1,next,RecordWord(addr&0xffffffffffffULL)|(RecordWord(dtype)<<52)|(RecordWord(2)<<60)|(RecordWord(addr>>48)<<64));
}
struct HostTables {
  uint64_t commandBase=0,descriptorBase=0,tableLimit=0,outputBase=0,outputLimit=0;
  uint64_t sourceA=0,sourceB=0,inputBase=0,inputLimit=0;
  unsigned rows=1,width=1,commands=3,dtype=7;uint64_t span=0;
  size_t count()const{return size_t(rows)*width;}
  static uint64_t align64(uint64_t n){return (n+63)&~uint64_t(63);}
  void storeRecord(std::vector<uint32_t>& mem,uint64_t base,uint64_t addr,RecordWord w)const{
    hcheck(addr>=base && (addr-base)/4+4<=mem.size(),"table bounds");
    for(unsigned i=0;i<4;i++)mem[(addr-base)/4+i]=uint32_t(w>>(32*i));
  }
  void populate(std::vector<uint32_t>& mem,std::vector<uint8_t>& initialized,uint64_t base)const{
    for(unsigned n=0;n<commands;n++){
      const uint32_t root=n*10;const uint64_t a=n?outputBase+(n-1)*span:sourceA;
      const uint64_t dst=outputBase+n*span;
      RecordWord cmd=0x330|(RecordWord(n)<<24)|(RecordWord(n+1)<<40)|(RecordWord(root)<<56)|(RecordWord(root+4)<<80)|(RecordWord(root+7)<<104);
      storeRecord(mem,base,commandBase+n*16,cmd);
      const RecordWord shape=RecordWord(rows)|(RecordWord(width)<<18)|(RecordWord(1)<<36)|(RecordWord(1)<<54);
      const RecordWord stride=RecordWord(width)|(RecordWord(1)<<24)|(RecordWord(1)<<48);
      const RecordWord program=0x30|(RecordWord(2)<<16)|(RecordWord(1)<<24)|(RecordWord(dtype)<<32)|(RecordWord(dtype)<<36)|(RecordWord(16)<<40);
      std::array<RecordWord,10> r{{hbase(a,dtype,root+1),hrec(2,root+2,shape),hrec(3,root+3,stride),hrec(0x20,0xffffff,program),
        hbase(sourceB,dtype,root+5),hrec(2,root+6,shape),hrec(3,0xffffff,stride),
        hbase(dst,dtype,root+8),hrec(2,root+9,shape),hrec(3,0xffffff,stride)}};
      for(unsigned i=0;i<10;i++)storeRecord(mem,base,descriptorBase+(root+i)*16,r[i]);
    }
    for(uint64_t addr=commandBase;addr<tableLimit;addr+=4)initialized[(addr-base)/4]=1;
  }
};
struct HostBeat {
  bool valid=false,write=false;uint64_t address=0,mask=0;uint8_t id=0;std::array<uint32_t,16> data{};unsigned delay=0;bool bad=false;
};

template<class D> class HostAxiService {
public:
  D& d;std::vector<uint32_t>& mem;std::vector<uint8_t>& init;uint64_t base;HostTables t;
  HostBeat aw,w,pending,heldAw,heldW,heldAr;bool awHeld=false,wHeld=false,arHeld=false;
  uint64_t cycles=0,readAcks=0,writeAcks=0,metadataReads=0,payloadReads=0,stalls=0,delays=0,completed=0,visibleBytes=0;
  std::array<uint64_t,3> commandWrites{};uint32_t rng=0x7196b31;bool injectWrite=false,injectRead=false,badId=false,injected=false;
  bool allowCompletion=false;std::array<bool,3> published{};std::vector<std::vector<uint32_t>> golden;
  HostAxiService(D& dut,std::vector<uint32_t>& m,std::vector<uint8_t>& i,uint64_t b,HostTables tab):d(dut),mem(m),init(i),base(b),t(tab){}
  unsigned random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
  static bool eq(const HostBeat&a,const HostBeat&b){return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data;}
  bool inOutput(uint64_t addr)const{return addr>=t.outputBase && addr<t.outputLimit;}
  unsigned outputId(uint64_t addr)const{return unsigned((addr-t.outputBase)/t.span);}
  uint8_t byteAt(uint64_t address)const{return uint8_t(mem[(address-base)/4]>>(8*((address-base)%4)));}
  void bytePut(uint64_t address,uint8_t v){auto pos=address-base;auto& x=mem[pos/4];unsigned shift=(pos%4)*8;x=(x&~(uint32_t(255)<<shift))|(uint32_t(v)<<shift);init[pos/4]=1;}
  void checkRead(uint64_t address){
    for(unsigned j=0;j<64;j++)hcheck(init[(address-base+j)/4],"read uninitialized DDR");
    if(inOutput(address))hcheck(published[outputId(address)],"consumer read before producer completion/write ACK");
  }
  void checkWrite(const HostBeat& beat){
    hcheck(inOutput(beat.address)&&outputId(beat.address)==completed,"write outside current command output");
    for(unsigned j=0;j<64;j++)if((beat.mask>>j)&1){
      hcheck(beat.address+j<t.outputBase+completed*t.span+t.count()*(t.dtype==5?2:4),"tail mask out of tensor");
    }
  }
  void compare(unsigned n){
    hcheck(commandWrites[n]==t.count()*(t.dtype==5?2:4),"completion before final successful B ACK");
    const uint64_t address=t.outputBase+n*t.span;
    for(size_t j=0;j<t.count();j++){
      uint32_t actual=0;unsigned bytes=t.dtype==5?2:4;for(unsigned k=0;k<bytes;k++)actual|=uint32_t(byteAt(address+j*bytes+k))<<(8*k);
      hcheck(actual==golden[n][j],"host residual bit mismatch command="+std::to_string(n)+" index="+std::to_string(j));
    }
    for(uint64_t a=address+t.count()*(t.dtype==5?2:4);a<address+t.span;a++)hcheck(byteAt(a)==0xa5,"masked tail overwritten");
    published[n]=true;
    std::cout<<"HOST_COMMAND_CHECK pc="<<n<<" values="<<t.count()<<" bit_diffs=0 write_ack_bytes="<<commandWrites[n]<<"\n";
  }
  void step(){
    d.clock=0;
    d.io_axi_ar_ready=!pending.valid&&!aw.valid&&!w.valid&&(random()%4!=0);
    d.io_axi_aw_ready=!pending.valid&&!aw.valid&&(random()%3!=0);d.io_axi_w_ready=!pending.valid&&!w.valid&&(random()%4!=0);
    d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;
    d.io_axi_b_bits_resp=pending.bad?2:0;d.io_axi_b_bits_id=pending.id^((pending.bad&&badId)?1:0);
    d.io_axi_r_bits_resp=pending.bad?2:0;d.io_axi_r_bits_id=pending.id^((pending.bad&&badId)?1:0);d.io_axi_r_bits_last=1;
    for(int j=0;j<16;j++)d.io_axi_r_bits_data[j]=pending.data[j];d.eval();
    bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
    bool ack=(d.io_axi_b_valid&&d.io_axi_b_ready)||(d.io_axi_r_valid&&d.io_axi_r_ready);
    bool cf=d.HCOMP(valid)&&d.HCOMP(ready);
    HostBeat a,b,c;
    if(d.io_axi_aw_valid){a.valid=true;a.address=d.io_axi_aw_bits_addr;a.id=d.io_axi_aw_bits_id;
      hcheck(d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size<=6&&d.io_axi_aw_bits_burst==1,"bad AW descriptor");
      if(awHeld)hcheck(eq(a,heldAw),"unstable AW");heldAw=a;awHeld=!af;}else hcheck(!awHeld,"withdrawn AW");
    if(d.io_axi_w_valid){b.valid=true;b.write=true;b.mask=d.io_axi_w_bits_strb;for(int j=0;j<16;j++)b.data[j]=d.io_axi_w_bits_data[j];
      hcheck(d.io_axi_w_bits_last,"missing WLAST");if(wHeld)hcheck(eq(b,heldW),"unstable W");heldW=b;wHeld=!wf;}else hcheck(!wHeld,"withdrawn W");
    if(d.io_axi_ar_valid){c.valid=true;c.address=d.io_axi_ar_bits_addr;c.id=d.io_axi_ar_bits_id;
      hcheck(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"bad AR descriptor");
      if(arHeld)hcheck(eq(c,heldAr),"unstable AR");heldAr=c;arHeld=!ar;}else hcheck(!arHeld,"withdrawn AR");
    stalls+=(d.io_axi_ar_valid&&!ar)+(d.io_axi_aw_valid&&!af)+(d.io_axi_w_valid&&!wf);
    if(pending.valid&&pending.delay)delays++;
    if(af)aw=a;if(wf)w=b;HostBeat next;
    if(aw.valid&&w.valid){hcheck(!pending.valid&&!ar,"overlapping AXI");next=w;next.address=aw.address;next.id=aw.id;aw={};w={};}
    else if(ar){hcheck(!pending.valid,"multiple reads");next=c;if(next.address>=t.commandBase&&next.address<t.tableLimit)metadataReads++;else payloadReads++;}
    if(next.valid){hcheck(next.address>=base&&next.address-base+64<=mem.size()*4&&(next.address&63)==0,"AXI address outside region");next.delay=1+random()%5;
      if(next.write)checkWrite(next);else checkRead(next.address);
      if(!next.write)for(unsigned j=0;j<64;j++)next.data[j/4]|=uint32_t(byteAt(next.address+j))<<(8*(j%4));
      if(!injected&&((next.write&&injectWrite)||(!next.write&&injectRead))){next.bad=true;injected=true;}}
    if(d.HCOMP(valid)){
      hcheck(!pending.valid&&!aw.valid&&!w.valid,"host completion before memory drain");
      const uint64_t comp=d.HCOMP(bits);const unsigned status=(comp>>32)&255;
      hcheck(((comp>>29)&7)==3,"wrong completion owner");
      if(status==0)hcheck(commandWrites[completed]==t.count()*(t.dtype==5?2:4),"premature successful completion");
      if(cf){if(status==0){hcheck((comp>>40)==completed+1,"wrong signal event");compare(completed);completed++;}}
    }
    d.clock=1;d.eval();cycles++;
    if(ack){if(pending.write){writeAcks++;if(!pending.bad){
          unsigned n=outputId(pending.address);for(unsigned j=0;j<64;j++)if((pending.mask>>j)&1){bytePut(pending.address+j,uint8_t(pending.data[j/4]>>(8*(j%4))));commandWrites[n]++;visibleBytes++;}}}
      else readAcks++;pending={};}
    if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;
    d.clock=0;d.eval();
  }
  void configure(unsigned epoch=90){
    d.HLAUNCH(valid)=0;d.HRESULT(ready)=0;d.HCOMP(ready)=0;
    d.HLAUNCH(bits_commandBase)=t.commandBase;d.HLAUNCH(bits_commandLimit)=t.commandBase+64;
    d.HLAUNCH(bits_commands)=t.commands;d.HLAUNCH(bits_descriptorBase)=t.descriptorBase;
    d.HLAUNCH(bits_descriptorLimit)=t.descriptorBase+HostTables::align64(t.commands*10*16);
    d.HLAUNCH(bits_descriptors)=t.commands*10;d.HLAUNCH(bits_epoch)=epoch;
#define SET_REGION(i,b,l,r,w) d.HLAUNCH(bits_regions_##i##_base)=b;d.HLAUNCH(bits_regions_##i##_limit)=l;d.HLAUNCH(bits_regions_##i##_read)=r;d.HLAUNCH(bits_regions_##i##_write)=w
    SET_REGION(0,t.inputBase,t.inputLimit,1,0);
    SET_REGION(1,t.commandBase,t.tableLimit,1,0);
    SET_REGION(2,t.outputBase,t.outputLimit,1,1);
    SET_REGION(3,0,0,0,0);
#undef SET_REGION
  }
  void run(bool expectError=false){
    const uint64_t dmaBefore=d.io_idmaTransfers;
    configure();d.eval();hcheck(d.HLAUNCH(ready),"host launch not ready");d.HLAUNCH(valid)=1;step();d.HLAUNCH(valid)=0;
    uint64_t bound=20000+t.count()*100;
    unsigned completionHold=0;
    while(!d.HRESULT(valid)&&cycles<bound){
      d.HCOMP(ready)=d.HCOMP(valid)&&completionHold++>4;
      if(!d.HCOMP(valid))completionHold=0;
      step();
    }
    hcheck(d.HRESULT(valid),"host command timeout");
    hcheck(bool(d.HRESULT(bits_status))==expectError,"unexpected host result status "+std::to_string(d.HRESULT(bits_status)));
    hcheck(d.HRESULT(bits_completed)==completed,"completion count mismatch");
    hcheck(d.io_idmaTransfers-dmaBefore==readAcks+writeAcks,"transactions bypassed sole iDMA");
    if(!expectError){hcheck(completed==t.commands,"missing host command");hcheck(metadataReads==11*t.commands,"descriptor fetch coverage mismatch");
      hcheck(payloadReads>0&&visibleBytes==t.commands*t.count()*(t.dtype==5?2:4),"no actual data path");}
    else hcheck(d.io_resetRequired&&completed==0,"error published dependent result");
    auto status=d.HRESULT(bits_status);for(int k=0;k<7;k++){step();hcheck(d.HRESULT(valid)&&d.HRESULT(bits_status)==status,"unstable result");}
    d.HRESULT(ready)=1;step();d.HRESULT(ready)=0;
    if(expectError){d.HLAUNCH(valid)=1;for(int k=0;k<8;k++){hcheck(!d.HLAUNCH(ready),"reset lockout violated");step();}d.HLAUNCH(valid)=0;}
    std::cout<<"HOST_COMMAND_CHAIN_"<<(expectError?"ERROR_REJECT_PASS":"PASS")<<" commands="<<completed<<" values="<<t.count()*completed<<" dtype="<<t.dtype
      <<" bit_diffs=0 metadata_reads="<<metadataReads<<" payload_reads="<<payloadReads<<" write_ack_bytes="<<visibleBytes
      <<" idma_transfers="<<d.io_idmaTransfers-dmaBefore<<" request_stalls="<<stalls<<" response_delay_cycles="<<delays<<" host_intermediate_writes=0\n";
  }
};
