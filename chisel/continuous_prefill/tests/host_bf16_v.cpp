// SPDX-License-Identifier: Apache-2.0
// Actual production HostBlockTop. The only provided service is AXI DDR.
// Canonical sequential-K std::fma reference is computed before Host launch.
#include "VHostBlockTop.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
static void check(bool ok,const std::string&why){if(!ok)throw std::runtime_error(why);}
static uint32_t bits(float x){uint32_t u;std::memcpy(&u,&x,4);return u;}
static float fp(uint32_t u){float x;std::memcpy(&x,&u,4);return x;}
static uint16_t rne(float x){uint32_t u=bits(x);return uint16_t((u+0x7fff+((u>>16)&1))>>16);}
struct Beat {bool valid=false,write=false,error=false,last=true;uint64_t address=0,id=0,mask=0;unsigned delay=0,total=1,remaining=1;std::array<uint32_t,16> data{};};
class Test {
 public:
 VHostBlockTop d;uint64_t base,limit,cb,cl,commands,db,dl,descriptors,meta,scratch,aa,bb,dd,rows,first,count;
 std::vector<uint32_t> mem,initial;std::vector<uint16_t> reference,native;
 std::vector<Beat> collected,committing;Beat pending,aw,heldAr,heldAw,heldW;
 bool arHeld=false,awHeld=false,wHeld=false,running=false,injected=false;
 uint32_t rng=91827;uint64_t ticks=0,reads=0,readAck=0,writeBeats=0,writeAck=0,writeBytes=0,readBursts=0,writeBursts=0,metadata=0;
 unsigned completed=0;std::string mode;std::filesystem::path out;
 Test(const std::filesystem::path&fixture,const std::filesystem::path&output,std::string m):mode(m),out(output){
  std::ifstream f(fixture/"launch.txt");f>>base>>limit>>cb>>cl>>commands>>db>>dl>>descriptors>>meta>>scratch>>aa>>bb>>dd>>rows>>first>>count;
  check(bool(f)&&count>0&&first+count<=rows,"fixture launch");mem.resize((limit-base)/4,0xa55ac33cU);
  load(fixture/"host_commands.bin",cb,cl-cb);load(fixture/"host_descriptors.bin",db,dl-db);
  load(fixture/"activation.bf16le",aa,rows*2048);load(fixture/"weight.bf16le",bb,1024*512*2);
  native.resize(rows*512);std::ifstream n(fixture/"native_v.bf16le",std::ios::binary);n.read((char*)native.data(),native.size()*2);check(bool(n),"native file");
  initial=mem;reference.resize(count*512);
  for(unsigned row=0;row<count;row++)for(unsigned col=0;col<512;col++){
   float sum=0;for(unsigned k=0;k<1024;k++)sum=std::fma(fp(uint32_t(half(aa,(first+row)*1024+k))<<16),fp(uint32_t(half(bb,k*512+col))<<16),sum);
   check(std::isfinite(sum)&&((bits(sum)&0x7fffffffU)<0x7f7f8000U),"reference nonfinite");reference[row*512+col]=rne(sum);
  }
  std::filesystem::create_directories(out);d.clock=0;d.reset=1;d.io_launch_valid=0;d.io_completion_ready=0;d.io_result_ready=0;
  for(unsigned i=0;i<6;i++)step();d.reset=0;for(unsigned i=0;i<30;i++)step();
 }
 size_t pos(uint64_t address)const{check(address>=base&&address<limit&&address%4==0,"DDR address");return (address-base)/4;}
 uint16_t half(uint64_t address,size_t i)const{return uint16_t(mem[pos(address)+i/2]>>((i%2)*16));}
 void load(const std::filesystem::path&p,uint64_t address,size_t bytes){std::ifstream f(p,std::ios::binary|std::ios::ate);check(bool(f)&&size_t(f.tellg())==bytes,"fixture bytes "+p.string());f.seekg(0);f.read((char*)(mem.data()+pos(address)),bytes);check(bool(f),"fixture read");}
 unsigned random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 static bool eq(const Beat&a,const Beat&b){return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data&&a.total==b.total&&a.last==b.last;}
 bool within(uint64_t x,uint64_t end,uint64_t lo,uint64_t hi)const{return lo<=x&&x<end&&end<=hi;}
 void readCheck(const Beat&b){auto end=b.address+64*b.total;
  bool table=within(b.address,end,cb,cl)||within(b.address,end,db,dl);
  bool act=within(b.address,end,aa+first*2048,aa+(first+count)*2048);
  bool weight=within(b.address,end,bb,bb+1024*512*2);
  check(table||act||weight,"read outside owned source window");if(table){check(b.total==1,"metadata burst");metadata++;}
 }
 void writeCheck(const Beat&b){check(b.mask==~0ULL,"BF16 write strobe");check(within(b.address,b.address+64,dd+first*1024,dd+(first+count)*1024),"write outside active D");}
 void fault(Beat&b){
  if(!injected&&((mode=="last-write-error"&&b.write&&b.address+64*b.total==dd+(first+count)*1024)||
     (mode=="activation-read-error"&&!b.write&&b.address>=aa&&b.address<aa+rows*2048))){b.error=true;injected=true;}
 }
 void step(){
  d.clock=0;d.io_completion_ready=random()%4!=0;
  d.io_axi_ar_ready=!pending.valid&&!aw.valid&&collected.empty()&&random()%4!=0;
  d.io_axi_aw_ready=!pending.valid&&!aw.valid&&random()%3!=0;
  d.io_axi_w_ready=!pending.valid&&collected.size()<16&&random()%4!=0;
  d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;
  d.io_axi_r_bits_id=pending.id;d.io_axi_r_bits_resp=pending.error?2:0;d.io_axi_r_bits_last=pending.remaining==1;
  d.io_axi_b_bits_id=pending.id;d.io_axi_b_bits_resp=pending.error?2:0;
  for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];d.eval();
  bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
  bool ack=(d.io_axi_r_valid&&d.io_axi_r_ready)||(d.io_axi_b_valid&&d.io_axi_b_ready),cf=d.io_completion_valid&&d.io_completion_ready;
  Beat a,b,c;
  if(d.io_axi_ar_valid){c.valid=true;c.address=d.io_axi_ar_bits_addr;c.id=d.io_axi_ar_bits_id;c.total=c.remaining=d.io_axi_ar_bits_len+1;
   check(c.total<=16&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1&&((c.address&4095)+64*c.total)<=4096,"AR fields");
   if(arHeld)check(eq(c,heldAr),"AR changed under backpressure");heldAr=c;arHeld=!ar;
  }else check(!arHeld,"AR withdrawn");
  if(d.io_axi_aw_valid){a.valid=true;a.address=d.io_axi_aw_bits_addr;a.id=d.io_axi_aw_bits_id;a.total=a.remaining=d.io_axi_aw_bits_len+1;
   check(a.total<=16&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1&&((a.address&4095)+64*a.total)<=4096,"AW fields");
   if(awHeld)check(eq(a,heldAw),"AW changed under backpressure");heldAw=a;awHeld=!af;
  }else check(!awHeld,"AW withdrawn");
  if(d.io_axi_w_valid){b.valid=true;b.write=true;b.mask=d.io_axi_w_bits_strb;b.last=d.io_axi_w_bits_last;for(unsigned i=0;i<16;i++)b.data[i]=d.io_axi_w_bits_data[i];
   if(wHeld)check(eq(b,heldW),"W changed under backpressure");heldW=b;wHeld=!wf;
  }else check(!wHeld,"W withdrawn");
  if(!running)check(!a.valid&&!b.valid&&!c.valid,"traffic without Host launch");
  if(af){aw=a;writeBursts++;}if(wf)collected.push_back(b);Beat next;
  if(aw.valid&&collected.size()==aw.total){
   check(!pending.valid&&!ar,"AXI overlap");next=collected.back();next.address=aw.address;next.id=aw.id;next.total=next.remaining=aw.total;
   for(unsigned i=0;i<aw.total;i++){check(collected[i].last==(i+1==aw.total),"WLAST");collected[i].address=aw.address+64*i;writeCheck(collected[i]);}
   committing=collected;collected.clear();aw={};writeBeats+=next.total;
  }else if(ar){check(!pending.valid,"overlap AR");next=c;readCheck(next);readBursts++;reads+=c.total;}
  if(next.valid){check(next.address%64==0,"unaligned AXI");next.delay=1+random()%7;
   if(!next.write)for(unsigned i=0;i<16;i++)next.data[i]=mem[pos(next.address)+i];
   if(next.write&&next.address+64*next.total==dd+(first+count)*1024)next.delay=53;
   fault(next);
  }
  if(d.io_completion_valid){check(!pending.valid&&!aw.valid&&collected.empty(),"completion before final memory ACK");
   auto word=d.io_completion_bits;unsigned status=(word>>32)&255;check((word&((1ULL<<29)-1))==0&&((word>>29)&7)==2&&(word>>40)==1,"completion identity");
   if(status==0)check(writeBytes==count*1024&&!injected,"success before exact ACKed bytes");
   if(cf){completed++;check((status==0)==(mode=="pass"),"unexpected completion status");}
  }
  d.clock=1;d.eval();ticks++;
  if(ack){if(pending.write){writeAck+=pending.total;if(!pending.error){for(const auto&w:committing)for(unsigned i=0;i<16;i++)mem[pos(w.address)+i]=w.data[i];writeBytes+=pending.total*64;}committing.clear();}
   else readAck++;
   if(!pending.write&&pending.remaining>1){pending.address+=64;pending.remaining--;pending.delay=1+random()%7;pending.error=false;
    for(unsigned i=0;i<16;i++)pending.data[i]=mem[pos(pending.address)+i];fault(pending);
   }else pending={};
  }
  if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;d.clock=0;d.eval();
 }
 void launch(){
  running=true;
  d.io_launch_bits_commandBase=cb;d.io_launch_bits_commandLimit=cl;d.io_launch_bits_commands=commands;
  d.io_launch_bits_descriptorBase=db;d.io_launch_bits_descriptorLimit=dl;d.io_launch_bits_descriptors=descriptors;d.io_launch_bits_epoch=9;
  d.io_launch_bits_regions_0_base=base;d.io_launch_bits_regions_0_limit=meta;d.io_launch_bits_regions_0_read=1;d.io_launch_bits_regions_0_write=0;
  d.io_launch_bits_regions_1_base=meta;d.io_launch_bits_regions_1_limit=scratch;d.io_launch_bits_regions_1_read=1;d.io_launch_bits_regions_1_write=0;
  d.io_launch_bits_regions_2_base=scratch;d.io_launch_bits_regions_2_limit=limit;d.io_launch_bits_regions_2_read=1;d.io_launch_bits_regions_2_write=1;
  d.io_launch_bits_regions_3_base=0;d.io_launch_bits_regions_3_limit=0;d.io_launch_bits_regions_3_read=0;d.io_launch_bits_regions_3_write=0;
  check(d.io_launch_ready,"Host not ready");d.io_launch_valid=1;step();d.io_launch_valid=0;
  // Pins are not live configuration after admission.
  d.io_launch_bits_epoch=99;d.io_launch_bits_commandBase=0;
  while(!d.io_result_valid&&ticks<100000000ULL)step();check(d.io_result_valid,"watchdog");
  check(completed==1&&d.io_result_bits_epoch==9&&d.io_issuedJobs==1,"Host lifecycle");
  check(reads==readAck&&writeBeats==writeAck,"AXI accounting");check(d.io_idmaTransfers==readBursts+writeBursts,"single iDMA transfer accounting");
  check(metadata==22&&d.io_memoryAccepted_0==22&&d.io_memoryReturned_0==22,"command/descriptor DDR ownership");
  for(size_t i=0;i<mem.size();i++){uint64_t address=base+i*4;if(address<dd+first*1024||address>=dd+(first+count)*1024)check(mem[i]==initial[i],"readonly/guard/unpublished window modified");}
  if(mode=="pass"){
   check(d.io_result_bits_status==0&&d.io_result_bits_completed==1&&!d.io_resetRequired,"success result");
   check(d.io_usefulMacs==count*512*1024&&d.io_writeBytes==count*1024,"Host byte/MAC accounting");
   double max=0,sum=0;uint64_t nativeDiff=0;
   for(size_t i=0;i<reference.size();i++){auto got=half(dd+first*1024,i);check(got==reference[i],"BF16 mismatch element "+std::to_string(i));
    auto want=native[first*512+i];double err=std::abs(double(fp(uint32_t(got)<<16))-fp(uint32_t(want)<<16));max=std::max(max,err);sum+=err;nativeDiff+=got!=want;
   }
   auto dump=[&](const char*name,const void*ptr,size_t bytes){std::ofstream f(out/name,std::ios::binary);f.write((const char*)ptr,bytes);check(bool(f),"output dump");};
   dump("actual.bf16le",mem.data()+pos(dd+first*1024),count*1024);dump("reference.bf16le",reference.data(),count*1024);
   bool nativePass=max<=0.03125&&sum/reference.size()<=0.005;
   if(!nativePass){std::cerr<<"NATIVE_V_OPERATOR_FAIL max_abs="<<max<<" mean_abs="<<sum/reference.size()<<"\n";}
   check(nativePass,"official native V operator thresholds");
   std::cout<<"HOST_BF16_V_PASS tokens="<<count<<" token_base="<<first<<" checked_bf16="<<reference.size()<<" canonical_bit_differences=0 native_bit_differences="<<nativeDiff
    <<" native_max_abs="<<max<<" native_mean_abs="<<sum/reference.size()<<" native_operator_gate="<<(nativePass?"PASS":"FAIL")<<" cycles="<<ticks<<" write_ack_bytes="<<writeBytes
    <<" metadata_reads="<<metadata<<" logical_matrix_engines=1 physical_matrix_slices=8 idma_instances=1 unchanged_guards=1\n";
  }else{check(injected&&d.io_result_bits_status!=0&&d.io_result_bits_completed==0&&d.io_resetRequired,"fault not closed");
   check(d.io_writeBytes==0,"failed output published");std::cout<<"HOST_BF16_V_FAULT_PASS mode="<<mode<<" status="<<unsigned(d.io_result_bits_status)<<" write_ack_bytes="<<writeBytes<<" published_bytes=0\n";
  }
  auto status=d.io_result_bits_status;for(unsigned i=0;i<7;i++){step();check(d.io_result_valid&&d.io_result_bits_status==status,"result backpressure");}
  d.io_result_ready=1;step();d.io_result_ready=0;
  if(mode!="pass"){auto transfers=d.io_idmaTransfers;d.io_launch_valid=1;for(unsigned i=0;i<10;i++){check(!d.io_launch_ready,"poison escaped");step();check(d.io_idmaTransfers==transfers,"work after fault");}}
 }
};
int main(int argc,char**argv){try{std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);check(argc>=3,"FIXTURE OUTPUT [pass|last-write-error|activation-read-error]");
 auto test=std::make_unique<Test>(argv[1],argv[2],argc>3?argv[3]:"pass");test->launch();return 0;
}catch(const std::exception&e){std::cerr<<"HOST_BF16_V_FAIL: "<<e.what()<<std::endl;return 1;}}
