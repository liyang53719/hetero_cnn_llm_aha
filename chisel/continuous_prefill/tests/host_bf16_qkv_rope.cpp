// SPDX-License-Identifier: Apache-2.0
// Seven public commands on one actual HostBlockTop. No reference enters DDR.
#include "VHostBlockTop.h"
#include "verilated.h"
#include "host_physical_axi.h"
#include <cfenv>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <algorithm>

using host_test::require;
using host_test::Beat;
namespace fs=std::filesystem;
struct Span {
  std::string name; unsigned pc=0; uint64_t allocation=0,allocationBytes=0,begin=0,bytes=0;
  std::vector<uint16_t> reference; std::vector<uint8_t> touched;
};
struct Command {
  std::string name; unsigned engine=0,records=0,signal=0,spanFirst=0,spanCount=0;
  uint64_t input=0,inputBytes=0,constant=0,constantBytes=0,accepted=0,acked=0,finalAcks=0,dependencyReads=0;
  bool published=false;
};
class Chain {
 public:
  VHostBlockTop d;
  uint64_t base=0,limit=0,cb=0,cl=0,db=0,dl=0,meta=0,scratch=0,aa=0,rows=0,first=0,count=0,position=0,trig=0,trigTokens=0,gammaQ=0,gammaK=0;
  std::vector<Command> commands;std::vector<Span> spans;
  std::unique_ptr<host_test::PhysicalMemory> mem;
  std::unique_ptr<host_test::PhysicalAxi<VHostBlockTop,Chain>> bus;
  std::vector<uint32_t> initial;
  std::string mode;fs::path out;
  bool running=false,injected=false,held=false,faultAcknowledged=false;uint64_t heldWord=0,metadata=0,ackBytes=0;
  unsigned pc=0,successful=0,holdRemaining=11,run=0;
  static bool inside(uint64_t a,uint64_t bytes,uint64_t b,uint64_t size){return a>=b&&bytes>0&&a+bytes>=a&&a+bytes<=b+size;}
  static uint32_t bits(float f){uint32_t u;std::memcpy(&u,&f,4);return u;}
  static float fp(uint16_t b){uint32_t u=uint32_t(b)<<16;float f;std::memcpy(&f,&u,4);return f;}
  static uint16_t bf(float f){auto u=bits(f);require(std::isfinite(f)&&(u&0x7fffffffU)<0x7f7f8000U,"nonfinite canonical Dense");return uint16_t((u+0x7fff+((u>>16)&1))>>16);}
  unsigned faultPc()const{return mode=="output-alias"?1:mode=="reset-recovery"?0:mode=="gate-write-error"?3:6;}
  unsigned status()const{return mode=="pass"?0:mode=="output-alias"?9:3;}
  uint64_t expectedBytes(unsigned index)const{uint64_t n=0;const auto&c=commands[index];for(unsigned j=0;j<c.spanCount;j++)n+=spans[c.spanFirst+j].bytes;return n;}
  Span& spanAt(uint64_t a,uint64_t n){for(auto&s:spans)if(inside(a,n,s.begin,s.bytes))return s;throw std::runtime_error("access outside active physical output");}
  void load(const fs::path&path,uint64_t address,uint64_t bytes){
    require(inside(address,bytes,base,limit-base),"input allocation");std::ifstream f(path,std::ios::binary|std::ios::ate);
    require(bool(f)&&uint64_t(f.tellg())==bytes,"input bytes "+path.string());f.seekg(0);f.read((char*)(mem->words.data()+mem->index(address)),bytes);require(bool(f),"input read");
  }
  void dump(const std::string&name,const void*data,uint64_t bytes){require(!fs::exists(out/name),"stale artifact "+name);std::ofstream f(out/name,std::ios::binary);f.write((const char*)data,bytes);require(bool(f),"artifact write");}
  Chain(const fs::path&fixture,const fs::path&output,std::string selected):mode(std::move(selected)),out(output){
    require(mode=="pass"||mode=="last-write-error"||mode=="activation-read-error"||mode=="weight-read-error"||mode=="gate-write-error"||mode=="output-alias"||mode=="reset-recovery","unknown mode");
    std::ifstream f(fixture/"launch.txt");std::string magic;f>>magic;
    f>>base>>limit>>cb>>cl>>db>>dl>>meta>>scratch>>aa>>rows>>first>>count>>position>>trig>>trigTokens>>gammaQ>>gammaK;
    require(bool(f)&&magic=="HOST_QKV_ROPE_V1"&&rows==128&&count==1&&(first==0||first==127)&&position==(first?255:0),"bounded launch window");
    commands.resize(7);spans.resize(8);unsigned records=0;
    for(auto&c:commands){f>>c.name>>c.engine>>c.records>>c.signal>>c.input>>c.inputBytes>>c.constant>>c.constantBytes>>c.spanFirst>>c.spanCount;records+=c.records;}
    for(auto&s:spans){f>>s.name>>s.pc>>s.allocation>>s.allocationBytes>>s.begin>>s.bytes;require(s.pc<7&&inside(s.begin,s.bytes,s.allocation,s.allocationBytes),"output span geometry");s.touched.resize(s.bytes);}
    std::string extra;require(bool(f)&&!(f>>extra)&&records==114&&cl-cb==128&&dl-db==1856,"launch inventory");
    mem=std::make_unique<host_test::PhysicalMemory>(base,limit);bus=std::make_unique<host_test::PhysicalAxi<VHostBlockTop,Chain>>(d,*this,*mem);
    load(fixture/"host_commands.bin",cb,cl-cb);load(fixture/"host_descriptors.bin",db,dl-db);load(fixture/"activation.bf16le",aa,rows*2048);
    for(unsigned j=0;j<3;j++)load(fixture/("weight_"+commands[j].name+".bf16le"),commands[j].constant,commands[j].constantBytes);
    load(fixture/"q_gamma.bf16le",gammaQ,512);load(fixture/"k_gamma.bf16le",gammaK,512);load(fixture/"trig.bf16le",trig+position*128,128);
    for(auto&s:spans){std::ifstream r(fixture/("independent_"+s.name+".bf16le"),std::ios::binary|std::ios::ate);require(bool(r)&&uint64_t(r.tellg())==s.bytes,"independent bytes");s.reference.resize(s.bytes/2);r.seekg(0);r.read((char*)s.reference.data(),s.bytes);require(bool(r),"independent read");}
    // Independently recompute the three projections; downstream terminals remain
    // pinned integer+C results of these exact input bytes, never memory initializers.
    for(unsigned j=0;j<3;j++){auto&c=commands[j];auto&s=spans[j];unsigned n=s.bytes/2;
      for(unsigned col=0;col<n;col++){float sum=0;for(unsigned k=0;k<1024;k++)sum=std::fma(fp(mem->half(c.input+k*2)),fp(mem->half(c.constant+(uint64_t(k)*n+col)*2)),sum);
        require(bf(sum)==s.reference[col],"canonical Dense differs from independent terminal");}}
    if(mode=="output-alias"){
      uint64_t addr=spans[0].begin-first*1024,record=db+39*16;
      auto put=[&](uint64_t a,uint8_t v){auto&u=mem->words[mem->index(a&~uint64_t(3))];auto sh=(a%4)*8;u=(u&~(255U<<sh))|(uint32_t(v)<<sh);};
      for(unsigned j=0;j<6;j++)put(record+7+j,uint8_t(addr>>(8*j)));put(record+15,uint8_t(addr>>48));
    }
    initial=mem->words;require(!fs::exists(out)||fs::is_empty(out),"output must be fresh");fs::create_directories(out);
    d.clock=0;d.reset=1;d.io_launch_valid=0;d.io_completion_ready=0;d.io_result_ready=0;
    for(unsigned i=0;i<6;i++)bus->step();d.reset=0;for(unsigned i=0;i<30;i++)bus->step();
  }
  void drive(){bool block=d.io_completion_valid&&holdRemaining>0;d.io_completion_ready=running&&!block&&bus->random()%4!=0;if(block)holdRemaining--;}
  void traffic(bool present){require(running||!present,"traffic without launch");require(!d.io_completion_valid||!present,"traffic during completion backpressure");}
  void readCheck(const Beat&b){
    require(pc<7,"read after chain");uint64_t bytes=b.total*64;const auto&c=commands[pc];
    bool table=inside(b.address,bytes,cb,cl-cb)||inside(b.address,bytes,db,dl-db);
    bool input=inside(b.address,bytes,c.input,c.inputBytes),constant=inside(b.address,bytes,c.constant,c.constantBytes);
    require(table||input||constant,"read outside current typed source ranges");
    if(table){require(b.total==1,"metadata burst");metadata++;}
    else if(input&&pc>=3){auto&s=spanAt(b.address,bytes);require(s.pc<pc&&commands[s.pc].published,"consumer before actual predecessor publication");
      commands[pc].dependencyReads+=bytes;
      std::cout<<"HOST_QKV_ROPE_READ_DEP run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" address="<<b.address<<" bytes="<<bytes<<" producer="<<s.pc<<"\n";}
  }
  void writeCheck(const Beat&b){require(pc<7&&b.mask==~uint64_t(0),"BF16 write strobe");auto&s=spanAt(b.address,64);require(s.pc==pc,"write to another command output");
    for(uint64_t i=b.address-s.begin;i<b.address-s.begin+64;i++)require(!s.touched[i],"duplicate physical output write");}
  void request(Beat&b){
    require(!faultAcknowledged,"new transaction after fault response");
    if(b.write){auto&c=commands[pc];c.accepted+=b.total*64;require(c.accepted<=expectedBytes(pc),"excess command writes");b.final=c.accepted==expectedBytes(pc);}
    if(!injected&&mode!="pass"&&mode!="output-alias"&&pc==faultPc()){
      auto&c=commands[pc];bool input=!b.write&&inside(b.address,b.total*64,c.input,c.inputBytes),constant=!b.write&&inside(b.address,b.total*64,c.constant,c.constantBytes);
      bool gate=b.write&&mode=="gate-write-error"&&inside(b.address,b.total*64,spans[4].begin,spans[4].bytes)&&b.address+b.total*64==spans[4].begin+spans[4].bytes;
      if((mode=="last-write-error"&&b.write&&b.final)||((mode=="activation-read-error"||mode=="reset-recovery")&&input)||(mode=="weight-read-error"&&constant)||gate){b.error=true;injected=true;}}
    if(b.write)std::cout<<"HOST_QKV_ROPE_WRITE_REQUEST run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" address="<<b.address<<" bytes="<<b.total*64<<" final="<<b.final<<"\n";
  }
  void readAcknowledged(const Beat&b){faultAcknowledged|=b.error;}
  void acknowledged(const Beat&b){faultAcknowledged|=b.error;auto&c=commands[pc];if(!b.error){auto&s=spanAt(b.address,b.total*64);for(uint64_t j=b.address-s.begin;j<b.address-s.begin+b.total*64;j++){require(!s.touched[j],"duplicate ACK");s.touched[j]=1;}c.acked+=b.total*64;ackBytes+=b.total*64;c.finalAcks+=b.final;}
    std::cout<<"HOST_QKV_ROPE_WRITE_ACK run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" address="<<b.address<<" bytes="<<b.total*64<<" error="<<b.error<<" final="<<b.final<<"\n";
  }
  void verifyMemory(){
    auto expected=initial;
    for(const auto&s:spans)for(uint64_t j=0;j<s.bytes;j+=2){require(s.touched[j]==s.touched[j+1],"partial BF16 ACK");if(s.touched[j]){uint64_t a=s.begin+j;unsigned shift=(a%4)*8;auto&word=expected[mem->index(a&~uint64_t(3))];word=(word&~(0xffffU<<shift))|(uint32_t(s.reference[j/2])<<shift);}}
    require(expected==mem->words,"physical output/reference, prior output, inactive allocation, input or guard drift");
  }
  void observe(){
    if(d.io_completion_valid){require(pc<7&&bus->drained(),"completion before last ACK");auto&c=commands[pc];uint64_t word=d.io_completion_bits;unsigned st=(word>>32)&255;
      require((word&((1ULL<<29)-1))==pc&&((word>>29)&7)==c.engine&&(word>>40)==c.signal,"completion identity");
      require(!held||heldWord==word,"completion changed while blocked");heldWord=word;held=!d.io_completion_ready;
      bool success=mode=="pass"||pc<faultPc();require(st==(success?0:status()),"completion status");
      if(success){require(c.acked==expectedBytes(pc)&&c.accepted==c.acked&&c.finalAcks==1,"success before all primary/side ACK bytes");if(pc>=3)require(c.dependencyReads>=c.inputBytes,"missing actual predecessor reads");}
      else if(mode=="output-alias"||mode=="activation-read-error"||mode=="weight-read-error"||mode=="reset-recovery")
        require(c.accepted==0&&c.acked==0,"initial read fault or rejected alias wrote output");
      if(held)std::cout<<"HOST_QKV_ROPE_HOLD run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" word="<<word<<"\n";
      else{c.published=success;successful+=success;verifyMemory();dump("writable_after_command"+std::to_string(pc)+".bin",mem->words.data()+mem->index(scratch),limit-scratch);
        std::cout<<"HOST_QKV_ROPE_COMMAND run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" engine="<<c.engine<<" status="<<st<<" signal="<<c.signal<<" ack_bytes="<<c.acked<<" published="<<success<<"\n";pc++;holdRemaining=11;}
    }else require(!held,"completion withdrawn");
    if(d.io_result_valid)require(d.io_result_bits_status==status()&&d.io_result_bits_completed==successful&&d.io_result_bits_epoch==9+run&&d.io_result_bits_failedPc==(mode=="pass"?6:faultPc()),"result identity changed");
  }
  void launch(){running=true;uint64_t start=bus->ticks;
    std::cout<<"HOST_QKV_ROPE_BEGIN run="<<run<<" mode="<<mode<<" epoch="<<9+run<<" commands=7\n";
    d.io_launch_bits_commandBase=cb;d.io_launch_bits_commandLimit=cl;d.io_launch_bits_commands=7;d.io_launch_bits_descriptorBase=db;d.io_launch_bits_descriptorLimit=dl;d.io_launch_bits_descriptors=114;d.io_launch_bits_epoch=9+run;
#define REGION(i,b,l,r,w) d.io_launch_bits_regions_##i##_base=b;d.io_launch_bits_regions_##i##_limit=l;d.io_launch_bits_regions_##i##_read=r;d.io_launch_bits_regions_##i##_write=w
    REGION(0,base,meta,1,0);REGION(1,meta,scratch,1,0);REGION(2,scratch,limit,1,1);REGION(3,0,0,0,0);
#undef REGION
    require(d.io_launch_ready,"Host launch not ready");d.io_launch_valid=1;bus->step();d.io_launch_valid=0;d.io_launch_bits_epoch=99;d.io_launch_bits_commandBase=0;
    while(!d.io_result_valid&&bus->ticks-start<300000000ULL)bus->step();require(d.io_result_valid,"watchdog");
    unsigned expectedPc=mode=="pass"?7:faultPc()+1,jobs=mode=="output-alias"?1:expectedPc;uint64_t expectedMetadata=0,publishedBytes=0,macs=0;
    for(unsigned j=0;j<pc;j++)expectedMetadata+=1+commands[j].records;
    for(unsigned j=0;j<7;j++)if(commands[j].published){publishedBytes+=expectedBytes(j);if(j<3)macs+=(spans[j].bytes/2)*1024;}
    require(pc==expectedPc&&d.io_issuedJobs==jobs,"command/job lifecycle");require(bus->readBeats==bus->readAcks&&bus->writeBeats==bus->writeAcks,"AXI ACK counts");
    require(d.io_idmaTransfers==bus->readBursts+bus->writeBursts,"sole iDMA count");require(metadata==expectedMetadata&&d.io_memoryAccepted_0==metadata&&d.io_memoryReturned_0==metadata,"typed metadata ownership");
    require(d.io_writeBytes==publishedBytes&&d.io_usefulMacs==macs,"published byte/MAC count");require(bool(d.io_resetRequired)==(mode!="pass"),"reset lockout state");
    if(mode!="pass")require(injected||mode=="output-alias","fault never injected");
    verifyMemory();dump("ddr_after.bin",mem->words.data(),mem->words.size()*4);
    for(const auto&s:spans){dump("actual_"+s.name+".bf16le",mem->words.data()+mem->index(s.begin),s.bytes);dump("reference_"+s.name+".bf16le",s.reference.data(),s.bytes);}
    for(unsigned i=0;i<7;i++){bus->step();require(d.io_result_valid,"result withdrawn");std::cout<<"HOST_QKV_ROPE_RESULT_HOLD run="<<run<<" cycle="<<bus->ticks<<" epoch="<<unsigned(d.io_result_bits_epoch)<<" pc="<<unsigned(d.io_result_bits_failedPc)<<" status="<<unsigned(d.io_result_bits_status)<<" completed="<<successful<<"\n";}
    d.io_result_ready=1;bus->step();d.io_result_ready=0;running=false;
    if(mode!="pass"){auto transfers=d.io_idmaTransfers;d.io_launch_valid=1;for(unsigned i=0;i<10;i++){require(!d.io_launch_ready,"fault escaped reset lockout");bus->step();require(d.io_idmaTransfers==transfers,"work after poisoned result");}d.io_launch_valid=0;}
    std::cout<<"HOST_QKV_ROPE_END run="<<run<<" status="<<status()<<" epoch="<<9+run<<" result_pc="<<expectedPc-1<<" completions="<<pc<<" successful="<<successful<<" issued_jobs="<<jobs<<" metadata_reads="<<metadata<<" read_beats="<<bus->readBeats<<" read_ack_beats="<<bus->readAcks<<" write_beats="<<bus->writeBeats<<" write_ack_beats="<<bus->writeAcks<<" ack_bytes="<<ackBytes<<" published_bytes="<<publishedBytes<<" useful_macs="<<macs<<" idma_transfers="<<d.io_idmaTransfers<<" read_bursts="<<bus->readBursts<<" write_bursts="<<bus->writeBursts<<" reset_required="<<(d.io_resetRequired?1:0)<<"\n";
  }
  void recover(){require(mode=="reset-recovery"&&successful==0&&ackBytes==0&&mem->words==initial&&bus->drained(),"recovery DDR was modified");
    d.reset=1;for(unsigned i=0;i<6;i++)bus->step();d.reset=0;for(unsigned i=0;i<30;i++)bus->step();require(d.io_launch_ready&&!d.io_resetRequired,"reset did not recover");
    bus->clearCounts();pc=successful=0;metadata=ackBytes=0;holdRemaining=11;held=injected=faultAcknowledged=false;
    for(auto&c:commands){c.accepted=c.acked=c.finalAcks=c.dependencyReads=0;c.published=false;}
    mode="pass";run++;out/="recovery";fs::create_directory(out);launch();
    std::cout<<"HOST_QKV_ROPE_RECOVERY same_dut=1 unchanged_ddr=1 reference_injection=0 commands=7\n";
  }
};
int main(int argc,char**argv){try{require(argc==3||argc==4,"FIXTURE OUTPUT [mode]");std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);
  std::string mode=argc==4?argv[3]:"pass";auto c=std::make_unique<Chain>(argv[1],argv[2],mode);c->launch();if(mode=="reset-recovery")c->recover();return 0;
}catch(const std::exception&e){std::cerr<<"HOST_QKV_ROPE_FAIL: "<<e.what()<<"\n";return 1;}}
