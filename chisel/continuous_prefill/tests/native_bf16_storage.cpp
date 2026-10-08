// SPDX-License-Identifier: Apache-2.0
// The DUT is the real StreamingDenseOwner and SRAMs. Matrix values and DDR
// responses below are injected protocol stimulus, not arithmetic/iDMA signoff.
#include "VNativeBf16StorageProbe.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <deque>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static void ck(bool ok, const std::string& s) { if (!ok) throw std::runtime_error(s); }
static constexpr uint64_t BASE=0x102000000ULL, A=BASE+0x380, B=BASE+0x103c0, D=BASE+0x303c0;
static uint16_t rne(uint32_t x) { return uint16_t((uint64_t(x)+0x7fff+((x>>16)&1))>>16); }
static const uint32_t patterns[]={0,0x80000000,1,0x00007fff,0x00008000,0x00008001,0x00018000,
  0x007f8000,0x007fffff,0x00800000,0x3f807fff,0x3f808000,0x3f818000,0xbf808000,0xbf818000,
  0x7f7f0000,0x7f7f7fff,0xff7f7fff,0x3f7fffff,0x80008000,0x80008001,0x80018000};
enum Fault { Good, AError, ATag, ALast, ANonfinite, BError, BTag, BLast, BNonfinite,
  FinalAckError, FinalAckTag, OverflowLast, NegativeOverflowLast, FloatMaxLast,
  ResultNanLast, ResultError, ResultLast, BadK, BadN, BadWriteBytes };
struct Read { bool valid=false; uint64_t address=0,tag=0; unsigned count=0,index=0,delay=0; };
struct Write { bool valid=false; uint64_t address=0,tag=0; unsigned count=0,delay=0; bool error=false,badTag=false;
  std::vector<std::array<uint32_t,16>> data; };
struct Case { unsigned m,n,k; Fault fault=Good; bool abf=true,bbf=true,dbf=true; };
struct Test {
 VNativeBf16StorageProbe d;
 bool burstMode, running=false, injected=false, groupActive=false, matrixComplete=false, abortSeen=false;
 bool expectHalfPause=false, heldStep=false; std::array<uint32_t,136> heldOperands{}; unsigned heldControl=0; unsigned m=0,n=0,k=0,seed=0,groupRow=0,nextGroupRow=0,contexts=0,groupSteps=0;
 bool abf=true,bbf=true,dbf=true; Fault fault=Good;
 Read rd; Write wr; std::deque<unsigned> results;
 std::vector<uint8_t> memory=std::vector<uint8_t>(1024*1024,0xa5);
 uint64_t cycles=0,readBeats=0,aReadBeats=0,bReadBeats=0,operandChecks=0,steps=0,groups=0;
 uint64_t writeRequests=0,acceptedBytes=0,committedBytes=0,halfPauses=0,finalAckWait=0,writeBoundarySplits=0;
 uint64_t totalCases=0,totalOperands=0,totalHalfPauses=0,totalAckWait=0,totalBytes=0,totalFaults=0;
 explicit Test(bool mode):burstMode(mode) { reset(); }
 size_t pos(uint64_t a) const { ck(a>=BASE&&a<BASE+memory.size(),"DDR address out of range");return a-BASE; }
 void put16(uint64_t a,uint16_t x){auto p=pos(a);memory[p]=x;memory[p+1]=x>>8;}
 void put32(uint64_t a,uint32_t x){for(unsigned j=0;j<4;j++)memory[pos(a)+j]=x>>(8*j);}
 uint32_t get32(uint64_t a) const {uint32_t x=0;for(unsigned j=0;j<4;j++)x|=uint32_t(memory[pos(a)+j])<<(8*j);return x;}
 uint16_t av(unsigned r,unsigned z) const {return uint16_t(0x0080+((r*173+z*37+seed*19)%0x7e70)) ^ uint16_t(((r+z+seed)&1)<<15);}
 uint16_t bv(unsigned z,unsigned c) const {return uint16_t(0x0080+((z*97+c*23+seed*31)%0x7e70)) ^ uint16_t(((z+c+seed)&1)<<15);}
 uint32_t value(unsigned r,unsigned c) const {
  // Legacy FP32 egress must continue to admit both signs of FP32 max finite.
  if(!dbf&&r+1==m&&c+1==n)return 0x7f7fffff;
  if(!dbf&&r+1==m&&c+2==n)return 0xff7fffff;
  return patterns[(uint64_t(r)*n+c+seed)%std::size(patterns)];
 }
 uint64_t extent() const {return uint64_t(m)*n*(dbf?2:4);}
 unsigned rowsIn(unsigned ctx) const {return std::min(16u,m-groupRow-16*ctx);}
 unsigned expectedStatus() const {
  if(fault==Good)return 0;
  if(fault==AError||fault==BError||fault==FinalAckError)return 3;
  if(fault==ANonfinite||fault==BNonfinite||fault==OverflowLast||fault==NegativeOverflowLast||fault==FloatMaxLast||fault==ResultNanLast)return 8;
  if(fault==BadK||fault==BadN||fault==BadWriteBytes)return 5;
  return 7;
 }
 bool aFault() const {return fault>=AError&&fault<=ANonfinite;}
 bool bFault() const {return fault>=BError&&fault<=BNonfinite;}
 bool outputFault() const {return fault>=OverflowLast&&fault<=ResultLast;}
 void reset() {
  running=false; rd={};wr={};results.clear();groupActive=false;matrixComplete=false;expectHalfPause=false;heldStep=false;
  d.clock=0;d.reset=1;d.io_job_valid=0;d.io_done_ready=0;
  for(unsigned i=0;i<5;i++)tick(); d.reset=0;tick(); ck(d.io_job_ready,"reset did not recover owner");
 }
 void makeResult(unsigned ctx) {
  for(unsigned r=0;r<16;r++)for(unsigned c=0;c<256;c++) {
   uint32_t x=(r<rowsIn(ctx)&&c<n)?value(groupRow+ctx*16+r,c):0x7fc00123U;
   if(outputFault()&&r+1==rowsIn(ctx)&&c+1==n) {
    if(fault==OverflowLast)x=0x7f7f8000;
    if(fault==NegativeOverflowLast)x=0xff7f8000;
    if(fault==FloatMaxLast)x=0x7f7fffff;
    if(fault==ResultNanLast)x=0x7fc01234;
   }
   d.io_resultData[r*256+c]=x;
  }
 }
 void checkStep() {
  ck(groupActive,"Matrix.step without group"); unsigned ctx=groupSteps%contexts,z=groupSteps/contexts;
  ck(z<k&&d.io_stepContext==ctx,"strict ascending K/context schedule violated");
  ck(bool(d.io_stepClear)==(z==0)&&bool(d.io_stepLast)==(z+1==k)&&bool(d.io_stepEmit)==(z+1==k),"step clear/last/emit");
  ck(bool(d.io_stepFinish)==(z+1==k&&ctx+1==contexts),"step finish");
  for(unsigned r=0;r<16;r++) {
   auto got=uint16_t(d.io_stepA[r/2]>>(16*(r%2)));
   auto want=r<rowsIn(ctx)?av(groupRow+16*ctx+r,z):0;
   ck(got==want,"A operand mismatch row="+std::to_string(groupRow+16*ctx+r)+" k="+std::to_string(z)+" got="+std::to_string(got)+" want="+std::to_string(want));operandChecks++;
  }
  for(unsigned c=0;c<256;c++) {
   auto got=uint16_t(d.io_stepB[c/2]>>(16*(c%2)));auto want=c<n?bv(z,c):0;
   ck(got==want,"B operand mismatch k="+std::to_string(z)+" col="+std::to_string(c));operandChecks++;
  }
  groupSteps++;steps++;if(z+1==k)results.push_back(ctx);
  if(groupSteps==contexts*k)matrixComplete=true;
 }
 void checkPayload(const std::array<uint32_t,16>& data,uint64_t addr) {
  for(unsigned i=0;i<16;i++) {
   uint64_t off=addr-D+4*i;uint32_t want;
   if(dbf){unsigned e=off/2;want=uint32_t(rne(value(e/n,e%n)))|uint32_t(rne(value((e+1)/n,(e+1)%n)))<<16;}
   else {unsigned e=off/4;want=value(e/n,e%n);}
   ck(data[i]==want,"RNE/packing mismatch at byte="+std::to_string(off)+" got="+std::to_string(data[i])+" want="+std::to_string(want));
  }
 }
 void beginWrite(uint64_t addr,uint64_t tag,unsigned count) {
  ck(running&&!wr.valid,"overlapping/unrequested store");ck(addr==D+acceptedBytes,"store address/order or tensor hole");
  ck(count>=1&&count<=16&&(addr&63)==0&&(addr&1023)+64*count<=1024,"store burst geometry");
  ck(addr+64*count<=D+extent(),"store exceeded output extent");
  unsigned rowBytes=n*(dbf?2:4);ck((addr-D)%rowBytes+64*count<=rowBytes,"store crossed row boundary");
  ck((tag>>32)==seed&&(uint32_t)tag==writeRequests,"write tag sequence");
  if(burstMode&&(addr&1023)+64*count==1024&&64*count<rowBytes-(addr-D)%rowBytes)writeBoundarySplits++;
  wr.valid=true;wr.address=addr;wr.tag=tag;wr.count=count;wr.delay=3;writeRequests++;acceptedBytes+=64*count;
  if(acceptedBytes==extent()){wr.delay=47;if(fault==FinalAckError){wr.error=true;injected=true;}if(fault==FinalAckTag){wr.badTag=true;injected=true;}}
 }
 void tick() {
  d.clock=0;
  d.io_burst_ready=!rd.valid&&cycles%5!=1;
  d.io_burstResponse_valid=rd.valid&&rd.delay==0;
  d.io_burstResponse_bits_tag=rd.tag;d.io_burstResponse_bits_last=rd.index+1==rd.count;d.io_burstResponse_bits_error=0;
  for(unsigned i=0;i<16;i++)d.io_burstResponse_bits_data[i]=rd.valid?get32(rd.address+rd.index*64+4*i):0;
  bool readInject=rd.valid&&!injected&&((rd.address<B&&aFault())||(rd.address>=B&&bFault()&&bReadBeats>=1));
  if(readInject) {
   if(fault==AError||fault==BError)d.io_burstResponse_bits_error=1;
   if(fault==ATag||fault==BTag)d.io_burstResponse_bits_tag^=1;
   if(fault==ALast||fault==BLast)d.io_burstResponse_bits_last=!d.io_burstResponse_bits_last;
   if(fault==ANonfinite||fault==BNonfinite)d.io_burstResponse_bits_data[15]=0x7f810000; // Poison native upper half.
  }
  d.io_memory_ready=!wr.valid&&cycles%7!=2;
  d.io_writeRequest_ready=!wr.valid&&cycles%7!=2;
  d.io_writeData_ready=wr.valid&&wr.data.size()<wr.count&&cycles%4!=0;
  bool ack=wr.valid&&wr.data.size()==wr.count&&wr.delay==0;
  d.io_response_valid=!burstMode&&ack; d.io_writeResponse_valid=burstMode&&ack;
  d.io_response_bits_tag=d.io_writeResponse_bits_tag=wr.tag^(wr.badTag?1:0);
  d.io_response_bits_error=d.io_writeResponse_bits_error=wr.error;
  for(unsigned i=0;i<16;i++)d.io_response_bits_data[i]=d.io_writeResponse_bits_data[i]=0;
  d.io_group_ready=cycles%3!=1;
  // Long enough stalls to fill the elastic FIFO, plus intermittent stalls.
  d.io_stepReady=cycles%29>=9&&cycles%7!=0;
  d.io_resultValid=!results.empty()&&cycles%5!=0;
  d.io_resultContext=results.empty()?0:results.front();d.io_resultLast=fault!=ResultLast;d.io_resultError=fault==ResultError;
  if(!results.empty())makeResult(results.front());
  d.io_matrixDone_valid=groupActive&&((matrixComplete&&results.empty())||abortSeen);
  d.io_matrixDone_bits_tag=seed;d.io_matrixDone_bits_error=0;
  d.eval();
  if(expectHalfPause&&!d.reset){ck(!d.io_burstResponse_ready&&!d.io_burst_valid&&!d.io_group_valid,"native A upper half did not backpressure external responses/requests");halfPauses++;}
  expectHalfPause=false;
  unsigned control=d.io_stepContext|(unsigned(d.io_stepClear)<<3)|(unsigned(d.io_stepLast)<<4)|
    (unsigned(d.io_stepEmit)<<5)|(unsigned(d.io_stepFinish)<<6);
  if(heldStep&&!d.reset&&!d.io_resetRequired){
   ck(d.io_stepValid&&control==heldControl,"Matrix step control changed under backpressure");
   for(unsigned i=0;i<8;i++)ck(d.io_stepA[i]==heldOperands[i],"A changed under Matrix backpressure");
   for(unsigned i=0;i<128;i++)ck(d.io_stepB[i]==heldOperands[i+8],"B changed under Matrix backpressure");
  }
  heldStep=!d.reset&&d.io_stepValid&&!d.io_stepReady&&!d.io_resetRequired;
  if(heldStep){heldControl=control;for(unsigned i=0;i<8;i++)heldOperands[i]=d.io_stepA[i];for(unsigned i=0;i<128;i++)heldOperands[i+8]=d.io_stepB[i];}
  if(wr.valid&&acceptedBytes==extent()&&wr.data.size()==wr.count&&wr.delay&&!d.reset) {
   ck(!d.io_done_valid,"completion before final write ACK");ck(d.io_done_bits_writeBytes==committedBytes,"bytes published before ACK");finalAckWait++;
  }
  bool readReq=d.io_burst_valid&&d.io_burst_ready;
  bool readResp=d.io_burstResponse_valid&&d.io_burstResponse_ready;
  bool scalar=d.io_memory_valid&&d.io_memory_ready;
  bool burstReq=d.io_writeRequest_valid&&d.io_writeRequest_ready;
  bool writeData=d.io_writeData_valid&&d.io_writeData_ready;
  bool writeAck=ack&&(burstMode?d.io_writeResponse_ready:d.io_response_ready);
  bool group=d.io_group_valid&&d.io_group_ready;
  bool step=d.io_stepValid&&d.io_stepReady;
  bool result=d.io_resultValid&&d.io_resultReady;
  bool done=d.io_matrixDone_valid&&d.io_matrixDone_ready;
  if(!d.reset) {
   if(group){ck(!groupActive,"overlapping Matrix groups");groupActive=true;groupRow=nextGroupRow;
    nextGroupRow+=std::min(80u,m-nextGroupRow);contexts=(nextGroupRow-groupRow+15)/16;groupSteps=0;matrixComplete=false;abortSeen=false;groups++;
    ck(d.io_group_bits_tag==seed&&d.io_group_bits_opcode==0x20&&d.io_group_bits_sliceMask==((1u<<((n+31)/32))-1),"Matrix group fields");
    ck(aReadBeats==uint64_t(nextGroupRow)*k*(abf?2:4)/64,"Matrix started before all A rows were fetched");}
   if(step)checkStep();
   if(result){if(outputFault())injected=true;results.pop_front();}
   if(d.io_matrixAbort){abortSeen=true;results.clear();}
   if(done){groupActive=false;matrixComplete=false;}
   if(scalar){ck(!burstMode&&d.io_memory_bits_write&&d.io_memory_bits_mask==~uint64_t(0),"scalar store routing/mask");
    beginWrite(d.io_memory_bits_address,d.io_memory_bits_tag,1);std::array<uint32_t,16> data{};
    for(unsigned i=0;i<16;i++)data[i]=d.io_memory_bits_data[i];checkPayload(data,wr.address);wr.data.push_back(data);}
   if(burstReq){ck(burstMode,"unexpected burst write");beginWrite(d.io_writeRequest_bits_address,d.io_writeRequest_bits_tag,d.io_writeRequest_bits_beats);}
   if(writeData){ck(burstMode&&wr.valid,"write data without descriptor");std::array<uint32_t,16> data{};
    for(unsigned i=0;i<16;i++)data[i]=d.io_writeData_bits_data[i];checkPayload(data,wr.address+wr.data.size()*64);
    ck(bool(d.io_writeData_bits_last)==(wr.data.size()+1==wr.count),"write LAST");wr.data.push_back(data);}
   if(readReq){ck(running&&!rd.valid,"overlapping read");auto addr=d.io_burst_bits_address;unsigned count=d.io_burst_bits_beats;
    bool isA=addr>=A&&addr<A+uint64_t(m)*k*(abf?2:4);
    bool isB=addr>=B&&addr<B+uint64_t(k)*n*(bbf?2:4);
    ck((isA||isB)&&count&&count<=16&&(addr&63)==0&&(addr&1023)+count*64<=1024,"read descriptor geometry");
    ck(addr+count*64<=(isA?A+uint64_t(m)*k*(abf?2:4):B+uint64_t(k)*n*(bbf?2:4)),"read exceeded tensor extent");
    if(isA)ck(addr==A+aReadBeats*64,"A DDR row/beat order");
    rd={true,addr,d.io_burst_bits_tag,count,0,2};}
   if(readResp){bool isA=rd.address<B;if(readInject)injected=true;
    if(isA){aReadBeats++;if(abf&&!d.io_burstResponse_bits_error&&!readInject&&!d.io_resetRequired)expectHalfPause=true;}else bReadBeats++;
    readBeats++;rd.index++;if(rd.index==rd.count)rd={};}
   if(writeAck){if(!wr.error&&!wr.badTag){for(unsigned b=0;b<wr.count;b++)for(unsigned i=0;i<16;i++)put32(wr.address+b*64+i*4,wr.data[b][i]);committedBytes+=64*wr.count;}wr={};}
  }
  d.clock=1;d.eval();cycles++;
  if(rd.valid&&rd.delay)rd.delay--;
  if(wr.valid&&wr.data.size()==wr.count&&wr.delay)wr.delay--;
  d.clock=0;d.eval();
 }
 void run(Case c) {
  ck(!running&&!rd.valid&&!wr.valid,"previous transaction undrained");m=c.m;n=c.n;k=c.k;fault=c.fault;abf=c.abf;bbf=c.bbf;dbf=c.dbf;seed=unsigned(totalCases)+1;
  injected=false;groupRow=nextGroupRow=contexts=groupSteps=0;groupActive=false;matrixComplete=false;abortSeen=false;expectHalfPause=false;heldStep=false;results.clear();
  cycles=readBeats=aReadBeats=bReadBeats=operandChecks=steps=groups=writeRequests=acceptedBytes=committedBytes=halfPauses=finalAckWait=writeBoundarySplits=0;
  std::fill(memory.begin(),memory.end(),0xa5);
  for(unsigned r=0;r<m;r++)for(unsigned z=0;z<k;z++){auto x=av(r,z);auto p=A+(uint64_t(r)*k+z)*(abf?2:4);if(abf)put16(p,x);else put32(p,uint32_t(x)<<16);}
  for(unsigned z=0;z<k;z++)for(unsigned col=0;col<n;col++){auto x=bv(z,col);auto p=B+(uint64_t(z)*n+col)*(bbf?2:4);if(bbf)put16(p,x);else put32(p,uint32_t(x)<<16);}
  d.io_job_bits_kind=1;d.io_job_bits_m=m;d.io_job_bits_n=n;d.io_job_bits_k=k;
  d.io_job_bits_a=A;d.io_job_bits_b=B;d.io_job_bits_c=0;d.io_job_bits_dst=D;d.io_job_bits_tag=seed;
  d.io_job_bits_activationBf16=abf;d.io_job_bits_weightBf16=bbf;d.io_job_bits_outputBf16=dbf;
  d.io_job_bits_writeBytes=extent()+(fault==BadWriteBytes?64:0);
  d.io_job_valid=1;d.io_done_ready=0;d.eval();ck(d.io_job_ready,"job not ready");running=true;tick();d.io_job_valid=0;
  while(!d.io_done_valid&&cycles<250000)tick();ck(d.io_done_valid,"owner timeout");
  ck(!rd.valid&&!wr.valid&&!groupActive&&results.empty(),"completion before external protocol drain");
  ck(d.io_done_bits_tag==seed,"completion tag");
  ck(d.io_done_bits_status==expectedStatus(),"status got="+std::to_string(d.io_done_bits_status)+" expected="+std::to_string(expectedStatus()));
  ck(d.io_done_bits_writeBytes==committedBytes,"completion acknowledged byte count");
  if(fault==Good){ck(!d.io_resetRequired&&committedBytes==extent(),"successful completion extent/reset");
   ck(d.io_done_bits_usefulMacs==uint64_t(m)*n*k,"useful MAC count");
   ck(steps==uint64_t((m+15)/16)*k&&operandChecks==steps*272,"operand coverage count");
   ck(aReadBeats==uint64_t(m)*k*(abf?2:4)/64,"native A footprint");
   ck(bReadBeats==groups*uint64_t(k)*n*(bbf?2:4)/64,"B footprint/reuse");
   ck(!abf||halfPauses==aReadBeats,"missing held-upper-half cycle");
   ck(finalAckWait>=40,"final ACK delay coverage missing");
   for(uint64_t off=0;off<extent();off+=4){std::array<uint32_t,16> data{};if(off%64==0){for(unsigned j=0;j<16;j++)data[j]=get32(D+off+j*4);checkPayload(data,D+off);}}
   if(burstMode&&n==256)ck(writeBoundarySplits>0,"no output 1-KiB boundary split exercised");
  }else{ck(d.io_resetRequired,"failed owner did not require reset");ck(injected||fault>=BadK,"fault was not injected");totalFaults++;
   if(bFault())ck(bReadBeats==17,"failed B burst did not drain through final beat");
   if(aFault()||bFault()||outputFault()||fault>=BadK)ck(writeRequests==0&&committedBytes==0,"bad input/tile wrote output before rejection");
   if(fault==FinalAckError||fault==FinalAckTag){ck(committedBytes<extent()&&acceptedBytes==extent(),"final ACK failure accounting");
    for(uint64_t off=committedBytes;off<extent();off++)ck(memory[pos(D+off)]==0xa5,"failed write response committed bytes");}
  }
  for(unsigned i=1;i<=64;i++)ck(memory[pos(D-i)]==0xa5,"leading output guard modified");
  for(unsigned i=0;i<64;i++)ck(memory[pos(D+extent()+i)]==0xa5,"trailing output guard modified");
  auto status=d.io_done_bits_status;auto bytes=d.io_done_bits_writeBytes;
  for(unsigned i=0;i<9;i++){tick();ck(d.io_done_valid&&d.io_done_bits_status==status&&d.io_done_bits_writeBytes==bytes,"unstable held completion");}
  d.io_done_ready=1;tick();d.io_done_ready=0;running=false;
  totalCases++;totalOperands+=operandChecks;totalHalfPauses+=halfPauses;totalAckWait+=finalAckWait;totalBytes+=committedBytes;
  std::cout<<"NATIVE_BF16_STORAGE_CASE_PASS burst="<<burstMode<<" case="<<totalCases<<" m="<<m<<" n="<<n<<" k="<<k<<" flags="<<abf<<bbf<<dbf<<" fault="<<int(fault)<<" status="<<unsigned(status)<<" operands="<<operandChecks<<" half_pauses="<<halfPauses<<" ack_wait="<<finalAckWait<<" acknowledged_bytes="<<committedBytes<<" cycles="<<cycles<<std::endl;
  if(fault!=Good){for(unsigned i=0;i<4;i++){tick();ck(!d.io_job_ready,"failed owner re-admitted before reset");}reset();}else ck(d.io_job_ready,"successful owner did not rearm");
 }
};
int main(int argc,char**argv){try {
 Verilated::commandArgs(argc,argv);ck(argc==2,"usage: probe burst_mode");auto t=std::make_unique<Test>(std::string(argv[1])=="1");
 for(auto c:std::vector<Case>{{1,32,64},{15,256,32},{16,256,64},{17,32,64},{80,256,32},{81,256,64},{128,32,64},
   {17,256,64,Good,false,false,false},{17,256,64,Good,true,true,false},{17,256,64,Good,false,true,true}})t->run(c);
 for(Fault f:{AError,ATag,ALast,ANonfinite,BError,BTag,BLast,BNonfinite,FinalAckError,FinalAckTag,
   OverflowLast,NegativeOverflowLast,FloatMaxLast,ResultNanLast,ResultError,ResultLast}){
  t->run({15,256,64,f});t->run({17,32,32}); // Fresh data verifies reset recovery, not just ready.
 }
 t->run({1,32,16,BadK});t->run({1,16,32,BadN,true,false,true});t->run({1,32,32,BadWriteBytes});t->run({1,32,32});
 std::cout<<"NATIVE_BF16_STORAGE_PROTOCOL_PASS burst="<<t->burstMode<<" cases="<<t->totalCases<<" faults="<<t->totalFaults<<" operand_checks="<<t->totalOperands<<" half_pauses="<<t->totalHalfPauses<<" final_ack_wait_cycles="<<t->totalAckWait<<" acknowledged_bytes="<<t->totalBytes<<" actual_controller=1 injected_matrix_results=1 real_idma=0 arithmetic_signoff=0\n";
 return 0;
}catch(const std::exception&e){std::cerr<<"NATIVE_BF16_STORAGE_FAIL: "<<e.what()<<std::endl;return 1;}}
