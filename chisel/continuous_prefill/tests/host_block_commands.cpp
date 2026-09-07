// SPDX-License-Identifier: Apache-2.0
// The only service supplied to the DUT is AXI memory. The independent ordered
// oracle runs before launch and NEVER services a DUT read or modifies DDR.
#include "VHostBlockTop.h"
#include "verilated.h"
#include "owner_shape.h"
#include "owner_fixture.h"
#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#ifndef OWNER_MATRIX_MACS
#define OWNER_MATRIX_MACS 512
#endif
static_assert(OWNER_MATRIX_MACS==512 || OWNER_MATRIX_MACS==4096,"Matrix specification");
constexpr unsigned KV=KVHEADS*HD;
constexpr unsigned MATRIX_SLICES=OWNER_MATRIX_MACS/512;
#ifndef OWNER_STACK_FIXTURE
static constexpr unsigned LAYERS=1;
static unsigned ORACLE_LAYER=0;
#endif
static void check(bool b,const std::string& s){if(!b)throw std::runtime_error(s);}
static uint32_t bits(float f){uint32_t u;std::memcpy(&u,&f,4);return u;}
static float fp(uint32_t u){float f;std::memcpy(&f,&u,4);return f;}
static float bf(float f){uint32_t u=bits(f);return fp((u+0x7fff+((u>>16)&1))&0xffff0000);}
static float add(float a,float b){return a+b;} static float mul(float a,float b){return a*b;}
static float expneg(float x){x=std::abs(x);if(x>=80)return 0;float z=mul(x,float(1.0/std::log(2.0)));unsigned k=unsigned(z);float f=add(z,-float(k));float c[8];double fact=1;for(int i=0;i<8;i++){if(i)fact*=i;c[i]=float(std::pow(-std::log(2.0),i)/fact);}float y=c[7];for(int i=6;i>=0;i--)y=add(mul(y,f),c[i]);return mul(y,fp((127-k)<<23));}
struct Output {const char*name;uint64_t address,words;unsigned pc;};
#ifndef OWNER_STACK_FIXTURE
static const std::vector<Output> OUTPUTS={
 {"n0",A_N0,TOKENS*H,0},{"qraw",A_QRAW,TOKENS*H,1},{"qr",A_QR,TOKENS*H,2},{"q",A_Q,TOKENS*H,3},
 {"kraw",A_KRAW,TOKENS*KV,4},{"kr",A_KR,TOKENS*KV,5},{"k",A_K,TOKENS*KV,6},
 {"vraw",A_VRAW,TOKENS*KV,7},{"v",A_V,TOKENS*KV,8},{"cache_k",A_CACHE_K,TOKENS*KV,9},{"cache_v",A_CACHE_V,TOKENS*KV,9},
 {"att",A_ATT,TOKENS*H,12},{"o",A_O,TOKENS*H,13},{"r",A_R,TOKENS*H,14},{"n1",A_N1,TOKENS*H,15},
 {"gate",A_GATE,TOKENS*F,16},{"up",A_UP,TOKENS*F,17},{"act",A_ACT,TOKENS*F,18},{"down",A_DOWN,TOKENS*H,19},{"y",A_Y,TOKENS*H,20}};
#else
static const std::vector<Output> OUTPUTS={OWNER_OUTPUT_TABLE};
#endif
struct Beat {bool valid=false,write=false,error=false;uint64_t address=0,id=0,mask=0;unsigned delay=0;std::array<uint32_t,16> data{};};
class Test {
public:
 VHostBlockTop d;std::vector<uint32_t> mem;std::vector<float> oracle;std::vector<uint8_t> initialized;
 std::array<bool,64> published{};std::array<uint64_t,64> writeBytes{},readBeats{};
 uint64_t cycles=0,reads=0,writes=0,ackReads=0,ackWrites=0,metadata=0,stalls=0,delays=0,checked=0;
 uint32_t rng=20260907;unsigned completions=0,successful=0;
 // Request-local stimulus and fault knobs. These never write DUT internal state.
 unsigned requestEpoch=1,inputSalt=0,weightSalt=0,faultTargetPc=1;
 uint64_t dmaAtStart=0;std::array<uint64_t,2> acceptedAtStart{},returnedAtStart{};
 Beat pending,aw,w,heldAr,heldAw,heldW;bool arHeld=false,awHeld=false,wHeld=false;
 bool running=false;int errorPc=-1;std::string mode;bool injected=false;uint64_t readOnlyHash=0;std::filesystem::path out;
 Test(std::string m,std::filesystem::path p):mem((LIMIT-BASE)/4,0x7fc00001),oracle(mem.size(),0),initialized(mem.size(),0),mode(m),out(p){
   std::filesystem::create_directories(out);d.clock=0;d.reset=1;d.io_launch_valid=0;d.io_completion_ready=0;d.io_result_ready=0;
   for(int i=0;i<6;i++)step();d.reset=0;step();
 }
 size_t pos(uint64_t a)const{check(a>=BASE&&a<LIMIT,"physical address");return (a-BASE)/4;}
 void put(uint64_t a,size_t i,float f){check(!running,"Host write after launch");mem[pos(a)+i]=bits(f);oracle[pos(a)+i]=f;initialized[pos(a)+i]=1;}
 float get(uint64_t a,size_t i)const{return oracle[pos(a)+i];}
 void refput(uint64_t a,size_t i,float f){oracle[pos(a)+i]=f;}
 void dump(const std::string&name,const void*p,size_t n){auto file=out/name;check(!std::filesystem::exists(file),"refuse overwrite "+file.string());std::ofstream f(file,std::ios::binary);f.write((const char*)p,n);check(bool(f),"dump failure");}
 void load(std::filesystem::path path,uint64_t a,uint64_t bytes){std::ifstream f(path,std::ios::binary|std::ios::ate);check(bool(f)&&uint64_t(f.tellg())==bytes,"table size "+path.string());f.seekg(0);f.read((char*)(mem.data()+pos(a)),bytes);check(bool(f),"table read");for(size_t i=0;i<bytes/4;i++)initialized[pos(a)+i]=1;}
 void weight(uint64_t a,unsigned k,unsigned n,unsigned salt){salt+=weightSalt;for(unsigned i=0;i<k;i++)for(unsigned j=0;j<n;j++){uint32_t x=i*1664525u+j*1013904223u+salt*2654435761u;x^=x>>13;x*=2246822519u;put(a,size_t(i)*n+j,bf(float(int(x%31)-15)*(H>64?0.00390625f:0.015625f)));}}
 void norm(uint64_t a,uint64_t g,uint64_t dst){for(unsigned t=0;t<TOKENS;t++){float sum=0;for(unsigned i=0;i<H;i++){float x=get(a,size_t(t)*H+i);sum=add(sum,mul(x,x));}float inv=1.0f/std::sqrt(add(mul(sum,float(1.0/H)),1e-6f));for(unsigned i=0;i<H;i++)refput(dst,size_t(t)*H+i,bf(mul(mul(get(a,size_t(t)*H+i),inv),get(g,i))));}}
 void dense(uint64_t a,uint64_t w,uint64_t dst,unsigned K,unsigned N){std::vector<float>x(K);for(unsigned t=0;t<TOKENS;t++){for(unsigned k=0;k<K;k++)x[k]=bf(get(a,size_t(t)*K+k));for(unsigned n=0;n<N;n+=16){float sum[16]={};for(unsigned k=0;k<K;k++){const float*b=oracle.data()+pos(w)+size_t(k)*N+n;for(unsigned j=0;j<16;j++)sum[j]=std::fma(x[k],bf(b[j]),sum[j]);}for(unsigned j=0;j<16;j++)refput(dst,size_t(t)*N+n+j,sum[j]);}}}
 void bias(uint64_t a,uint64_t b,uint64_t dst,unsigned N){for(unsigned t=0;t<TOKENS;t++)for(unsigned n=0;n<N;n++)refput(dst,size_t(t)*N+n,add(get(a,size_t(t)*N+n),get(b,n)));}
 void rope(uint64_t a,uint64_t dst,unsigned heads){unsigned width=heads*HD;for(unsigned t=0;t<TOKENS;t++)for(unsigned h=0;h<heads;h++)for(unsigned j=0;j<HD/2;j++){size_t i=size_t(t)*width+h*HD+j;float x=get(a,i),y=get(a,i+HD/2),c=get(A_ROPE,size_t(t)*HD/2+j),s=get(A_ROPE,size_t(MAX_TOKENS)*HD/2+size_t(t)*HD/2+j);refput(dst,i,add(mul(x,c),-mul(y,s)));refput(dst,i+HD/2,add(mul(x,s),mul(y,c)));}}
 void attention(){std::vector<float>p(TOKENS);for(unsigned t=0;t<TOKENS;t++)for(unsigned h=0;h<HEADS;h++){unsigned kh=h/(HEADS/KVHEADS);float max=-INFINITY;for(unsigned k=0;k<=t;k++){float parts[16]={};for(unsigned j=0;j<HD;j++)parts[j%16]=std::fma(bf(get(A_Q,size_t(t)*H+h*HD+j)),bf(get(A_CACHE_K,size_t(k)*KV+kh*HD+j)),parts[j%16]);float sum=0;for(float x:parts)sum=add(sum,x);p[k]=mul(sum,float(1.0/std::sqrt(double(HD))));max=std::max(max,p[k]);}float sum=0;for(unsigned k=0;k<=t;k++){p[k]=expneg(add(p[k],-max));sum=add(sum,p[k]);}float inv=1.0f/sum;for(unsigned j=0;j<HD;j++){float sum=0;for(unsigned k=0;k<=t;k++)sum=std::fma(bf(mul(p[k],inv)),bf(get(A_CACHE_V,size_t(k)*KV+kh*HD+j)),sum);refput(A_ATT,size_t(t)*H+h*HD+j,sum);}}}
 void initialize(const std::filesystem::path&fixture){
   load(fixture/"host_commands.bin",COMMAND_BASE,COMMAND_LIMIT-COMMAND_BASE);load(fixture/"host_descriptors.bin",DESC_BASE,DESC_LIMIT-DESC_BASE);
   const unsigned savedSalt=weightSalt;
   for(unsigned layer=0;layer<LAYERS;layer++){
   ORACLE_LAYER=layer;weightSalt=savedSalt+17*layer;
   weight(A_WQ,H,H,1);weight(A_WK,H,KV,2);weight(A_WV,H,KV,3);weight(A_WO,H,H,4);weight(A_WG,H,F,5);weight(A_WU,H,F,6);weight(A_WD,F,H,7);
   for(unsigned i=0;i<H;i++){put(A_GAMMA0,i,bf(0.9f+(i%11)*0.015625f));put(A_GAMMA1,i,bf(1.0f+(i%7)*0.015625f));put(A_BQ,i,float(int(i%13)-6)*0.00390625f);}
   for(unsigned i=0;i<KV;i++){put(A_BK,i,float(int(i%7)-3)*0.0078125f);put(A_BV,i,float(int(i%9)-4)*0.00390625f);}
   for(unsigned t=0;t<MAX_TOKENS;t++)for(unsigned i=0;i<HD/2;i++){double angle=t/std::pow(1000000.0,2.0*i/HD);put(A_ROPE,size_t(t)*HD/2+i,float(std::cos(angle)));put(A_ROPE,size_t(MAX_TOKENS)*HD/2+size_t(t)*HD/2+i,float(std::sin(angle)));}
   if(layer==0)for(unsigned t=0;t<TOKENS;t++)for(unsigned i=0;i<H;i++)put(A_X,size_t(t)*H+i,float(int((i*37u+t*101u+73u+inputSalt*17u)%1021)-510)*0.00390625f);
   norm(A_X,A_GAMMA0,A_N0);dense(A_N0,A_WQ,A_QRAW,H,H);bias(A_QRAW,A_BQ,A_QR,H);rope(A_QR,A_Q,HEADS);
   dense(A_N0,A_WK,A_KRAW,H,KV);bias(A_KRAW,A_BK,A_KR,KV);rope(A_KR,A_K,KVHEADS);
   dense(A_N0,A_WV,A_VRAW,H,KV);bias(A_VRAW,A_BV,A_V,KV);
   for(size_t i=0;i<size_t(TOKENS)*KV;i++){refput(A_CACHE_K,i,get(A_K,i));refput(A_CACHE_V,i,get(A_V,i));}
   attention();dense(A_ATT,A_WO,A_O,H,H);for(size_t i=0;i<size_t(TOKENS)*H;i++)refput(A_R,i,add(get(A_X,i),get(A_O,i)));
   norm(A_R,A_GAMMA1,A_N1);dense(A_N1,A_WG,A_GATE,H,F);dense(A_N1,A_WU,A_UP,H,F);
   for(size_t i=0;i<size_t(TOKENS)*F;i++){float g=get(A_GATE,i),e=expneg(g),sig=1.0f/add(1.0f,e);sig=mul(sig,std::signbit(g)?e:1.0f);refput(A_ACT,i,mul(mul(sig,g),get(A_UP,i)));}
   dense(A_ACT,A_WD,A_DOWN,F,H);for(size_t i=0;i<size_t(TOKENS)*H;i++)refput(A_Y,i,add(get(A_R,i),get(A_DOWN,i)));
   std::cout<<"LAYER_WEIGHT_ID layer="<<layer<<" salt="<<weightSalt<<" wq="<<hashRange(A_WQ,uint64_t(H)*H*4)
     <<" wg="<<hashRange(A_WG,uint64_t(H)*F*4)<<" wd="<<hashRange(A_WD,uint64_t(F)*H*4)<<std::endl;
   }
   ORACLE_LAYER=0;weightSalt=savedSalt;
   auto mutateCmd=[&](unsigned pc,uint8_t op){mem[pos(COMMAND_BASE)+pc*4]=(mem[pos(COMMAND_BASE)+pc*4]&~255u)|op;};
   if(mode=="bad-first-op"){mutateCmd(0,0xff);errorPc=0;}
   if(mode=="missing-bias"){mutateCmd(2,0);errorPc=2;}
   if(mode=="wrong-softmax"){mutateCmd(11,0x30);errorPc=11;}
   if(mode=="wrong-dependency"){mem[pos(COMMAND_BASE)+4]&=0x00ffffffu;mem[pos(COMMAND_BASE)+4]|=uint32_t(99)<<24;errorPc=1;}
   if(mode=="descriptor-shape"){mem[pos(DESC_BASE)+4]=2u|(uint32_t(0xffffff)<<0);errorPc=0;}
   if(mode=="read-error"||mode=="write-error"||mode=="last-write-error"||mode=="command-read-error"||mode=="descriptor-read-error"){
     check(faultTargetPc<COMMANDS,"fault PC out of graph");errorPc=int(faultTargetPc);
   }
   dump("host_commands.bin",mem.data()+pos(COMMAND_BASE),COMMAND_LIMIT-COMMAND_BASE);dump("host_descriptors.bin",mem.data()+pos(DESC_BASE),DESC_LIMIT-DESC_BASE);
   dump("input_x.f32le",mem.data()+pos(A_X),TOKENS*H*4);
   readOnlyHash=hashRange(BASE,SCRATCH-BASE);
 }
 uint64_t hashRange(uint64_t a,uint64_t bytes)const{uint64_t h=1469598103934665603ULL;for(size_t i=0;i<bytes/4;i++)h=(h^mem[pos(a)+i])*1099511628211ULL;return h;}
 unsigned random(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
 static bool eq(const Beat&a,const Beat&b){return a.address==b.address&&a.id==b.id&&a.mask==b.mask&&a.data==b.data;}
 void checkRead(uint64_t a){check(a>=BASE&&a+64<=LIMIT,"read bounds");for(unsigned i=0;i<16;i++)check(initialized[pos(a)+i],"read unwritten word "+std::to_string(a));
   for(auto&o:OUTPUTS)if(a>=o.address&&a<o.address+o.words*4)check(published[o.pc],"consumer before completion pc="+std::to_string(o.pc));
   for(auto&t:ALLOCATIONS)if(t.virtualValue)check(a<t.address||a>=t.address+t.words*4,"materialized virtual attention input");
 }
 void checkWrite(const Beat&b){check(b.mask==~0ULL,"non-full FP32 write");bool allowed=false;for(auto&o:OUTPUTS)if(b.address>=o.address&&b.address+64<=o.address+o.words*4&&d.io_pc==o.pc)allowed=true;check(allowed,"write outside commanded output at pc="+std::to_string(d.io_pc));for(unsigned i=0;i<16;i++)check(!initialized[pos(b.address)+i],"duplicate owner write");}
 void compare(unsigned pc){uint64_t expected=0;for(auto&o:OUTPUTS)if(o.pc==pc){expected+=o.words*4;uint64_t diffs=0;for(size_t i=0;i<o.words;i++){check(initialized[pos(o.address)+i],"unwritten output");auto a=mem[pos(o.address)+i];auto b=bits(get(o.address,i));check(std::isfinite(fp(a))&&std::isfinite(fp(b)),"NaN or Inf");if(a!=b){if(diffs<2)std::cerr<<"MISMATCH "<<o.name<<"["<<i<<"] "<<std::hex<<a<<" != "<<b<<std::dec<<"\n";diffs++;}}
     std::cout<<"OWNER_TENSOR pc="<<pc<<" name="<<o.name<<" values="<<o.words<<" bit_differences="<<diffs<<" cycle="<<cycles<<std::endl;
     check(diffs==0,"numerical mismatch pc="+std::to_string(pc));checked+=o.words;
     dump(std::string(o.name)+"_actual.f32le",mem.data()+pos(o.address),o.words*4);dump(std::string(o.name)+"_reference.f32le",oracle.data()+pos(o.address),o.words*4);
   }
   check(writeBytes[pc]==expected,"early/short write completion pc="+std::to_string(pc));
   if(pc%21==10||pc%21==11){check(writeBytes[(pc/21)*21+12]==TOKENS*H*4,"fused event before PV writeback");for(auto&t:ALLOCATIONS)if(t.virtualValue)for(size_t i=0;i<t.words;i++)check(!initialized[pos(t.address)+i],"score/probability materialized");}
   published[pc]=true;
 }
 void step(){
   d.clock=0;d.io_completion_ready=random()%4!=0;
   d.io_axi_ar_ready=!pending.valid&&!aw.valid&&!w.valid&&random()%4!=0;
   d.io_axi_aw_ready=!pending.valid&&!aw.valid&&random()%3!=0;d.io_axi_w_ready=!pending.valid&&!w.valid&&random()%4!=0;
   d.io_axi_r_valid=pending.valid&&!pending.write&&pending.delay==0;d.io_axi_b_valid=pending.valid&&pending.write&&pending.delay==0;
   d.io_axi_r_bits_id=pending.id;d.io_axi_r_bits_resp=pending.error?2:0;d.io_axi_r_bits_last=1;d.io_axi_b_bits_id=pending.id;d.io_axi_b_bits_resp=pending.error?2:0;
   for(unsigned i=0;i<16;i++)d.io_axi_r_bits_data[i]=pending.data[i];d.eval();
   bool ar=d.io_axi_ar_valid&&d.io_axi_ar_ready,af=d.io_axi_aw_valid&&d.io_axi_aw_ready,wf=d.io_axi_w_valid&&d.io_axi_w_ready;
   bool ack=(d.io_axi_r_valid&&d.io_axi_r_ready)||(d.io_axi_b_valid&&d.io_axi_b_ready),cf=d.io_completion_valid&&d.io_completion_ready;
   Beat a,b,c;
   if(d.io_axi_ar_valid){c.valid=true;c.address=d.io_axi_ar_bits_addr;c.id=d.io_axi_ar_bits_id;check(d.io_axi_ar_bits_len==0&&d.io_axi_ar_bits_size==6&&d.io_axi_ar_bits_burst==1,"bad AR");if(arHeld)check(eq(c,heldAr),"AR unstable");heldAr=c;arHeld=!ar;}else check(!arHeld,"AR withdrawn");
   if(d.io_axi_aw_valid){a.valid=true;a.address=d.io_axi_aw_bits_addr;a.id=d.io_axi_aw_bits_id;check(d.io_axi_aw_bits_len==0&&d.io_axi_aw_bits_size==6&&d.io_axi_aw_bits_burst==1,"bad AW");if(awHeld)check(eq(a,heldAw),"AW unstable");heldAw=a;awHeld=!af;}else check(!awHeld,"AW withdrawn");
   if(d.io_axi_w_valid){b.valid=true;b.write=true;b.mask=d.io_axi_w_bits_strb;for(unsigned i=0;i<16;i++)b.data[i]=d.io_axi_w_bits_data[i];check(d.io_axi_w_bits_last,"bad WLAST");if(wHeld)check(eq(b,heldW),"W unstable");heldW=b;wHeld=!wf;}else check(!wHeld,"W withdrawn");
   if(!running)check(!a.valid&&!b.valid&&!c.valid,"DUT ran without Host launch");
   stalls+=(d.io_axi_ar_valid&&!ar)+(d.io_axi_aw_valid&&!af)+(d.io_axi_w_valid&&!wf);if(pending.valid&&pending.delay)delays++;
   if(af)aw=a;if(wf)w=b;Beat next;
   if(aw.valid&&w.valid){check(!pending.valid&&!ar,"AXI overlap");next=w;next.address=aw.address;next.id=aw.id;aw={};w={};writes++;}
   else if(ar){check(!pending.valid,"overlap AR");next=c;reads++;readBeats[d.io_pc]++;if(next.address<META_LIMIT)metadata++;}
   if(next.valid){check(next.address>=BASE&&next.address+64<=LIMIT&&(next.address&63)==0,"AXI bounds/alignment");next.delay=1+random()%5;if(next.write)checkWrite(next);else{checkRead(next.address);for(unsigned i=0;i<16;i++)next.data[i]=mem[pos(next.address)+i];}
     if(!injected&&d.io_pc==faultTargetPc){
       uint64_t last=0;for(const auto&o:OUTPUTS)if(o.pc==faultTargetPc)last=std::max(last,o.address+o.words*4-64);
       bool match=(mode=="read-error"&&!next.write&&next.address>=META_LIMIT)||
         (mode=="command-read-error"&&!next.write&&next.address>=COMMAND_BASE&&next.address<COMMAND_LIMIT)||
         (mode=="descriptor-read-error"&&!next.write&&next.address>=DESC_BASE&&next.address<DESC_LIMIT)||
         (mode=="write-error"&&next.write)||(mode=="last-write-error"&&next.write&&next.address==last);
       if(match){next.error=true;injected=true;std::cout<<"FAULT_INJECT pc="<<faultTargetPc<<" mode="<<mode<<" address="<<next.address<<" prior_write_bytes="<<writeBytes[faultTargetPc]<<std::endl;}
     }
   }
   if(d.io_completion_valid){check(!pending.valid&&!aw.valid&&!w.valid,"completion before memory drained");uint64_t word=d.io_completion_bits;unsigned stat=(word>>32)&255,owner=(word>>29)&7,pc=word&((1u<<29)-1);
     if(stat==0){check(pc==successful && (word>>40)==pc+1,"completion identity");unsigned localPc=pc%21;unsigned expected=(localPc==1||localPc==4||localPc==7||localPc==10||localPc==12||localPc==13||localPc==16||localPc==17||localPc==19)?2:(localPc==9?4:3);check(owner==expected,"wrong owner");}
     if(cf){completions++;if(stat==0){compare(pc);std::cout<<"OWNER_COMPLETION pc="<<pc<<" owner="<<owner<<" signal="<<(word>>40)<<" write_ack_bytes="<<writeBytes[pc]<<" cycle="<<cycles<<std::endl;successful++;}else{check(errorPc>=0&&int(pc)==errorPc,"unexpected completion error pc="+std::to_string(pc)+" status="+std::to_string(stat));std::cout<<"EXPECTED_ERROR pc="<<pc<<" status="<<stat<<std::endl;}}
   }
   d.clock=1;d.eval();cycles++;
   if(ack){if(pending.write){ackWrites++;if(!pending.error){for(unsigned i=0;i<16;i++){mem[pos(pending.address)+i]=pending.data[i];initialized[pos(pending.address)+i]=1;}writeBytes[d.io_pc]+=64;}}else ackReads++;pending={};}
   if(next.valid)pending=next;else if(pending.valid&&pending.delay)pending.delay--;d.clock=0;d.eval();
 }
 void launch(){
   dmaAtStart=d.io_idmaTransfers;acceptedAtStart={d.io_memoryAccepted_0,d.io_memoryAccepted_1};returnedAtStart={d.io_memoryReturned_0,d.io_memoryReturned_1};
   const auto priorJobs=d.io_issuedJobs;
   for(unsigned i=0;i<30;i++)step();check(reads==0&&writes==0&&d.io_issuedJobs==priorJobs,"uncommanded execution");running=true;
   d.io_launch_bits_commandBase=COMMAND_BASE;d.io_launch_bits_commandLimit=COMMAND_LIMIT;d.io_launch_bits_commands=COMMANDS;
   d.io_launch_bits_descriptorBase=DESC_BASE;d.io_launch_bits_descriptorLimit=DESC_LIMIT;d.io_launch_bits_descriptors=DESCRIPTORS;d.io_launch_bits_epoch=requestEpoch;
   d.io_launch_bits_regions_0_base=BASE;d.io_launch_bits_regions_0_limit=META_LIMIT;d.io_launch_bits_regions_0_read=1;d.io_launch_bits_regions_0_write=0;
   d.io_launch_bits_regions_1_base=META_LIMIT;d.io_launch_bits_regions_1_limit=SCRATCH;d.io_launch_bits_regions_1_read=1;d.io_launch_bits_regions_1_write=0;
   d.io_launch_bits_regions_2_base=SCRATCH;d.io_launch_bits_regions_2_limit=LIMIT;d.io_launch_bits_regions_2_read=1;d.io_launch_bits_regions_2_write=1;
   d.io_launch_bits_regions_3_base=0;d.io_launch_bits_regions_3_limit=0;d.io_launch_bits_regions_3_read=0;d.io_launch_bits_regions_3_write=0;
   check(d.io_launch_ready,"launch not ready");d.io_launch_valid=1;step();d.io_launch_valid=0;
   uint64_t max=4000000ULL+uint64_t(LAYERS)*uint64_t(TOKENS)*(uint64_t(H)*H*2+uint64_t(H)*KV*2+uint64_t(H)*F*3)*2+uint64_t(LAYERS)*uint64_t(TOKENS)*TOKENS*H*100;
   while(!d.io_result_valid&&cycles<max)step();check(d.io_result_valid,"watchdog pc="+std::to_string(d.io_pc));
   if(errorPc>=0){check(d.io_result_bits_status!=0&&d.io_result_bits_failedPc==unsigned(errorPc)&&d.io_resetRequired,"bad error result");check(successful==((unsigned(errorPc)%21>=10&&unsigned(errorPc)%21<=12)?unsigned(errorPc)-unsigned(errorPc)%21+10u:unsigned(errorPc)),"failed operation published success");
     if(mode.find("error")!=std::string::npos)check(injected,"fault not exercised");std::cout<<"HOST_BLOCK_FAULT_PASS mode="<<mode<<" pc="<<errorPc<<" prior_completions="<<successful<<" next_owner_not_started=1\n";
   }else{
     uint64_t values=0;for(auto&o:OUTPUTS)values+=o.words;
     check(d.io_result_bits_status==0&&successful==COMMANDS&&completions==COMMANDS&&d.io_result_bits_completed==COMMANDS,"not full command graph");
     check(checked==values&&d.io_issuedJobs==19*LAYERS,"incomplete numerical owner coverage");
     uint64_t mac=uint64_t(TOKENS)*(uint64_t(H)*H*2+uint64_t(H)*KV*2+uint64_t(H)*F*3)+uint64_t(TOKENS)*(TOKENS+1)*H;
     uint64_t denseSteps=((TOKENS+15)/16)*(uint64_t(H)*((H+31)/32)*2+uint64_t(H)*((KV+31)/32)*2+uint64_t(H)*((F+31)/32)*2+uint64_t(F)*((H+31)/32));
     uint64_t physical=(denseSteps+uint64_t(TOKENS)*(TOKENS+1)*H/16)*512;
     mac*=LAYERS;physical*=LAYERS;check(d.io_usefulMacs==mac&&d.io_executedMacs==physical,"MAC count");check(d.io_writeBytes==values*4,"write byte conservation");
     check(reads==ackReads&&writes==ackWrites&&reads+writes==d.io_idmaTransfers-dmaAtStart,"all memory crossed iDMA");
     check(d.io_memoryAccepted_0-acceptedAtStart[0]==d.io_memoryReturned_0-returnedAtStart[0]&&d.io_memoryAccepted_1-acceptedAtStart[1]==d.io_memoryReturned_1-returnedAtStart[1],"arbiter response balance");
     check(d.io_memoryAccepted_0-acceptedAtStart[0]==metadata&&d.io_memoryAccepted_1-acceptedAtStart[1]==reads+writes-metadata,"metadata/payload ownership");
     check(metadata==COMMANDS+DESCRIPTORS,"each command and descriptor fetched from DDR");
     check(hashRange(BASE,SCRATCH-BASE)==readOnlyHash,"readonly data modified");
     for(auto&t:ALLOCATIONS){for(unsigned i=0;i<16;i++)check(mem[pos(t.address)-16+i]==0x7fc00001,"guard overwritten");if(t.virtualValue)for(size_t i=0;i<t.words;i++)check(mem[pos(t.address)+i]==0x7fc00001,"virtual tensor materialized");}
     std::cout<<"HOST_BLOCK_ALL_OWNERS_PASS tokens="<<TOKENS<<" hidden="<<H<<" ffn="<<F<<" layers="<<LAYERS<<" host_commands="<<COMMANDS<<" completed="<<COMMANDS<<" owner_jobs="<<19*LAYERS<<" matrix_commands="<<9*LAYERS<<" sfu_commands="<<11*LAYERS<<" kv_commands="<<LAYERS<<" checked_fp32="<<checked<<" bit_differences=0 useful_macs="<<mac<<" executed_macs="<<physical<<" cycles="<<cycles<<" metadata_reads="<<metadata<<" read_bytes="<<reads*64<<" write_ack_bytes="<<writes*64<<" idma_transfers="<<(d.io_idmaTransfers-dmaAtStart)<<" request_stalls="<<stalls<<" response_delay_cycles="<<delays<<" host_intermediate_writes=0 legacy_block_launch=0 original_matrix_instances="<<MATRIX_SLICES<<" logical_matrix_engines=1 matrix_macs="<<OWNER_MATRIX_MACS<<" original_idma_instances=1 score_ddr_accesses=0 output_fnv64="<<std::hex<<hashRange(OUTPUTS.back().address,TOKENS*H*4)<<std::dec<<std::endl;
   }
   auto result=d.io_result_bits_status;for(unsigned i=0;i<5;i++){step();check(d.io_result_valid&&d.io_result_bits_status==result,"result not held");}d.io_result_ready=1;step();d.io_result_ready=0;
   if(errorPc>=0){const auto stoppedJobs=d.io_issuedJobs;const auto stoppedDma=d.io_idmaTransfers;
     d.io_launch_valid=1;for(unsigned i=0;i<10;i++){check(!d.io_launch_ready,"poison escaped");step();check(d.io_issuedJobs==stoppedJobs&&d.io_idmaTransfers==stoppedDma,"work after failed completion");}d.io_launch_valid=0;}
   check(d.io_result_bits_epoch==requestEpoch,"result epoch mismatch");
 }
};
int main(int argc,char**argv){try{std::fesetround(FE_TONEAREST);Verilated::commandArgs(argc,argv);check(argc>=3,"FIXTURE_DIR OUTPUT_DIR [MODE]");auto t=std::make_unique<Test>(argc>3?argv[3]:"pass",argv[2]);if(const char* seed=std::getenv("OWNER_RANDOM_SEED")){const auto n=std::stoull(seed);check(n>0&&n<=0xffffffffULL,"invalid seed");t->rng=uint32_t(n);}t->initialize(argv[1]);t->launch();return 0;}catch(const std::exception&e){std::cerr<<"HOST_BLOCK_FAIL: "<<e.what()<<std::endl;return 1;}}
