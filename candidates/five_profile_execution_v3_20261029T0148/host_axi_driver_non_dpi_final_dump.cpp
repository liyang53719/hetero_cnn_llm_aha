// SPDX-License-Identifier: Apache-2.0
// Only an external AXI memory service for the original HostBlockTopV4.
// No software owner/arithmetic, expected tensor, internal-state access or seed injection.
#ifndef HOST_DRIVER_CONFIG_ONLY
#include "VHostBlockTopV4.h"
#include "verilated.h"
#endif
#include "affine_tsv_loader.hpp"
#include "sparse_write_memory.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
namespace {
void need(bool p,const std::string& why){if(!p)throw std::runtime_error(why);}
uint64_t number(const std::string& s){uint64_t n=0;auto r=std::from_chars(s.data(),s.data()+s.size(),n);need(!s.empty()&&r.ec==std::errc()&&r.ptr==s.data()+s.size(),"unsigned decimal field");return n;}
std::vector<std::string> fields(const std::string& s){std::vector<std::string> v;size_t a=0;for(;;){auto b=s.find('\t',a);v.push_back(s.substr(a,b-a));if(b==std::string::npos)return v;a=b+1;}}
bool simple(const std::string& s){return !s.empty()&&s.size()<80&&std::all_of(s.begin(),s.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='.';});}
struct Region {uint64_t base=0,limit=0;bool read=false,write=false;};
struct Allocation {std::string name,access;uint64_t address=0,bytes=0,reserved=0;};
struct Input {std::string name,path;uint64_t address=0,bytes=0;};
struct Output {std::string name;uint64_t pc=0,address=0,bytes=0,dtype=0;bool observed=false;};
struct Config {
 uint64_t version=0,profile=0,epoch=0,commandBase=0,commandLimit=0,commands=0,descriptorBase=0,descriptorLimit=0,descriptors=0;
 std::string viewManifest;
 std::array<Region,4> regions;std::vector<Allocation> allocations;std::vector<Input> inputs;std::vector<Output> outputs;
 explicit Config(const std::filesystem::path& path){
  need(std::filesystem::is_regular_file(path)&&!std::filesystem::is_symlink(path)&&std::filesystem::file_size(path)<=65536,"small regular input manifest");
  std::ifstream f(path);std::string line;need(bool(std::getline(f,line))&&line=="HOST_COMPILED_INPUT_V2","manifest version");
  bool launch=false;std::set<unsigned> regionIds;std::set<std::string> names,observations;size_t lines=0;
  while(std::getline(f,line)){need(++lines<=2048&&!line.empty()&&line.size()<4096,"manifest line bound");auto v=fields(line);
   if(v[0]=="launch"){
    need(!launch&&v.size()==10,"one launch record");launch=true;
    std::array<uint64_t*,9> p{&version,&profile,&epoch,&commandBase,&commandLimit,&commands,&descriptorBase,&descriptorLimit,&descriptors};
    // The common ABI is version/profile/epoch plus the two original tables.
    need(v.size()==10,"launch field count");
    for(size_t i=1;i<v.size();i++)*p[i-1]=number(v[i]);
   }else if(v[0]=="region"){
    need(v.size()==6,"region fields");auto i=number(v[1]);need(i<4&&regionIds.insert(unsigned(i)).second,"unique region");
    auto& r=regions[i];r.base=number(v[2]);r.limit=number(v[3]);auto rd=number(v[4]),wr=number(v[5]);need(rd<=1&&wr<=1,"region permission bits");r.read=rd;r.write=wr;
   }else if(v[0]=="allocation"){
    need(v.size()==6&&simple(v[1])&&names.insert(v[1]).second,"unique allocation");
    allocations.push_back({v[1],v[5],number(v[2]),number(v[3]),number(v[4])});
   }else if(v[0]=="views"){
    need(v.size()==2&&viewManifest.empty(),"one views manifest");viewManifest=v[1];
    need(std::filesystem::path(viewManifest).is_absolute()&&std::filesystem::is_regular_file(viewManifest)&&!std::filesystem::is_symlink(viewManifest)&&std::filesystem::file_size(viewManifest)<=16*1024*1024,"bounded regular views manifest");
   }else if(v[0]=="observe"){
    need(v.size()==6&&simple(v[2])&&observations.insert(v[2]).second,"unique observation");
    outputs.push_back({v[2],number(v[1]),number(v[3]),number(v[4]),number(v[5]),false});
   }else need(false,"unknown manifest record");
  }
  need(f.eof()&&launch&&regionIds.size()==4&&version==1&&profile<=4&&epoch<65536,"fixed Host844 envelope");
  need(commands>0&&commands<=64&&descriptors>0&&descriptors<=0xffffff&&commandBase%64==0&&descriptorBase%64==0,"table limits");
  need(commandLimit>commandBase&&commandLimit-commandBase==((commands*16+63)&~uint64_t(63))&&descriptorLimit>descriptorBase&&descriptorLimit-descriptorBase==((descriptors*16+63)&~uint64_t(63)),"exact table extents");
  for(const auto& r:regions)need(r.base<=r.limit&&r.limit<(uint64_t(1)<<56)&&r.base%64==0&&r.limit%64==0&&(!r.write||r.read),"region envelope");
  std::sort(allocations.begin(),allocations.end(),[](const auto&a,const auto&b){return a.address<b.address;});
  need(!allocations.empty()&&allocations.size()<=512,"allocation bound");
  uint64_t end=0;
  for(const auto& a:allocations){need(a.address>=end&&a.address%64==0&&a.bytes>0&&a.bytes%64==0&&a.reserved>=a.bytes&&a.reserved%64==0&&a.address<(uint64_t(1)<<56)&&a.reserved<(uint64_t(1)<<56)-a.address,"allocation extent/overlap");end=a.address+a.reserved;
   need(a.access=="ro"||a.access=="rw"||a.access=="virtual","allocation access");bool admitted=false;
   for(const auto& r:regions)admitted|=r.read&&r.write==(a.access!="ro")&&r.base<=a.address&&end<=r.limit;
   need(admitted,"allocation region permissions");
  }
  need(!viewManifest.empty(),"required byte views manifest");
  uint64_t observedBytes=0;for(const auto& o:outputs){need(o.pc<commands&&o.bytes>0&&o.bytes%64==0&&(o.dtype==5||o.dtype==7)&&range(o.address,o.bytes).access=="rw","actual output subspan");observedBytes+=o.bytes;}
  need(!outputs.empty()&&observedBytes<=64*1024*1024,"output retention cap");
  need(range(commandBase,commandLimit-commandBase).access=="ro"&&range(descriptorBase,descriptorLimit-descriptorBase).access=="ro","DDR tables readonly");
 }
 const Allocation& range(uint64_t a,uint64_t n)const{
  auto i=std::upper_bound(allocations.begin(),allocations.end(),a,[](uint64_t p,const Allocation& x){return p<x.address;});
  need(i!=allocations.begin(),"DDR address below allocations");--i;
  need(a>=i->address&&a-i->address<i->bytes&&n>0&&n<=i->bytes-(a-i->address),"DDR crosses tensor/guard");return *i;
 }
};
#ifndef HOST_DRIVER_CONFIG_ONLY
struct Address {bool valid=false;uint64_t address=0;unsigned id=0,beats=0;bool operator==(const Address& b)const{return address==b.address&&id==b.id&&beats==b.beats;}};
struct Write {std::array<uint32_t,16> data{};uint64_t mask=0;bool last=false;bool operator==(const Write& b)const{return data==b.data&&mask==b.mask&&last==b.last;}};
class Simulation {
 Config cfg;VerilatedContext context;std::unique_ptr<VHostBlockTopV4> dut;
 stimulus::ReadOnly immutable;stimulus::SparseWrites mutableMemory{8388608};
 Address aw,pending;bool pendingWrite=false;unsigned readIndex=0;std::vector<Write> writes,committing;
 Address heldAr,heldAw;Write heldW;bool arHeld=false,awHeld=false,wHeld=false;
 bool launched=false;uint64_t cycles=0,activeCycles=0,readBeats=0,readAcks=0,writeBeats=0,writeAcks=0,readBursts=0,writeBursts=0,writeBytes=0,completions=0,launchFires=0;
 std::filesystem::path output;
 uint8_t memoryByte(uint64_t address)const{const auto& a=cfg.range(address,1);need(a.access!="virtual","virtual allocation access");return a.access=="ro"?immutable.byte(address):mutableMemory.byte(address);}
 void initializedRead(uint64_t address,uint64_t bytes){need(cfg.range(address,bytes).access!="virtual","virtual scores/probabilities must not reach DDR");for(uint64_t i=0;i<bytes;++i)(void)memoryByte(address+i);}
 bool drained()const{return !pending.valid&&!aw.valid&&writes.empty()&&committing.empty();}
 void trace(const char* phase){auto& d=*dut;std::cout<<"HOST_PROGRESS "<<phase<<" cycles="<<cycles<<" active_cycles="<<activeCycles<<" pc="<<unsigned(d.io_pc)<<" completions="<<completions<<" read_bursts="<<readBursts<<" read_beats="<<readBeats<<" read_acks="<<readAcks<<" write_bursts="<<writeBursts<<" write_beats="<<writeBeats<<" write_acks="<<writeAcks<<" write_ack_bytes="<<writeBytes<<" pipeline_issues="<<uint64_t(d.io_pipelineIssues)<<" pipeline_stalls="<<uint64_t(d.io_pipelineStalls)<<" idma_transfers="<<uint64_t(d.io_idmaTransfers)<<" idma_cache_hits="<<uint64_t(d.io_idmaCacheHits)<<" idma_streamed_read_beats="<<uint64_t(d.io_idmaStreamedBeats)<<" idma_streamed_write_beats="<<uint64_t(d.io_idmaStreamedWriteBeats)<<" owner_jobs="<<uint64_t(d.io_issuedJobs)<<" useful_macs="<<uint64_t(d.io_usefulMacs)<<" executed_macs="<<uint64_t(d.io_executedMacs)<<" host_write_bytes="<<uint64_t(d.io_writeBytes)<<" memory_accepted_0="<<uint64_t(d.io_memoryAccepted_0)<<" memory_returned_0="<<uint64_t(d.io_memoryReturned_0)<<" memory_accepted_1="<<uint64_t(d.io_memoryAccepted_1)<<" memory_returned_1="<<uint64_t(d.io_memoryReturned_1)<<" reset_required="<<unsigned(d.io_resetRequired)<<"\n";std::cout.flush();}
 void observe(uint64_t word){auto& d=*dut;unsigned status=(word>>32)&255,engine=(word>>29)&7;uint64_t pc=word&((uint64_t(1)<<29)-1);
  need(drained()&&!d.io_axi_ar_valid&&!d.io_axi_aw_valid&&!d.io_axi_w_valid&&status==0&&pc==completions&&(word>>40)==pc+1,"real ordered clean completion after AXI drain");
  need(!d.io_resetRequired,"completion while reset required");
  // Engine identity is decoded from the actual Command128 DDR bytes, not a simulated owner.
  auto commandAddress=cfg.commandBase+pc*16;unsigned expectedEngine=memoryByte(commandAddress+1)&15;
  need(engine==expectedEngine,"completion engine versus original command bytes");
  for(auto& o:cfg.outputs)if(o.pc==pc){need(!o.observed,"output observed twice");initializedRead(o.address,o.bytes);
   auto file=output/(o.name+".actual.bin");need(!std::filesystem::exists(file),"fresh actual output only");std::ofstream f(file,std::ios::binary);std::array<uint8_t,4096> bytes{};for(uint64_t offset=0;offset<o.bytes;){auto n=std::min<uint64_t>(bytes.size(),o.bytes-offset);mutableMemory.read(o.address+offset,bytes.data(),n);f.write(reinterpret_cast<const char*>(bytes.data()),n);offset+=n;}need(bool(f),"actual output write");o.observed=true;
   std::cout<<"HOST_OUTPUT pc="<<pc<<" name="<<o.name<<" bytes="<<o.bytes<<" dtype="<<o.dtype<<" cycles="<<cycles<<"\n";
  }
  ++completions;trace("completion");
 }
 Address address(bool read){auto& d=*dut;Address a;a.valid=true;a.address=read?d.io_axi_ar_bits_addr:d.io_axi_aw_bits_addr;a.id=read?d.io_axi_ar_bits_id:d.io_axi_aw_bits_id;a.beats=1+unsigned(read?d.io_axi_ar_bits_len:d.io_axi_aw_bits_len);
  need(a.beats<=16&&a.address%64==0&&(read?d.io_axi_ar_bits_size:d.io_axi_aw_bits_size)==6&&(read?d.io_axi_ar_bits_burst:d.io_axi_aw_bits_burst)==1&&(a.address&4095)+64*a.beats<=4096,"actual AXI burst fields");
  need(cfg.range(a.address,64*a.beats).access!="virtual","virtual allocation AXI access");return a;
 }
 void step(){if((cycles&0xffff)==0)immutable.checkStable();auto& d=*dut;d.clock=0;
  d.io_axi_ar_ready=launched&&!pending.valid&&!aw.valid&&writes.empty();
  d.io_axi_aw_ready=launched&&!pending.valid&&!aw.valid;
  d.io_axi_w_ready=launched&&!pending.valid&&writes.size()<16&&(writes.empty()||!writes.back().last);
  d.io_axi_r_valid=pending.valid&&!pendingWrite;d.io_axi_b_valid=pending.valid&&pendingWrite;
  d.io_axi_r_bits_id=pending.id;d.io_axi_r_bits_resp=0;d.io_axi_r_bits_last=pending.valid&&readIndex+1==pending.beats;
  d.io_axi_b_bits_id=pending.id;d.io_axi_b_bits_resp=0;
  for(unsigned i=0;i<16;i++){uint32_t value=0;if(pending.valid&&!pendingWrite)for(unsigned b=0;b<4;++b)value|=uint32_t(memoryByte(pending.address+64*readIndex+4*i+b))<<(8*b);d.io_axi_r_bits_data[i]=value;}
  d.eval();
  const bool arf=d.io_axi_ar_valid&&d.io_axi_ar_ready,awf=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
  const bool rf=d.io_axi_r_valid&&d.io_axi_r_ready,bf=d.io_axi_b_valid&&d.io_axi_b_ready;
  if(!launched)need(!d.io_axi_ar_valid&&!d.io_axi_aw_valid&&!d.io_axi_w_valid&&!d.io_completion_valid&&!d.io_result_valid,"no uncommanded execution");
  if(launched)need(!d.io_resetRequired,"DUT resetRequired");
  Address arNow,awNow;Write wNow;
  if(d.io_axi_ar_valid){arNow=address(true);if(arHeld)need(arNow==heldAr,"AR changed while stalled");heldAr=arNow;arHeld=!arf;}else need(!arHeld,"AR withdrawn while stalled");
  if(d.io_axi_aw_valid){awNow=address(false);if(awHeld)need(awNow==heldAw,"AW changed while stalled");heldAw=awNow;awHeld=!awf;}else need(!awHeld,"AW withdrawn while stalled");
  if(d.io_axi_w_valid){for(unsigned i=0;i<16;i++)wNow.data[i]=d.io_axi_w_bits_data[i];wNow.mask=d.io_axi_w_bits_strb;wNow.last=d.io_axi_w_bits_last;if(wHeld)need(wNow==heldW,"W changed while stalled");heldW=wNow;wHeld=!wf;}else need(!wHeld,"W withdrawn while stalled");
  if(d.io_launch_valid&&d.io_launch_ready)++launchFires;
  if(d.io_completion_valid&&d.io_completion_ready)observe(d.io_completion_bits);
  Address next;bool nextWrite=false;
  if(awf){need(!aw.valid,"single AW buffer");aw=awNow;++writeBursts;}
  if(wf)writes.push_back(wNow);
  if(aw.valid)need(writes.size()<=aw.beats,"too many W beats for accepted AW");
  if(aw.valid&&writes.size()==aw.beats){need(!pending.valid&&!arf,"single outstanding AXI transaction");need(cfg.range(aw.address,64*aw.beats).access=="rw","DUT write to readonly/virtual/guard");
   for(unsigned i=0;i<aw.beats;i++)need(writes[i].last==(i+1==aw.beats),"exact WLAST");next=aw;nextWrite=true;committing=writes;writes.clear();aw={};writeBeats+=next.beats;
  }else if(arf){need(!pending.valid&&!awf&&!wf&&!aw.valid&&writes.empty(),"single outstanding AR");next=arNow;initializedRead(next.address,64*next.beats);++readBursts;readBeats+=next.beats;}
  d.clock=1;d.eval();context.timeInc(1);++cycles;if(launched)++activeCycles;
  if(bf){need(pending.valid&&pendingWrite&&committing.size()==pending.beats,"real B ACK association");
   for(unsigned beat=0;beat<pending.beats;beat++){const auto& w=committing[beat];auto a=pending.address+64*beat;
    std::array<uint8_t,64> data{};for(unsigned byte=0;byte<64;byte++){data[byte]=uint8_t(w.data[byte/4]>>(8*(byte%4)));if((w.mask>>byte)&1)++writeBytes;}
    mutableMemory.commitBeat(a,data.data(),w.mask);
   }
   writeAcks+=pending.beats;committing.clear();pending={};
  }
  if(rf){need(pending.valid&&!pendingWrite,"real R ACK association");++readAcks;if(++readIndex==pending.beats){pending={};readIndex=0;}}
  if(next.valid){need(!pending.valid,"pending transaction collision");pending=next;pendingWrite=nextWrite;readIndex=0;}
  d.clock=0;d.eval();context.timeInc(1);
 }
 public:
 Simulation(const std::filesystem::path& manifest,const std::filesystem::path& out):cfg(manifest),output(out){
  uint16_t endian=1;need(*reinterpret_cast<uint8_t*>(&endian)==1,"little-endian host");
  need(!std::filesystem::exists(output),"fresh retained output directory");std::filesystem::create_directory(output);
  std::vector<stimulus::ViewAllocation> readonly;
  for(const auto& a:cfg.allocations){if(a.access=="ro")readonly.push_back({a.name,a.address,a.bytes});else if(a.access=="rw")mutableMemory.addRange(a.address,a.bytes);}
  stimulus::loadViews(cfg.viewManifest,readonly,immutable);
  context.randReset(0);dut=std::make_unique<VHostBlockTopV4>(&context);auto& d=*dut;
  d.clock=0;d.reset=0;d.io_launch_valid=0;d.io_result_ready=0;d.io_completion_ready=0;
  d.io_axi_ar_ready=0;d.io_axi_aw_ready=0;d.io_axi_w_ready=0;d.io_axi_r_valid=0;d.io_axi_b_valid=0;d.io_axi_r_bits_resp=0;d.io_axi_r_bits_id=0;d.io_axi_r_bits_last=0;d.io_axi_b_bits_resp=0;d.io_axi_b_bits_id=0;for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=0;
  d.io_launch_bits_version=cfg.version;d.io_launch_bits_profileId=cfg.profile;d.io_launch_bits_epoch=cfg.epoch;d.io_launch_bits_commandBase=cfg.commandBase;d.io_launch_bits_commandLimit=cfg.commandLimit;d.io_launch_bits_commands=cfg.commands;
  d.io_launch_bits_descriptorBase=cfg.descriptorBase;d.io_launch_bits_descriptorLimit=cfg.descriptorLimit;d.io_launch_bits_descriptors=cfg.descriptors;
#define REGION(I) d.io_launch_bits_regions_##I##_base=cfg.regions[I].base;d.io_launch_bits_regions_##I##_limit=cfg.regions[I].limit;d.io_launch_bits_regions_##I##_read=cfg.regions[I].read;d.io_launch_bits_regions_##I##_write=cfg.regions[I].write
  REGION(0);REGION(1);REGION(2);REGION(3);
#undef REGION
  // Explicit physical reset setup, both evaluations with clock low and inputs inactive.
  d.eval();need(!d.io_axi_ar_valid&&!d.io_axi_aw_valid&&!d.io_axi_w_valid,"time0 no external DDR work");d.reset=1;d.eval();for(unsigned i=0;i<2;i++)step();d.reset=0;for(unsigned i=0;i<3;i++)step();
  need(!d.io_resetRequired&&d.io_launch_ready,"original Host ready after true reset");trace("reset");
 }
 void run(uint64_t maxCycles){auto& d=*dut;need(maxCycles>0&&maxCycles<=1000000000ULL,"explicit watchdog bound");
  const uint64_t dmaBefore=d.io_idmaTransfers,readBurstBefore=d.io_idmaReadBursts,readBeatBefore=d.io_idmaReadBeats;std::array<uint64_t,2> acceptedBefore{d.io_memoryAccepted_0,d.io_memoryAccepted_1},returnedBefore{d.io_memoryReturned_0,d.io_memoryReturned_1};
  d.io_completion_ready=1;d.io_launch_valid=1;d.eval();need(d.io_launch_ready,"real launch fire");launched=true;step();need(launchFires==1,"one actual Host launch handshake");d.io_launch_valid=0;
  while(!d.io_result_valid&&activeCycles<maxCycles){step();if((activeCycles&0xfffff)==0)trace("running");}
  trace("terminal");need(d.io_result_valid,"bounded original Host did not finish; partial progress is not numerical PASS");
  need(launchFires==1&&d.io_result_bits_status==0&&d.io_result_bits_completed==cfg.commands&&d.io_result_bits_epoch==cfg.epoch&&completions==cfg.commands,"complete clean original Host result");
  need(drained()&&readBeats==readAcks&&writeBeats==writeAcks&&!d.io_resetRequired,"final memory drain and ACK conservation");
  need(uint64_t(d.io_idmaTransfers)-dmaBefore==readBursts+writeBursts&&uint64_t(d.io_idmaReadBursts)-readBurstBefore==readBursts&&uint64_t(d.io_idmaReadBeats)-readBeatBefore==readBeats,"every burst through actual sole iDMA");
  need(uint64_t(d.io_memoryAccepted_0)-acceptedBefore[0]==uint64_t(d.io_memoryReturned_0)-returnedBefore[0]&&uint64_t(d.io_memoryAccepted_1)-acceptedBefore[1]==uint64_t(d.io_memoryReturned_1)-returnedBefore[1],"original memory accepted/returned balance");
  for(const auto& o:cfg.outputs)need(o.observed,"missing actual output observation");
  // Fixed weightReadBeats16 production constructor limits each logical request
  // to one 1KiB-contained <=16-beat burst; the exact transfers gate above is
  // specific to that real source, NOT a general iDMA legalizer assumption.
  const std::array<uint64_t,8> stopped{d.io_idmaTransfers,d.io_idmaReadBursts,d.io_idmaReadBeats,d.io_pipelineIssues,d.io_issuedJobs,d.io_memoryAccepted_0,d.io_memoryAccepted_1,d.io_idmaStreamedWriteBeats};
  auto terminalQuiet=[&](){
    need(!d.io_resetRequired&&!d.io_axi_ar_valid&&!d.io_axi_aw_valid&&!d.io_axi_w_valid&&!d.io_completion_valid&&drained(),"no terminal fault or new external offer");
    need(stopped==std::array<uint64_t,8>{d.io_idmaTransfers,d.io_idmaReadBursts,d.io_idmaReadBeats,d.io_pipelineIssues,d.io_issuedJobs,d.io_memoryAccepted_0,d.io_memoryAccepted_1,d.io_idmaStreamedWriteBeats},"no new work after terminal result");
  };
  auto status=d.io_result_bits_status;auto completed=d.io_result_bits_completed;auto failedPc=d.io_result_bits_failedPc;auto epoch=d.io_result_bits_epoch;
  for(unsigned i=0;i<3;i++){step();terminalQuiet();need(d.io_result_valid&&d.io_result_bits_status==status&&d.io_result_bits_completed==completed&&d.io_result_bits_failedPc==failedPc&&d.io_result_bits_epoch==epoch,"complete held result stability");}
  d.io_result_ready=1;step();d.io_result_ready=0;terminalQuiet();need(!d.io_result_valid&&drained(),"result consumption");immutable.checkStable();dut->final();
  // Final externally visible bytes only; no arithmetic, oracle, or internal DUT access.
  // Re-read after result consumption to reject later modification of a cache/state.
  for(const auto& o:cfg.outputs)if(o.name=="output"||o.name=="y"||o.name=="history_out"||o.name=="state_out"||o.name=="cache"||o.name=="cache_k"||o.name=="cache_v"){
   initializedRead(o.address,o.bytes);
   auto file=output/(o.name+".final.bin");need(!std::filesystem::exists(file),"fresh final dump only");
   std::ofstream f(file,std::ios::binary);std::array<uint8_t,4096> bytes{};
   for(uint64_t offset=0;offset<o.bytes;){auto n=std::min<uint64_t>(bytes.size(),o.bytes-offset);mutableMemory.read(o.address+offset,bytes.data(),n);f.write(reinterpret_cast<const char*>(bytes.data()),n);offset+=n;}
   f.close();need(bool(f),"final dump write/close");
   std::cout<<"HOST_FINAL_OUTPUT name="<<o.name<<" address="<<o.address<<" bytes="<<o.bytes<<" dtype="<<o.dtype<<" coverage=ACKNOWLEDGED_EVERY_BYTE\n";
  }
  if(cfg.profile==3||cfg.profile==4){
   // Actual allocator: region3.base + HostMoePhaseLayoutV4.Metadata(0).
   // First 8192 B are token-major 128*8 packed route records, not an oracle.
   uint64_t address=cfg.regions[3].base;initializedRead(address,8192);
   auto file=output/"router_token_map.final.bin";need(!std::filesystem::exists(file),"fresh route map only");
   std::ofstream f(file,std::ios::binary);std::array<uint8_t,4096> bytes{};
   for(uint64_t offset=0;offset<8192;offset+=bytes.size()){mutableMemory.read(address+offset,bytes.data(),bytes.size());f.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());}
   f.close();need(bool(f),"actual route map dump");
   std::cout<<"HOST_FINAL_ROUTE_MAP bytes=8192 coverage=ACKNOWLEDGED_EVERY_BYTE\n";
   // Authoritative router output is BF16 [128,256], 64 KiB, NOT FP32.
   // Region3+128KiB begins Gather and must not be included in this snapshot.
   uint64_t logitsAddress=cfg.regions[3].base+65536;initializedRead(logitsAddress,65536);
   auto logitsFile=output/"router_logits_bf16.final.bin";need(!std::filesystem::exists(logitsFile),"fresh router logits only");
   std::ofstream lf(logitsFile,std::ios::binary);
   for(uint64_t offset=0;offset<65536;offset+=bytes.size()){mutableMemory.read(logitsAddress+offset,bytes.data(),bytes.size());lf.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());}
   lf.close();need(bool(lf),"actual router logits dump");
   std::cout<<"HOST_FINAL_ROUTER_LOGITS bytes=65536 dtype=BF16 coverage=ACKNOWLEDGED_EVERY_BYTE\n";

  }
  std::cout<<"COMPLETE_ORIGINAL_HOST_DDR_REPLAY profile="<<cfg.profile<<" commands="<<cfg.commands<<" observations="<<cfg.outputs.size()<<" cycles="<<cycles<<" active_cycles="<<activeCycles<<" comparison=NOT_PERFORMED provider_matrix_rtl=BOUND_EXTERNAL_REVIEW_REQUIRED\n";
 }
};
#endif
}
#ifndef HOST_DRIVER_CONFIG_ONLY
int main(int argc,char**argv){try{need(argc==4,"MANIFEST OUTPUT MAX_ACTIVE_CYCLES; no oracle argv");Simulation sim(argv[1],argv[2]);sim.run(number(argv[3]));return 0;}catch(const std::exception& e){std::cerr<<"ORIGINAL_HOST_REPLAY_FAIL: "<<e.what()<<"\n";return 1;}}

#endif
