// SPDX-License-Identifier: Apache-2.0
// Actual production VHostBlockTop; two public launches, one physical DDR store.
// Expected files are audit-only. No cache/output/reference data are preloaded.
#include "VHostBlockTop.h"
#include "verilated.h"
#include "host_physical_axi.h"
#include "host_attention_block_prefix.h"
#include <algorithm>
#include <array>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <map>
#include <set>
using host_test::require;
using host_test::Beat;
namespace fs=std::filesystem;
static constexpr uint64_t ACK_BYTES=68608;
struct OutputSpan {
  std::string name; unsigned pc=0;
  uint64_t allocation=0,allocationBytes=0,begin=0,bytes=0;
  std::vector<uint8_t> reference,touched,physicallyWritten;
};
struct Command {
  std::string name;unsigned engine=0,records=0,signal=0;
  uint64_t input=0,inputBytes=0,constant=0,constantBytes=0,accepted=0,acked=0,finalAcks=0;
  bool published=false;
  std::set<uint64_t> reads;
};
struct Launch {
  uint64_t cb=0,cl=0,db=0,dl=0,rows=0,first=0,count=0,position=0,oldLength=0,oldGeneration=0,epoch=0;
  std::array<Command,22> commands;
  std::array<OutputSpan,21> spans;
};
class BlockPair {
 public:
  VHostBlockTop d;
  uint64_t base=0,limit=0,meta=0,scratch=0,cache=0,capacity=0;
  std::array<Launch,2> launches;
  std::unique_ptr<host_test::PhysicalMemory> mem;
  std::unique_ptr<host_test::PhysicalAxi<VHostBlockTop,BlockPair>> bus;
  attention_block_prefix::Recorder prefix;
  std::vector<uint32_t> initial;
  fs::path out;
  std::string mode;
  unsigned run=0,nextCompletion=0,completions=0,successful=0,holdRemaining=11;
  // This is an audit shadow inferred from accepted terminal completions. The
  // production top exposes no direct cache-generation/length observation port.
  unsigned inferredCommittedLength=0,inferredCommittedGeneration=0;
  uint64_t inferredFinalOutput=0;
  bool running=false,held=false,injected=false,faultAcknowledged=false,fenceAccepted=false;
  uint64_t heldWord=0,metadata=0,ackBytes=0,physicalBytes=0,transferBase=0,acceptedBase=0,returnedBase=0;
  static bool inside(uint64_t a,uint64_t n,uint64_t b,uint64_t size) {
    return n && a>=b && a+n>=a && b+size>=b && a+n<=b+size;
  }
  static bool safeName(const std::string& s) {return !s.empty()&&s[0]!='/'&&s.find("..") == std::string::npos;}
  Launch& l(){return launches[run];}
  unsigned executionPc()const{require(d.io_pc<22,"invalid physical execution pc");return d.io_pc;}
  bool failing()const{return run==1&&mode!="pass";}
  unsigned faultPc()const{return 20;}
  unsigned status()const{return failing()?3:0;}
  uint64_t expectedBytes(unsigned pc)const {uint64_t n=0;for(const auto&s:launches[run].spans)if(s.pc==pc)n+=s.bytes;return n;}
  OutputSpan& spanAt(uint64_t a,uint64_t n){for(auto&s:l().spans)if(inside(a,n,s.begin,s.bytes))return s;throw std::runtime_error("outside active physical output");}
  void dump(const std::string& name,const void* data,uint64_t bytes) {
    const auto root=out/(run?"carried1":"cold0");fs::create_directories(root);require(!fs::exists(root/name),"stale artifact");
    std::ofstream f(root/name,std::ios::binary);f.write((const char*)data,bytes);require(bool(f),"artifact write");
  }
  void load(const fs::path& fixture,const std::string& name,uint64_t address,uint64_t bytes) {
    require(safeName(name)&&inside(address,bytes,base,scratch-base),"readonly preload geometry");
    require(name.rfind("expected/",0)!=0&&name.rfind("reference/",0)!=0,"reference injection");
    std::ifstream f(fixture/name,std::ios::binary|std::ios::ate);
    require(bool(f)&&uint64_t(f.tellg())==bytes,"preload bytes: "+name);f.seekg(0);
    f.read((char*)(mem->words.data()+mem->index(address)),bytes);require(bool(f),"preload read");
  }
  BlockPair(const fs::path& fixture,const fs::path& output,const std::string& selected,uint64_t prefixCycles=0):prefix(prefixCycles),out(output),mode(selected) {
    require(mode=="pass"||mode=="final-residual-ack-error","unsupported mode");
    std::ifstream f(fixture/"launch.txt");std::string magic;f>>magic>>base>>limit>>meta>>scratch>>cache>>capacity;
    require(bool(f)&&magic=="HOST_ATTENTION_BLOCK_PAIR_V1"&&base>0xffffffffULL&&limit<=(1ULL<<56)&&meta==base+32768&&meta<scratch&&scratch==cache&&scratch<limit&&capacity==256,"physical aperture/contract");
    const uint32_t endian=1;require(*(const uint8_t*)&endian==1,"little-endian host required");
    mem=std::make_unique<host_test::PhysicalMemory>(base,limit);
    bus=std::make_unique<host_test::PhysicalAxi<VHostBlockTop,BlockPair>>(d,*this,*mem);
    unsigned preloads=0;f>>preloads;require(preloads==18,"preload inventory");
    std::map<std::string,uint64_t> allowed={
      {"cold0_commands.bin",384},{"carried1_commands.bin",384},
      {"cold0_descriptors.bin",4736},{"carried1_descriptors.bin",4736},
      {"input/cold0_hidden.bf16le",2048},{"input/cold1_hidden.bf16le",2048},
      {"input/weight_input_norm.bf16le",2048},{"input/weight_post_norm.bf16le",2048},
      {"input/weight_q_gamma.bf16le",512},{"input/weight_k_gamma.bf16le",512},
      {"input/weight_q.bf16le",1024*4096*2},{"input/weight_k.bf16le",1024*512*2},
      {"input/weight_v.bf16le",1024*512*2},{"input/weight_o.bf16le",2048*1024*2},
      {"input/weight_ffn_gate.bf16le",1024*3584*2},{"input/weight_ffn_up.bf16le",1024*3584*2},
      {"input/weight_down.bf16le",3584*1024*2},{"input/trig.bf16le",32768}};
    std::vector<std::pair<uint64_t,uint64_t>> loaded;
    for(unsigned i=0;i<preloads;i++) {
      std::string name;uint64_t address=0,bytes=0;f>>name>>address>>bytes;require(bool(f)&&address%64==0&&bytes%64==0,"preload alignment");
      require(allowed.count(name)&&allowed.at(name)==bytes,"only authenticated raw hidden and parameters may preload");allowed.erase(name);
      bool table=name.rfind("input/",0)!=0;
      require(table?inside(address,bytes,base,meta-base):inside(address,bytes,meta,scratch-meta),"metadata/source allocation separation");
      if(table){uint64_t expected=base+(name.rfind("carried1",0)==0?16384:0)+(name.find("descriptors")!=std::string::npos?4096:0);require(address==expected,"metadata table address");}
      for(auto [a,n]:loaded)require(!(address<a+n&&a<address+bytes),"preload overlap");loaded.push_back({address,bytes});load(fixture,name,address,bytes);
    }
    static const std::array<unsigned,22> records={12,21,21,21,15,12,12,12,11,13,9,13,12,13,12,12,13,13,12,13,12,12};
    static const std::array<unsigned,22> engines={3,2,2,2,3,3,3,3,4,2,3,2,3,2,3,3,2,2,3,2,3,3};
    static const std::array<std::string,21> names={"input_norm","q","k","v","norm_q","gate","norm_k","rope_q","rope_k","cache_k","cache_v","context","sigmoid_mul","o","residual1","post_norm","ffn_gate","ffn_up","silu_mul","down","residual2"};
    static const std::array<unsigned,21> pcs={0,1,2,3,4,4,5,6,7,8,8,11,12,13,14,15,16,17,18,19,20};
    static const std::array<unsigned,21> widths={1024,4096,512,512,2048,2048,512,2048,512,512,512,2048,2048,1024,1024,1024,3584,3584,3584,1024,1024};
    static const std::array<std::string,22> commandNames={"input_norm","q","k","v","norm_q","norm_k","rope_q","rope_k","append","qk","softmax","pv","sigmoid_mul","o","residual1","post_norm","ffn_gate","ffn_up","silu_mul","down","residual2","fence"};
    auto allocations=loaded;allocations.push_back({cache,capacity*2048});
    for(unsigned r=0;r<2;r++) {
      auto& x=launches[r];f>>x.cb>>x.cl>>x.db>>x.dl>>x.rows>>x.first>>x.count>>x.position>>x.oldLength>>x.oldGeneration>>x.epoch;
      require(bool(f)&&x.rows==1&&x.first==0&&x.count==1&&x.position==r&&x.oldLength==r&&x.oldGeneration==r&&x.epoch==9+r&&x.cb==base+r*16384&&x.db==x.cb+4096&&x.cl-x.cb==384&&x.dl-x.db==4736,"two-token launch contract");
      for(unsigned pc=0;pc<22;pc++){auto& c=x.commands[pc];f>>c.name>>c.engine>>c.records>>c.signal>>c.input>>c.inputBytes>>c.constant>>c.constantBytes;
        require(bool(f)&&c.name==commandNames[pc]&&c.engine==engines[pc]&&c.records==records[pc]&&c.signal==pc+1,"command inventory");}
      for(unsigned j=0;j<21;j++){auto& s=x.spans[j];f>>s.name>>s.pc>>s.allocation>>s.allocationBytes>>s.begin>>s.bytes;
        require(bool(f)&&s.name==names[j]&&s.pc==pcs[j]&&s.bytes==widths[j]*2&&inside(s.begin,s.bytes,s.allocation,s.allocationBytes)&&inside(s.allocation,s.allocationBytes,scratch,limit-scratch)&&s.begin%64==0&&s.bytes%64==0,"output span");
        if(j==9||j==10)require(s.allocation==cache&&s.allocationBytes==capacity*2048,"shared cache allocation");
        else {require(s.begin==s.allocation&&s.bytes==s.allocationBytes,"complete M1 output allocation");allocations.push_back({s.allocation,s.allocationBytes});}
        s.touched.resize(s.bytes);s.physicallyWritten.resize(s.bytes);s.reference.resize(s.bytes);
        std::ifstream ref(fixture/"expected"/(r?"carried1":"cold0")/(s.name+".bf16le"),std::ios::binary|std::ios::ate);
        require(bool(ref)&&uint64_t(ref.tellg())==s.bytes,"independent reference bytes");ref.seekg(0);ref.read((char*)s.reference.data(),s.bytes);require(bool(ref),"independent reference read");
      }
      require(x.spans[9].begin==cache+r*1024&&x.spans[10].begin==cache+capacity*1024+r*1024,"combined cache planes");
      require(x.spans[9].reference==x.spans[8].reference&&x.spans[10].reference==x.spans[3].reference,"independent append predecessor");
      for(unsigned i=0;i<21;i++)for(unsigned j=i+1;j<21;j++)require(!(x.spans[i].begin<x.spans[j].begin+x.spans[j].bytes&&x.spans[j].begin<x.spans[i].begin+x.spans[i].bytes),"active spans alias");
    }
    std::string extra;require(!(f>>extra),"trailing layout data");
    for(unsigned i=0;i<allocations.size();i++)for(unsigned j=i+1;j<allocations.size();j++){
      auto [a,n]=allocations[i];auto [b,k]=allocations[j];require(a+n<=b||b+k<=a,"metadata/source/output allocation overlap");}
    for(auto&a:launches[0].spans)for(auto&b:launches[1].spans)require(!(a.begin<b.begin+b.bytes&&b.begin<a.begin+a.bytes),"prior active output alias");
    initial=mem->words;require(!fs::exists(out),"fresh execution output required");fs::create_directories(out);
    d.clock=0;d.reset=1;d.io_launch_valid=0;d.io_completion_ready=0;d.io_result_ready=0;
    for(unsigned i=0;i<6;i++)step();d.reset=0;for(unsigned i=0;i<30;i++)step();
  }
  void step(){prefix.step(*bus,out);}
  // Observe existing public counters; no extra eval, clock, request or RNG draw.
  // Useful/executed reset on launch and include successful owner receipts only.
  // Pipeline/iDMA counters are cumulative and are differenced by the auditor.
  void macCounters(){
    std::cout<<" useful_macs="<<uint64_t(d.io_usefulMacs)<<" executed_macs="<<uint64_t(d.io_executedMacs)
      <<" wide_steps="<<uint64_t(d.io_pipelineIssues)<<" pipeline_stalls="<<uint64_t(d.io_pipelineStalls)
      <<" read_beats="<<bus->readBeats<<" read_ack_beats="<<bus->readAcks
      <<" write_beats="<<bus->writeBeats<<" write_ack_beats="<<bus->writeAcks;
  }
  void drive(){bool block=d.io_completion_valid&&holdRemaining>0;d.io_completion_ready=running&&!block&&bus->random()%4!=0;if(block)holdRemaining--;}
  void traffic(bool present){require(running||!present,"traffic without launch");require(!d.io_completion_valid||!present,"traffic during blocked/completing command");prefix.capture(*bus);}
  void readCheck(const Beat& b) {
    const unsigned pc=executionPc();auto& c=l().commands[pc];uint64_t n=b.total*64;
    bool table=inside(b.address,n,l().cb,l().cl-l().cb)||inside(b.address,n,l().db,l().dl-l().db);
    if(table){require(b.total==1,"metadata burst");metadata++;return;}
    bool input=inside(b.address,n,c.input,c.inputBytes),constant=inside(b.address,n,c.constant,c.constantBytes);
    require(input||constant,"read outside typed actual sources");
    if(pc==11&&constant){
      require(inside(b.address,n,cache,(l().oldLength+1)*1024)||inside(b.address,n,cache+capacity*1024,(l().oldLength+1)*1024),"inactive cache suffix read");
      require(l().commands[8].published,"GQA before successful append completion");
      for(uint64_t a=b.address;a<b.address+n;a+=64){
        bool proven=false;
        for(unsigned r=0;r<=run;r++)for(unsigned j=9;j<11;j++){auto& s=launches[r].spans[j];if(inside(a,64,s.begin,s.bytes)){
          require(std::all_of(s.touched.begin()+(a-s.begin),s.touched.begin()+(a-s.begin)+64,[](uint8_t v){return v==1;}),"cache read before actual append ACK");
          if(r<run)require(inferredCommittedLength>=r+1&&inferredCommittedGeneration>=r+1,"old cache before accepted fence");proven=true;}}
        require(proven,"cache read without physical producer");
      }
    } else if(inside(b.address,n,scratch,limit-scratch)){
      auto& s=spanAt(b.address,n);require(s.pc<pc&&l().commands[s.pc].published,"consumer before actual producer completion");
      require(std::all_of(s.touched.begin()+(b.address-s.begin),s.touched.begin()+(b.address-s.begin)+n,[](uint8_t v){return v==1;}),"consumer before successful physical producer ACK");
    }
    for(uint64_t a=b.address;a<b.address+n;a+=64)c.reads.insert(a);
    std::cout<<"HOST_ATTN_BLOCK_READ run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" address="<<b.address<<" bytes="<<n<<"\n";
  }
  void writeCheck(const Beat& b){auto& s=spanAt(b.address,64);require(s.pc==executionPc()&&b.mask==~uint64_t(0),"wrong physical output or partial strobe");
    for(uint64_t j=b.address-s.begin;j<b.address-s.begin+64;j++)require(!s.physicallyWritten[j],"duplicate physical output write");}
  void request(Beat& b){
    require(!faultAcknowledged,"transaction after fault ACK");unsigned pc=executionPc();
    if(b.write){auto& c=l().commands[pc];c.accepted+=b.total*64;require(c.accepted<=expectedBytes(pc),"excess owner writes");b.final=c.accepted==expectedBytes(pc);
      if(failing()&&!injected&&pc==faultPc()){
        auto& s=l().spans[20];
        if(inside(b.address,b.total*64,s.begin,s.bytes)&&b.address+b.total*64==s.begin+s.bytes){require(b.final,"fault is not final owner write");b.error=true;injected=true;}
      }
      std::cout<<"HOST_ATTN_BLOCK_WRITE_REQUEST run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" address="<<b.address<<" bytes="<<b.total*64<<" final="<<b.final<<"\n";
    }
  }
  void readAcknowledged(const Beat& b){require(!b.error,"unexpected read error");}
  void acknowledged(const Beat& b){unsigned pc=executionPc();auto& c=l().commands[pc];faultAcknowledged|=b.error;
    // Exercise the permitted worst case: a failing B response does not undo W
    // beats the target already stored. Copy ACTUAL collected bus data, never
    // independent reference data. The unchanged adapter commits successful B
    // responses itself, before this callback; its collection remains live here.
    require(bus->committing.size()==b.total,"missing actual W beats at B response");
    if(b.error)for(const auto& w:bus->committing){
      require(w.mask==~uint64_t(0),"partial failed-burst strobe");
      for(unsigned i=0;i<16;i++)mem->words[mem->index(w.address)+i]=w.data[i];
    }
    auto& s=spanAt(b.address,b.total*64);
    for(uint64_t j=b.address-s.begin;j<b.address-s.begin+b.total*64;j++){
      require(!s.physicallyWritten[j],"duplicate physical store");s.physicallyWritten[j]=1;
      if(!b.error){require(!s.touched[j],"duplicate successful B ACK");s.touched[j]=1;}
    }
    physicalBytes+=b.total*64;
    if(!b.error){c.acked+=b.total*64;c.finalAcks+=b.final;ackBytes+=b.total*64;}
    std::cout<<"HOST_ATTN_BLOCK_WRITE_ACK run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" address="<<b.address<<" bytes="<<b.total*64<<" error="<<b.error<<" final="<<b.final<<" physical_write=1\n";
  }
  void verifyMemory(){
    auto expected=initial;auto* bytes=(uint8_t*)expected.data();
    for(unsigned r=0;r<=run;r++)for(auto& s:launches[r].spans)for(uint64_t j=0;j<s.bytes;j++)if(s.physicallyWritten[j])bytes[s.begin-base+j]=s.reference[j];
    require(expected==mem->words,"full physical DDR mismatch: actual output, old output, cache suffix, internal scratch, input or guard");
  }
  void verifyReads(unsigned pc){
    auto& c=l().commands[pc];
    auto covered=[&](uint64_t a,uint64_t n){for(uint64_t b=a;b<a+n;b+=64)require(c.reads.count(b),"missing actual predecessor/cache reads");};
    if(pc!=11&&pc!=21){covered(c.input,c.inputBytes);covered(c.constant,c.constantBytes);}
    if(pc==11){covered(c.input,c.inputBytes);covered(cache,(l().oldLength+1)*1024);covered(cache+capacity*1024,(l().oldLength+1)*1024);}
  }
  void observe(){
    if(!running || (d.io_launch_valid&&d.io_launch_ready))return;
    require(uint64_t(d.io_writeBytes)<=ackBytes,"owner byte counter before successful physical ACK");
    if(d.io_completion_valid){
      require(bus->drained(),"completion before final physical ACK");uint64_t word=d.io_completion_bits;unsigned pc=word&((1ULL<<29)-1),st=(word>>32)&255;
      unsigned wanted=nextCompletion;
      require(pc==wanted&&pc<22,"completion ordering including fused-failure identity");auto& c=l().commands[pc];
      require(((word>>29)&7)==c.engine&&(word>>40)==c.signal,"completion identity");require(!held||heldWord==word,"completion changed under backpressure");
      heldWord=word;held=!d.io_completion_ready;bool success=!(failing()&&pc==faultPc());require(st==(success?0:3),"unexpected completion status");
      unsigned ownerPc=(pc>=9&&pc<=11)?11:pc;
      if(success&&pc!=21){auto& owner=l().commands[ownerPc];require(owner.acked==expectedBytes(ownerPc)&&owner.accepted==owner.acked&&owner.finalAcks==1,"completion before all owner primary/side ACKs");verifyReads(ownerPc);}
      if(pc==21){require(!failing()&&!fenceAccepted&&successful==21&&ackBytes==ACK_BYTES&&!d.io_result_valid&&!d.io_launch_ready,"early terminal fence/result/launch");}
      if(held){std::cout<<"HOST_ATTN_BLOCK_HOLD run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" word="<<word<<"\n";}
      else {
        c.published=success;successful+=success;completions++;nextCompletion=pc+1;
        if(pc==21){fenceAccepted=true;inferredCommittedLength=l().oldLength+1;inferredCommittedGeneration=l().oldGeneration+1;inferredFinalOutput=l().spans[20].begin;}
        verifyMemory();dump("writable_after_command"+std::to_string(pc)+".bin",mem->words.data()+mem->index(scratch),limit-scratch);
        std::cout<<"HOST_ATTN_BLOCK_COMMAND run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks<<" engine="<<c.engine<<" status="<<st<<" signal="<<c.signal<<" ack_bytes="<<c.acked<<" owner_pc="<<ownerPc<<" checkpoint_accepted="<<fenceAccepted<<"\n";
        std::cout<<"HOST_MAC_PROFILE_COMMAND run="<<run<<" pc="<<pc<<" cycle="<<bus->ticks;macCounters();std::cout<<"\n";
        holdRemaining=pc==20?37:11;
      }
    }else require(!held,"completion withdrawn while blocked");
    if(d.io_result_valid){
      require(d.io_result_bits_status==status()&&d.io_result_bits_completed==successful&&d.io_result_bits_epoch==l().epoch&&d.io_result_bits_failedPc==(failing()?faultPc():21),"result identity");
      require(fenceAccepted==!failing(),"result before terminal checkpoint acceptance");
    }
  }
  void launch(){
    require(run==0||(inferredCommittedLength==1&&inferredCommittedGeneration==1&&inferredFinalOutput==launches[0].spans[20].begin),"carried launch before accepted cold block fence");
    require(bus->drained(),"launch with outstanding transport");bus->clearCounts();metadata=ackBytes=physicalBytes=0;
    transferBase=d.io_idmaTransfers;acceptedBase=d.io_memoryAccepted_0;returnedBase=d.io_memoryReturned_0;
    nextCompletion=completions=successful=0;holdRemaining=11;held=fenceAccepted=faultAcknowledged=false;running=true;uint64_t start=bus->ticks;
    std::cout<<"HOST_ATTN_BLOCK_BEGIN run="<<run<<" mode="<<mode<<" epoch="<<l().epoch<<" commands=22 old_length="<<l().oldLength<<" old_generation="<<l().oldGeneration<<"\n";
    d.io_launch_bits_commandBase=l().cb;d.io_launch_bits_commandLimit=l().cl;d.io_launch_bits_commands=22;
    d.io_launch_bits_descriptorBase=l().db;d.io_launch_bits_descriptorLimit=l().dl;d.io_launch_bits_descriptors=296;d.io_launch_bits_epoch=l().epoch;
#define REGION(i,b,e,r,w) d.io_launch_bits_regions_##i##_base=b;d.io_launch_bits_regions_##i##_limit=e;d.io_launch_bits_regions_##i##_read=r;d.io_launch_bits_regions_##i##_write=w
    REGION(0,base,meta,1,0);REGION(1,meta,scratch,1,0);REGION(2,scratch,limit,1,1);REGION(3,0,0,0,0);
#undef REGION
    require(d.io_launch_ready,"Host launch not ready");d.io_launch_valid=1;
    // Boundary before accepting edge: END-BEGIN includes that edge and excludes
    // the constructor/reset and later deliberate seven-cycle result hold.
    std::cout<<"HOST_MAC_PROFILE_BEGIN run="<<run<<" cycle="<<start<<" wide_steps="<<uint64_t(d.io_pipelineIssues)
      <<" pipeline_stalls="<<uint64_t(d.io_pipelineStalls)<<" idma_transfers="<<uint64_t(d.io_idmaTransfers)<<"\n";
    step();require(d.io_usefulMacs==0&&d.io_executedMacs==0,"launch MAC counters did not reset");
    d.io_launch_valid=0;d.io_launch_bits_epoch=99;d.io_launch_bits_commandBase=0;
    while(!d.io_result_valid&&bus->ticks-start<300000000ULL)step();require(d.io_result_valid,"watchdog");
    std::cout<<"HOST_MAC_PROFILE_END run="<<run<<" cycle="<<bus->ticks<<" cycles="<<bus->ticks-start;
    macCounters();std::cout<<" idma_transfers="<<uint64_t(d.io_idmaTransfers)<<" status="<<unsigned(d.io_result_bits_status)<<"\n";
    unsigned failed=failing()?faultPc():21;unsigned expectedCompletions=failing()?21:22;
    unsigned expectedSuccess=failing()?20:22,jobs=19;
    uint64_t expectedMetadata=0;for(unsigned pc=0;pc<=failed;pc++)expectedMetadata+=1+l().commands[pc].records;
    uint64_t receiptBytes=0,macs=0;
    for(unsigned pc=0;pc<22;pc++)if(expectedBytes(pc)&&(!failing()||pc<failed)){receiptBytes+=expectedBytes(pc);if(pc>=1&&pc<=3)macs+=expectedBytes(pc)/2*1024;if(pc==13)macs+=2048*1024;if(pc==16||pc==17)macs+=1024*3584;if(pc==19)macs+=3584*1024;if(pc==11)macs+=(l().oldLength+1)*4096;}
    require(completions==expectedCompletions&&successful==expectedSuccess&&d.io_issuedJobs==jobs,"command/owner lifecycle");
    require(bus->readBeats==bus->readAcks&&bus->writeBeats==bus->writeAcks&&bus->drained(),"AXI drain/ACK counters");
    require(physicalBytes==bus->writeBeats*64&&ackBytes<=physicalBytes&&(!failing()||ackBytes<physicalBytes),"physical stores versus successful ACKs");
    require(uint64_t(d.io_idmaTransfers)-transferBase==bus->readBursts+bus->writeBursts,"sole iDMA count");
    require(metadata==expectedMetadata&&uint64_t(d.io_memoryAccepted_0)-acceptedBase==metadata&&uint64_t(d.io_memoryReturned_0)-returnedBase==metadata,"typed metadata ownership");
    require(d.io_writeBytes==receiptBytes&&d.io_usefulMacs==macs,"successful owner receipt counter");
    require(bool(d.io_resetRequired)==failing()&&(!failing()||injected),"fault/reset lockout");
    verifyMemory();dump("ddr_after.bin",mem->words.data(),mem->words.size()*4);
    for(auto& s:l().spans)dump("actual_"+s.name+".bf16le",mem->words.data()+mem->index(s.begin),s.bytes);
    for(unsigned i=0;i<7;i++){step();require(d.io_result_valid,"result withdrawn");std::cout<<"HOST_ATTN_BLOCK_RESULT_HOLD run="<<run<<" cycle="<<bus->ticks<<" epoch="<<l().epoch<<" pc="<<failed<<" status="<<status()<<" completed="<<successful<<"\n";}
    std::cout<<"HOST_ATTN_BLOCK_END run="<<run<<" status="<<status()<<" completions="<<completions<<" successful="<<successful<<" issued_jobs="<<jobs<<" metadata_reads="<<metadata<<" ack_bytes="<<ackBytes<<" physical_bytes="<<physicalBytes<<" receipt_bytes="<<receiptBytes<<" useful_macs="<<macs<<" read_beats="<<bus->readBeats<<" read_ack_beats="<<bus->readAcks<<" write_beats="<<bus->writeBeats<<" write_ack_beats="<<bus->writeAcks<<" read_bursts="<<bus->readBursts<<" write_bursts="<<bus->writeBursts<<" idma_transfers="<<uint64_t(d.io_idmaTransfers)-transferBase<<" checkpoint_accepted="<<fenceAccepted<<" inferred_length="<<inferredCommittedLength<<" inferred_generation="<<inferredCommittedGeneration<<" inferred_final_output="<<inferredFinalOutput<<" reset_required="<<unsigned(d.io_resetRequired)<<"\n";
    d.io_result_ready=1;step();d.io_result_ready=0;running=false;
    if(failing()){
      auto transfers=d.io_idmaTransfers;d.io_launch_valid=1;
      for(unsigned i=0;i<10;i++){require(!d.io_launch_ready,"fault escaped reset lockout");step();require(d.io_idmaTransfers==transfers,"work after poisoned result");}
      d.io_launch_valid=0;verifyMemory();
    }
  }
};
int main(int argc,char** argv){try{
  require(argc>=3&&argc<=5,"FIXTURE FRESH_OUTPUT [pass|final-residual-ack-error] [--diagnostic-prefix=37..65536]");
  std::string mode="pass";uint64_t prefixCycles=0;unsigned next=3;
  if(next<unsigned(argc)&&std::string(argv[next]).rfind("--",0)!=0)mode=argv[next++];
  if(next<unsigned(argc)){
    const std::string arg=argv[next++],key="--diagnostic-prefix=";
    require(arg.rfind(key,0)==0,"unsupported diagnostic option");prefixCycles=attention_block_prefix::cycleLimit(arg.substr(key.size()));
  }
  require(next==unsigned(argc),"unexpected driver argument");Verilated::commandArgs(argc,argv);
  auto p=std::make_unique<BlockPair>(argv[1],argv[2],mode,prefixCycles);p->launch();p->run=1;p->launch();
  require(!prefixCycles,"full run ended before diagnostic prefix limit");
  std::cout<<"HOST_ATTN_BLOCK_PAIR same_dut=1 resets_between_launches=0 reference_injection=0 cache_prefill=0 launches=2\n";return 0;
}catch(const attention_block_prefix::PrefixStop&){std::cout<<"HOST_ATTN_BLOCK_PREFIX numerical_acceptance=0\n";return 0;
}catch(const std::exception& e){std::cerr<<"HOST_ATTN_BLOCK_FAIL: "<<e.what()<<"\n";return 1;}}
