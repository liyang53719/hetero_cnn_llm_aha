// SPDX-License-Identifier: Apache-2.0
// Real HostBlockTop Dense0 -> Conv0 -> Dense1 -> Conv1 commands; only external service is physical DDR.
// No per-command memory buckets, expected fills, Matrix/SFU stubs or native injection.
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
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static void check(bool ok, const std::string &why) { if (!ok) throw std::runtime_error(why); }
static uint32_t bits(float x) { uint32_t u; std::memcpy(&u, &x, 4); return u; }
static float fp(uint32_t u) { float x; std::memcpy(&x, &u, 4); return x; }
static uint16_t rne(float x) { uint32_t u = bits(x); return uint16_t((u + 0x7fff + ((u >> 16) & 1)) >> 16); }
struct Beat {
  bool valid=false, write=false, error=false, last=true;
  uint64_t address=0, id=0, mask=0;
  unsigned delay=0, total=1, remaining=1;
  std::array<uint32_t,16> data{};
};
struct Operation {
  uint64_t token=0, dense=0, activation=0, weight=0, output=0, historyIn=0, historyOut=0;
  uint64_t records=0, wait=0, signal=0, destinationRoot=0;
  uint64_t ackBytes=0, acceptedBytes=0, finalAcks=0, outputAck=0, historyAck=0;
  bool completed=false;
  std::vector<uint16_t> reference, history, conv, native, independent, conditioned;
  uint64_t bytes() const { return 12288+(dense?0:49152); }
  uint64_t engine() const { return dense?2:3; }
  std::string name() const { return std::string(dense?"dense":"conv")+std::to_string(token); }
};
struct Metric {
  double max=0, sum=0; uint64_t differences=0, elements=0;
  void add(uint16_t actual, uint16_t target) {
    double error=std::abs(double(fp(uint32_t(actual)<<16))-fp(uint32_t(target)<<16));
    check(std::isfinite(error), "nonfinite native comparison");
    max=std::max(max,error); sum+=error; differences+=actual!=target; elements++;
  }
  double mean() const { check(elements>0,"empty native comparison"); return sum/elements; }
  bool pass() const { return max<=0.03125 && mean()<=0.005; }
};

class Test {
 public:
  VHostBlockTop d;
  uint64_t base=0, limit=0, cb=0, cl=0, commands=0, db=0, dl=0, descriptors=0;
  uint64_t meta=0, scratch=0, denseWeight=0, convWeight=0, initialHistory=0;
  std::vector<Operation> operations;
  // The sole memory store is indexed by actual physical address, independent of pc.
  std::vector<uint32_t> mem, initial;
  std::vector<Beat> collected, committing;
  Beat pending, aw, heldAr, heldAw, heldW;
  bool arHeld=false, awHeld=false, wHeld=false, running=false, injected=false;
  bool completionHeld=false; uint64_t heldCompletion=0;
  uint32_t rng=91827;
  uint64_t ticks=0, startTicks=0, reads=0, readAck=0, writeBeats=0, writeAck=0;
  uint64_t writeBytes=0, readBursts=0, writeBursts=0, metadata=0, completionBlocked=0;
  unsigned completions=0, successful=0, completionWait=11, runId=0;
  std::string mode; std::filesystem::path out;

  Test(const std::filesystem::path &fixture, const std::filesystem::path &output, std::string selected)
      : mode(std::move(selected)), out(output) {
    check(mode=="pass" || mode=="last-history-ack-error" || mode=="activation-read-error" ||
          mode=="weight-read-error" || mode=="output-alias" || mode=="reset-recovery", "unknown mode");
    std::ifstream launch(fixture/"launch.txt"); std::string magic; launch>>magic;
    launch>>base>>limit>>cb>>cl>>commands>>db>>dl>>descriptors>>meta>>scratch>>denseWeight>>convWeight>>initialHistory;
    check(bool(launch) && magic=="HOST_GDN_DENSE_CONV_V1" && commands==4 && descriptors==60 &&
          base<limit && (limit-base)%64==0,"fixture launch");
    operations.resize(commands); uint64_t recordTotal=0;
    for (unsigned pc=0; pc<commands; pc++) {
      auto &p=operations[pc];
      launch>>p.token>>p.dense>>p.activation>>p.weight>>p.output>>p.historyIn>>p.historyOut
            >>p.records>>p.wait>>p.signal>>p.destinationRoot;
      check(bool(launch) && p.token==pc/2 && p.dense==unsigned(pc%2==0) && p.wait==pc && p.signal==pc+1 &&
            p.records==(p.dense?12:18) && p.destinationRoot<descriptors,"operation binding");
      recordTotal+=p.records;
    }
    check(recordTotal==descriptors && cl-cb==64 && dl-db==960,"table geometry");
    std::string extra; check(!(launch>>extra),"unexpected launch fields");
    mem.resize((limit-base)/4,0xa55ac33cU);
    load(fixture/"host_commands.bin",cb,cl-cb); load(fixture/"host_descriptors.bin",db,dl-db);
    load(fixture/"weight_dense.bf16le",denseWeight,1024*6144*2);
    load(fixture/"weight_conv.bf16le",convWeight,6144*4*2);
    load(fixture/"initial_history.bf16le",initialHistory,6144*4*2);
    check(operations[1].activation==operations[0].output && operations[3].activation==operations[2].output &&
          operations[3].historyIn==operations[1].historyOut && operations[1].historyIn==initialHistory,"actual DMA dependency binding");
    for (auto &p:operations) {
      auto token=std::to_string(p.token);
      p.native=readWords(fixture/(std::string(p.dense?"native_dense":"native_output")+token+".bf16le"),6144);
      if (p.dense) {
        load(fixture/("activation"+token+".bf16le"),p.activation,2048);
        p.independent=readWords(fixture/("independent_dense"+token+".bf16le"),6144);
        p.reference.resize(6144);
        for (unsigned col=0; col<6144; col++) {
          float sum=0;
          for (unsigned k=0; k<1024; k++) sum=std::fma(fp(uint32_t(half(p.activation,k))<<16),fp(uint32_t(half(p.weight,k*6144+col))<<16),sum);
          check(std::isfinite(sum),"canonical Dense nonfinite"); p.reference[col]=rne(sum);
        }
        check(p.reference==p.independent,"C++ Dense differs from existing integer/C oracle");
      } else {
        p.reference=readWords(fixture/("expected_output"+token+".bf16le"),6144);
        p.conv=readWords(fixture/("expected_conv"+token+".bf16le"),6144);
        p.history=readWords(fixture/("expected_history"+token+".bf16le"),6144*4);
        p.conditioned=readWords(fixture/("conditioned_output"+token+".bf16le"),6144);
        // This computes comparison values only. It never writes expected data into physical DDR.
        verifyConvRecipe(p, operations[2*p.token].reference, p.token?operations[1].history:std::vector<uint16_t>(6144*4,0));
      }
    }
    if (mode=="output-alias") {
      // Dense1 D aliases still-live Conv0 output; malformed before launch.
      auto &p=operations[2]; uint64_t address=operations[1].output, record=db+p.destinationRoot*16;
      for (unsigned byte=0;byte<6;byte++) putByte(record+7+byte,uint8_t(address>>(8*byte)));
      putByte(record+15,uint8_t(address>>48));
    }
    initial=mem; // Inputs/constants remain readonly from this point onward.
    check(!std::filesystem::exists(out) || std::filesystem::is_empty(out),"output must be fresh");
    std::filesystem::create_directories(out);
    for (const auto &p:operations) dump("reference_"+p.name()+".bf16le",p.reference.data(),p.reference.size()*2);
    d.clock=0; d.reset=1; d.io_launch_valid=0; d.io_completion_ready=0; d.io_result_ready=0;
    for (unsigned i=0;i<6;i++) step(); d.reset=0; for (unsigned i=0;i<30;i++) step();
  }

  size_t pos(uint64_t address) const {
    check(address>=base && address<limit && address%4==0,"DDR physical address"); return (address-base)/4;
  }
  uint16_t half(uint64_t address,size_t index) const {
    check(address+index*2+2<=limit,"DDR BF16 bound");
    return uint16_t(mem[pos(address)+index/2]>>((index%2)*16));
  }
  void putByte(uint64_t address,uint8_t value) {
    auto index=pos(address&~uint64_t(3)); unsigned shift=(address%4)*8;
    mem[index]=(mem[index]&~(0xffU<<shift))|(uint32_t(value)<<shift);
  }
  void load(const std::filesystem::path &path,uint64_t address,size_t bytes) {
    check(address+bytes<=limit,"fixture physical bounds");
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    check(bool(file) && size_t(file.tellg())==bytes,"fixture bytes "+path.string());
    file.seekg(0); file.read((char *)(mem.data()+pos(address)),bytes); check(bool(file),"fixture read");
  }
  static std::vector<uint16_t> readWords(const std::filesystem::path &path,size_t words) {
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    check(bool(file) && size_t(file.tellg())==words*2,"reference file size "+path.string());
    std::vector<uint16_t> result(words); file.seekg(0); file.read((char *)result.data(),words*2);
    check(bool(file),"reference read"); return result;
  }
  void dump(const std::string &name,const void *data,size_t bytes) const {
    check(!std::filesystem::exists(out/name),"refuse stale output "+name);
    std::ofstream file(out/name,std::ios::binary); file.write((const char *)data,bytes); check(bool(file),"output dump "+name);
  }
  unsigned random() { rng^=rng<<13; rng^=rng>>17; rng^=rng<<5; return rng; }
  static bool equal(const Beat &a,const Beat &b) {
    return a.address==b.address && a.id==b.id && a.mask==b.mask && a.data==b.data && a.total==b.total && a.last==b.last;
  }
  static bool within(uint64_t x,uint64_t end,uint64_t lo,uint64_t hi) { return lo<=x && x<end && end<=hi; }
  uint64_t begin(const Operation &p) const { return p.output; }
  uint64_t end(const Operation &p) const { return p.output+12288; }
  uint64_t finalEnd(const Operation &p) const { return p.dense?end(p):p.historyOut+49152; }
  unsigned faultIndex() const { return mode=="output-alias"?2:mode=="reset-recovery"?0:commands-1; }
  bool outputRange(const Operation &p,uint64_t a,uint64_t b) const {
    return within(a,b,begin(p),end(p)) || (!p.dense && within(a,b,p.historyOut,p.historyOut+49152));
  }
  static float mul(float a,float b) { volatile float x=a*b; return x; }
  static float add(float a,float b) { volatile float x=a+b; return x; }
  static float silu(float x) {
    float e=0;
    if (std::abs(x)<80) {
      float t=mul(std::abs(x),float(1/std::log(2.0))); int k=int(t); float frac=add(t,-float(k));
      std::array<float,8> coeff{}; double factorial=1;
      for(unsigned i=0;i<8;i++) { if(i) factorial*=i; coeff[i]=float(std::pow(-std::log(2.0),i)/factorial); }
      float h=coeff[7]; for(int i=6;i>=0;i--) h=add(mul(h,frac),coeff[i]);
      e=mul(h,fp(uint32_t(127-k)<<23));
    }
    volatile float inv=1.0f/add(1.0f,e);
    return mul(mul(inv,(bits(x)>>31)?e:1.0f),x);
  }
  void verifyConvRecipe(const Operation &p,const std::vector<uint16_t> &raw,const std::vector<uint16_t> &past) const {
    for(unsigned c=0;c<6144;c++) {
      float sum=0;
      for(unsigned k=0;k<4;k++) {
        uint16_t sample=k==3?raw[c]:past[c*4+k+1];
        check(p.history[c*4+k]==sample,"frozen raw history recipe mismatch");
        sum=add(sum,mul(fp(uint32_t(sample)<<16),fp(uint32_t(half(p.weight,c*4+k))<<16)));
      }
      auto conv=rne(sum); float x=fp(uint32_t(conv)<<16);
      check(x>-80 && std::isfinite(x),"Conv unsupported numerical domain");
      check(conv==p.conv[c] && rne(silu(x))==p.reference[c],"independent C++ frozen Conv/SiLU recipe mismatch");
    }
  }
  void readCheck(const Beat &beat) {
    check(completions<commands,"read after all completions");
    const auto &p=operations[completions]; auto last=beat.address+64*beat.total;
    bool table=within(beat.address,last,cb,cl) || within(beat.address,last,db,dl);
    bool activation=within(beat.address,last,p.activation,p.activation+(p.dense?2048:12288));
    bool weight=within(beat.address,last,p.weight,p.weight+(p.dense?12582912:49152));
    bool history=!p.dense && p.token && within(beat.address,last,p.historyIn,p.historyIn+49152);
    check(table || activation || weight || history,"read outside actual command source spans");
    if(table) { check(beat.total==1,"metadata burst"); metadata++; }
    if(!p.dense && activation) check(operations[completions-1].completed,"Conv consumed unpublished actual Dense output");
    if(history) check(operations[1].completed,"Conv consumed unpublished actual prior history");
  }
  void writeCheck(const Beat &beat) {
    check(completions<commands,"write after all completions");
    check(beat.mask==~0ULL,"BF16 write strobe");
    check(outputRange(operations[completions],beat.address,beat.address+64),"write outside exact D/Hout spans or into gap");
  }
  void fault(Beat &beat) {
    if(injected || mode=="pass" || mode=="output-alias" || completions!=faultIndex()) return;
    const auto &p=operations[completions];
    bool activation=!beat.write && within(beat.address,beat.address+64,p.activation,p.activation+(p.dense?2048:12288));
    bool weight=!beat.write && within(beat.address,beat.address+64,p.weight,p.weight+(p.dense?12582912:49152));
    if((mode=="last-history-ack-error" && beat.write && beat.address+64*beat.total==finalEnd(p)) ||
       ((mode=="activation-read-error" || mode=="reset-recovery") && activation) ||
       (mode=="weight-read-error" && weight)) { beat.error=true; injected=true; }
  }
  void verifyMemory(unsigned through,bool allowPartial=false) const {
    for(const auto &p:operations) if(p.completed) {
      for(size_t i=0;i<p.reference.size();i++) check(half(p.output,i)==p.reference[i],"canonical/preserved "+p.name()+" element "+std::to_string(i));
      if(!p.dense) for(size_t i=0;i<p.history.size();i++) check(half(p.historyOut,i)==p.history[i],"canonical/preserved history");
    }
    for(size_t i=0;i<mem.size();i++) {
      uint64_t address=base+i*4; bool writable=false;
      for(unsigned index=0;index<commands;index++) {
        const auto &p=operations[index]; writable|=(p.completed || (allowPartial && index==through)) && outputRange(p,address,address+4);
      }
      if(!writable) check(mem[i]==initial[i],"readonly input, future output or physical guard modified");
    }
  }
  void step() {
    d.clock=0;
    bool hold=d.io_completion_valid && completionWait>0;
    d.io_completion_ready=!hold && random()%4!=0;
    if (hold) { completionWait--; completionBlocked++; }
    d.io_axi_ar_ready=!pending.valid && !aw.valid && collected.empty() && random()%4!=0;
    d.io_axi_aw_ready=!pending.valid && !aw.valid && random()%3!=0;
    d.io_axi_w_ready=!pending.valid && collected.size()<16 && random()%4!=0;
    d.io_axi_r_valid=pending.valid && !pending.write && pending.delay==0;
    d.io_axi_b_valid=pending.valid && pending.write && pending.delay==0;
    d.io_axi_r_bits_id=pending.id; d.io_axi_r_bits_resp=pending.error?2:0; d.io_axi_r_bits_last=pending.remaining==1;
    d.io_axi_b_bits_id=pending.id; d.io_axi_b_bits_resp=pending.error?2:0;
    for (unsigned i=0;i<16;i++) d.io_axi_r_bits_data[i]=pending.data[i];
    d.eval();
    bool ar=d.io_axi_ar_valid && d.io_axi_ar_ready, af=d.io_axi_aw_valid && d.io_axi_aw_ready;
    bool wf=d.io_axi_w_valid && d.io_axi_w_ready;
    bool ack=(d.io_axi_r_valid && d.io_axi_r_ready) || (d.io_axi_b_valid && d.io_axi_b_ready);
    bool cf=d.io_completion_valid && d.io_completion_ready;
    Beat address, data, read;
    if (d.io_axi_ar_valid) {
      read.valid=true; read.address=d.io_axi_ar_bits_addr; read.id=d.io_axi_ar_bits_id; read.total=read.remaining=d.io_axi_ar_bits_len+1;
      check(read.total<=16 && d.io_axi_ar_bits_size==6 && d.io_axi_ar_bits_burst==1 && ((read.address&4095)+64*read.total)<=4096,"AR fields");
      if (arHeld) check(equal(read,heldAr),"AR changed under backpressure"); heldAr=read; arHeld=!ar;
    } else check(!arHeld,"AR withdrawn");
    if (d.io_axi_aw_valid) {
      address.valid=true; address.address=d.io_axi_aw_bits_addr; address.id=d.io_axi_aw_bits_id; address.total=address.remaining=d.io_axi_aw_bits_len+1;
      check(address.total<=16 && d.io_axi_aw_bits_size==6 && d.io_axi_aw_bits_burst==1 && ((address.address&4095)+64*address.total)<=4096,"AW fields");
      if (awHeld) check(equal(address,heldAw),"AW changed under backpressure"); heldAw=address; awHeld=!af;
    } else check(!awHeld,"AW withdrawn");
    if (d.io_axi_w_valid) {
      data.valid=true; data.write=true; data.mask=d.io_axi_w_bits_strb; data.last=d.io_axi_w_bits_last;
      for (unsigned i=0;i<16;i++) data.data[i]=d.io_axi_w_bits_data[i];
      if (wHeld) check(equal(data,heldW),"W changed under backpressure"); heldW=data; wHeld=!wf;
    } else check(!wHeld,"W withdrawn");
    if (!running) check(!address.valid && !data.valid && !read.valid,"traffic without Host launch");
    if (d.io_completion_valid) check(!address.valid && !data.valid && !read.valid,"traffic before held completion acceptance");
    if (af) { aw=address; writeBursts++; }
    if (wf) collected.push_back(data);
    Beat next;
    if (aw.valid && collected.size()==aw.total) {
      check(!pending.valid && !ar,"AXI overlap"); next=collected.back(); next.address=aw.address; next.id=aw.id; next.total=next.remaining=aw.total;
      for (unsigned i=0;i<aw.total;i++) {
        check(collected[i].last==(i+1==aw.total),"WLAST"); collected[i].address=aw.address+64*i; writeCheck(collected[i]);
      }
      operations[completions].acceptedBytes+=next.total*64;
      committing=collected; collected.clear(); aw={}; writeBeats+=next.total;
    } else if (ar) { check(!pending.valid,"overlap AR"); next=read; readCheck(next); readBursts++; reads+=read.total; }
    if (next.valid) {
      check(next.address%64==0,"unaligned AXI"); next.delay=1+random()%7;
      if (!next.write) for (unsigned i=0;i<16;i++) next.data[i]=mem[pos(next.address)+i];
      if (next.write && next.address+64*next.total==finalEnd(operations[completions])) next.delay=53;
      fault(next);
      if (next.write) std::cout<<"HOST_BF16_GDN_WRITE_REQUEST run="<<runId<<" pc="<<completions<<" cycle="<<ticks
         <<" address="<<next.address<<" bytes="<<next.total*64<<" final="<<(next.address+64*next.total==finalEnd(operations[completions])?1:0)<<"\n";
    }
    if (d.io_completion_valid) {
      check(completions<commands && !pending.valid && !aw.valid && collected.empty(),"completion before final memory ACK");
      auto word=d.io_completion_bits; unsigned status=(word>>32)&255; auto &p=operations[completions];
      check((word&((1ULL<<29)-1))==completions && ((word>>29)&7)==p.engine() && (word>>40)==p.signal,"completion pc/engine/event identity");
      if (completionHeld) check(word==heldCompletion,"completion changed under backpressure");
      heldCompletion=word; completionHeld=!cf;
      if (!cf) std::cout<<"HOST_BF16_GDN_COMPLETION_HOLD run="<<runId<<" pc="<<completions
                       <<" cycle="<<ticks<<" word="<<word<<"\n";
      bool expectedSuccess=mode=="pass" || completions<faultIndex();
      check((status==0)==expectedSuccess,"unexpected per-command completion status");
      if (!expectedSuccess) check(status==(mode=="output-alias"?9:3),"wrong fault classification");
      if (status==0) check(p.ackBytes==p.bytes() && p.acceptedBytes==p.ackBytes && p.finalAcks==1 && p.outputAck==12288 && p.historyAck==(p.dense?0:49152),"success before exact command ACK bytes");
      if (cf) {
        p.completed=status==0;
        if (p.completed) successful++;
        verifyMemory(completions,status!=0 && mode!="output-alias");
        dump("writable_after_command"+std::to_string(completions)+".bin",mem.data()+pos(scratch),limit-scratch);
        std::cout<<"HOST_BF16_GDN_COMMAND run="<<runId<<" cycle="<<ticks<<" operation="<<p.name()<<" pc="<<completions<<" status="<<status
                 <<" signal="<<p.signal<<" write_ack_bytes="<<p.ackBytes<<" published="<<(p.completed?1:0)
                 <<" previous_outputs_preserved=1 guards_unchanged=1\n";
        completions++; completionWait=11;
      }
    } else check(!completionHeld,"completion withdrawn");
    if (d.io_result_valid) {
      unsigned expected=mode=="pass"?commands:faultIndex()+1;
      unsigned status=mode=="pass"?0:mode=="output-alias"?9:3;
      check(d.io_result_bits_epoch==9+runId && d.io_result_bits_failedPc==expected-1 &&
            d.io_result_bits_completed==successful && d.io_result_bits_status==status,
            "result identity changed, including acceptance cycle");
    }
    d.clock=1; d.eval(); ticks++;
    if (ack) {
      if (pending.write) {
        writeAck+=pending.total;
        auto &p=operations[completions];
        if (!pending.error) {
          for (const auto &w:committing) for (unsigned i=0;i<16;i++) mem[pos(w.address)+i]=w.data[i];
          writeBytes+=pending.total*64; p.ackBytes+=pending.total*64;
          if(within(pending.address,pending.address+pending.total*64,p.output,end(p))) p.outputAck+=pending.total*64; else p.historyAck+=pending.total*64;
          if (pending.address+64*pending.total==finalEnd(p)) p.finalAcks++;
        }
        std::cout<<"HOST_BF16_GDN_WRITE_ACK run="<<runId<<" pc="<<completions<<" cycle="<<ticks
                 <<" address="<<pending.address<<" bytes="<<pending.total*64<<" error="<<(pending.error?1:0)
                 <<" final="<<(pending.address+64*pending.total==finalEnd(p)?1:0)<<"\n";
        committing.clear();
      } else readAck++;
      if (!pending.write && pending.remaining>1) {
        pending.address+=64; pending.remaining--; pending.delay=1+random()%7; pending.error=false;
        for (unsigned i=0;i<16;i++) pending.data[i]=mem[pos(pending.address)+i]; fault(pending);
      } else pending={};
    }
    if (next.valid) pending=next; else if (pending.valid && pending.delay) pending.delay--;
    d.clock=0; d.eval();
  }
  void launch() {
    running=true; startTicks=ticks;
    std::cout<<"HOST_BF16_GDN_BEGIN run="<<runId<<" mode="<<mode<<" commands="<<commands<<" epoch="<<9+runId<<"\n";
    d.io_launch_bits_commandBase=cb; d.io_launch_bits_commandLimit=cl; d.io_launch_bits_commands=commands;
    d.io_launch_bits_descriptorBase=db; d.io_launch_bits_descriptorLimit=dl; d.io_launch_bits_descriptors=descriptors; d.io_launch_bits_epoch=9+runId;
    d.io_launch_bits_regions_0_base=base; d.io_launch_bits_regions_0_limit=meta; d.io_launch_bits_regions_0_read=1; d.io_launch_bits_regions_0_write=0;
    d.io_launch_bits_regions_1_base=meta; d.io_launch_bits_regions_1_limit=scratch; d.io_launch_bits_regions_1_read=1; d.io_launch_bits_regions_1_write=0;
    d.io_launch_bits_regions_2_base=scratch; d.io_launch_bits_regions_2_limit=limit; d.io_launch_bits_regions_2_read=1; d.io_launch_bits_regions_2_write=1;
    d.io_launch_bits_regions_3_base=0; d.io_launch_bits_regions_3_limit=0; d.io_launch_bits_regions_3_read=0; d.io_launch_bits_regions_3_write=0;
    check(d.io_launch_ready,"Host not ready"); d.io_launch_valid=1; step(); d.io_launch_valid=0;
    d.io_launch_bits_epoch=99; d.io_launch_bits_commandBase=0; // Admission latched these pins.
    while (!d.io_result_valid && ticks-startTicks<300000000ULL) step();
    check(d.io_result_valid,"watchdog");
    unsigned expectedCompletions=mode=="pass"?commands:faultIndex()+1;
    unsigned expectedJobs=mode=="output-alias"?2:expectedCompletions;
    check(completions==expectedCompletions && d.io_result_bits_epoch==9+runId &&
          d.io_result_bits_failedPc==expectedCompletions-1 && d.io_issuedJobs==expectedJobs,"Host lifecycle");
    check(reads==readAck && writeBeats==writeAck,"AXI accounting");
    check(d.io_idmaTransfers==readBursts+writeBursts,"single iDMA transfer accounting");
    uint64_t expectedMetadata=0, publishedBytes=0, usefulMacs=0;
    for (unsigned i=0;i<completions;i++) expectedMetadata+=1+operations[i].records;
    for (const auto &p:operations) if (p.completed) { publishedBytes+=p.bytes(); if(p.dense) usefulMacs+=6144*1024; }
    check(metadata==expectedMetadata && d.io_memoryAccepted_0==expectedMetadata && d.io_memoryReturned_0==expectedMetadata,"command/descriptor DDR ownership");
    check(d.io_writeBytes==publishedBytes && d.io_usefulMacs==usefulMacs,"per-command published byte/MAC accounting");
    check(completionBlocked>=11*completions,"completion backpressure not exercised");
    verifyMemory(completions-1,mode!="pass" && mode!="output-alias");
    dump("ddr_after.bin",mem.data(),mem.size()*4);
    for(const auto &p:operations) {
      dump("actual_"+p.name()+".bf16le",mem.data()+pos(p.output),12288);
      if(!p.dense) dump("actual_history"+std::to_string(p.token)+".bf16le",mem.data()+pos(p.historyOut),49152);
    }
    if (mode=="pass") {
      check(d.io_result_bits_status==0 && d.io_result_bits_completed==commands && !d.io_resetRequired,"success result");
      reportPass();
    } else {
      check((injected || mode=="output-alias") && d.io_result_bits_status!=0 && d.io_result_bits_completed==successful && d.io_resetRequired,"fault not closed");
      check(successful==faultIndex(),"failed command published");
      std::cout<<"HOST_BF16_GDN_FAULT_PASS run="<<runId<<" mode="<<mode<<" failed_pc="<<faultIndex()<<" status="<<unsigned(d.io_result_bits_status)
               <<" successful_commands="<<successful<<" write_ack_bytes="<<writeBytes<<" published_bytes="<<publishedBytes
               <<" failed_command_published_bytes=0 previous_outputs_preserved=1 guards_unchanged=1\n";
    }
    auto status=d.io_result_bits_status; auto resultEpoch=d.io_result_bits_epoch; auto resultPc=d.io_result_bits_failedPc;
    for (unsigned i=0;i<7;i++) {
      step(); check(d.io_result_valid && d.io_result_bits_status==status && d.io_result_bits_completed==successful &&
                    d.io_result_bits_epoch==resultEpoch && d.io_result_bits_failedPc==resultPc,"result backpressure");
    }
    d.io_result_ready=1; step(); d.io_result_ready=0; running=false;
    if (mode!="pass") {
      auto transfers=d.io_idmaTransfers; d.io_launch_valid=1;
      for (unsigned i=0;i<10;i++) { check(!d.io_launch_ready,"poison escaped"); step(); check(d.io_idmaTransfers==transfers,"work after fault"); }
      d.io_launch_valid=0;
    }
    std::cout<<"HOST_BF16_GDN_END run="<<runId<<" status="<<unsigned(status)<<" result_epoch="<<unsigned(resultEpoch)
             <<" result_pc="<<unsigned(resultPc)<<" completions="<<completions
             <<" successful="<<successful<<" issued_jobs="<<expectedJobs<<" metadata_reads="<<metadata
             <<" read_beats="<<reads<<" read_ack_beats="<<readAck<<" write_beats="<<writeBeats<<" write_ack_beats="<<writeAck
             <<" published_bytes="<<publishedBytes<<" reset_required="<<(d.io_resetRequired?1:0)<<"\n";
  }
  void reportPass() {
    bool nativePass=true; uint64_t words=0;
    for(const auto &p:operations) {
      Metric metric; uint64_t conditionedBits=0, conditionedNumeric=0, maximumUlp=0;
      for(size_t i=0;i<p.reference.size();i++) {
        auto actual=half(p.output,i); metric.add(actual,p.native[i]);
        if(!p.dense) {
          auto ordered=[](uint16_t x) { return (x&0x8000)?0x8000-int(x&0x7fff):0x8000+int(x); };
          auto ulp=uint64_t(std::abs(ordered(actual)-ordered(p.conditioned[i])));
          maximumUlp=std::max(maximumUlp,ulp); conditionedBits+=actual!=p.conditioned[i]; conditionedNumeric+=ulp!=0;
        }
      }
      nativePass&=metric.pass() && (p.dense || maximumUlp<=1); words+=p.reference.size()+p.history.size();
      std::cout<<"HOST_BF16_GDN_NATIVE run="<<runId<<" stage="<<p.name()<<" elements="<<metric.elements
               <<" bit_differences="<<metric.differences<<" max_abs="<<metric.max<<" mean_abs="<<metric.mean()
               <<" same_input_bit_differences="<<conditionedBits<<" same_input_numeric_differences="<<conditionedNumeric
               <<" same_input_max_bf16_ulp="<<maximumUlp<<" signed_zero_numeric_equal=1 gate="<<(metric.pass()?"PASS":"FAIL")<<"\n";
    }
    check(nativePass,"official native fixed operator thresholds");
    std::cout<<"HOST_BF16_GDN_PASS run="<<runId<<" scope=DENSE_QKV_CONV4_SILU_ONLY commands=4 tokens=2 checked_bf16="<<words
             <<" canonical_bit_differences=0 independent_terminal_checked=1 native_operator_gate=PASS cycles="<<ticks-startTicks
             <<" write_ack_bytes="<<writeBytes<<" metadata_reads="<<metadata
             <<" logical_matrix_engines=1 physical_matrix_slices=8 idma_instances=1 shared_scalar_services=1 unchanged_guards=1"
             <<" prior_outputs_preserved=1 delayed_final_ack_commands=4 completion_backpressure_commands=4"
             <<" actual_dma_intermediate_sources=1 history_generations=2 output_spans=6 input_norm_dut=0 full_block_supported=0\n";
  }
  void recover() {
    check(mode=="reset-recovery" && successful==0 && writeBytes==0 && mem==initial,"reset recovery requires untouched physical DDR");
    check(!pending.valid && !aw.valid && collected.empty() && committing.empty(),"reset with external DDR transaction");
    d.reset=1; for (unsigned i=0;i<6;i++) step(); d.reset=0; for (unsigned i=0;i<30;i++) step();
    check(!d.io_resetRequired && d.io_launch_ready,"reset failed to clear poison");
    reads=readAck=writeBeats=writeAck=writeBytes=readBursts=writeBursts=metadata=completionBlocked=0;
    completions=successful=0; completionWait=11; completionHeld=false; injected=false;
    for (auto &p:operations) { p.ackBytes=p.acceptedBytes=p.finalAcks=p.outputAck=p.historyAck=0; p.completed=false; }
    mode="pass"; runId++; out/="recovery"; std::filesystem::create_directory(out);
    for (const auto &p:operations) dump("reference_"+p.name()+".bf16le",p.reference.data(),p.reference.size()*2);
    launch();
    std::cout<<"HOST_BF16_GDN_RESET_RECOVERY_PASS same_dut=1 unchanged_input_constants=1 expected_output_injection=0 commands=4\n";
  }
};

int main(int argc,char **argv) {
  try {
    std::fesetround(FE_TONEAREST); Verilated::commandArgs(argc,argv);
    std::cout<<std::setprecision(17);
    check(argc>=3 && argc<=4,"FIXTURE OUTPUT [pass|last-history-ack-error|activation-read-error|weight-read-error|output-alias|reset-recovery]");
    std::string mode=argc>3?argv[3]:"pass";
    auto test=std::make_unique<Test>(argv[1],argv[2],mode); test->launch(); if (mode=="reset-recovery") test->recover();
    return 0;
  } catch (const std::exception &error) {
    std::cerr<<"HOST_BF16_GDN_FAIL: "<<error.what()<<std::endl; return 1;
  }
}
