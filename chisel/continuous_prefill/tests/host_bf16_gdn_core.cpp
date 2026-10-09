// SPDX-License-Identifier: Apache-2.0
// Production HostBlockTop, two M1 launches on one DUT, seven owners then fence.
// The external service is one physical DDR. Expected/native bytes are NEVER loaded
// there. Every intermediate and carried state originates in accepted AXI B ACKs.
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
static uint16_t rne(float x) { uint32_t u=bits(x); return uint16_t((u+0x7fff+((u>>16)&1))>>16); }
struct Beat {
  bool valid=false, write=false, error=false, last=true;
  uint64_t address=0, id=0, mask=0;
  unsigned delay=0, total=1, remaining=1;
  std::array<uint32_t,16> data{};
};
struct Source { uint64_t address=0, bytes=0; int producer=-1; };
struct Span {
  uint64_t address=0, bytes=0, elementBytes=0, ackBytes=0;
  std::string name, expectedFile, nativeFile;
  std::vector<uint8_t> reference, native, conditioned, acknowledged;
};
struct Operation {
  uint64_t pc=0, kind=0, records=0, engine=0, wait=0, signal=0, destinationRoot=0;
  uint64_t acceptedBytes=0, ackBytes=0, finalAcks=0;
  bool completed=false;
  std::vector<Source> reads;
  std::vector<Span> writes;
  uint64_t bytes() const { uint64_t total=0; for (const auto &s:writes) total+=s.bytes; return total; }
};
struct Launch {
  uint64_t token=0, epoch=0, cb=0, cl=0, commands=0, db=0, dl=0, descriptors=0;
  std::vector<Operation> operations;
  bool fenced=false;
};
static const std::array<std::string,8> kinds={"qkv","z","ab","conv","prep","recurrent","norm","fence"};

class Test {
 public:
  VHostBlockTop d;
  uint64_t base=0, limit=0, meta=0, scratch=0;
  std::array<Launch,2> launches;
  // This is the sole physical storage, indexed by address, never by command.
  std::vector<uint32_t> mem, initial;
  std::vector<Beat> collected, committing;
  Beat pending, aw, heldAr, heldAw, heldW;
  bool arHeld=false, awHeld=false, wHeld=false, running=false, completionHeld=false;
  uint64_t heldCompletion=0;
  uint32_t rng=91827;
  uint64_t ticks=0, startTicks=0, reads=0, readAck=0, writeBeats=0, writeAck=0;
  uint64_t writeBytes=0, readBursts=0, writeBursts=0, metadata=0, completionBlocked=0;
  uint64_t dmaStart=0, metadataAcceptedStart=0, metadataReturnedStart=0;
  unsigned runId=0, completions=0, completionWait=11;
  std::filesystem::path out;

  Test(const std::filesystem::path &fixture, const std::filesystem::path &output):out(output) {
    std::ifstream input(fixture/"launch.txt"); std::string magic; uint64_t inputs=0, runs=0;
    input>>magic>>base>>limit>>meta>>scratch>>inputs>>runs;
    check(bool(input) && magic=="HOST_GDN_CORE_V2" && runs==2 && inputs==11 &&
          base<meta && meta<scratch && scratch<limit && (limit-base)%64==0,"fixture launch header");
    mem.resize((limit-base)/4,0xa55ac33cU);
    const std::array<std::string,11> allowed={"activation0.bf16le","activation1.bf16le",
      "weight_qkv.bf16le","weight_z.bf16le","weight_ab.bf16le","weight_conv.bf16le",
      "a_log.f32le","dt_bias.bf16le","weight_norm.f32le","initial_history.bf16le","initial_state.f32le"};
    const std::array<uint64_t,11> sizes={2048,2048,12582912,4194304,65536,49152,64,64,512,49152,1048576};
    std::vector<Source> initialSources;
    for (unsigned i=0;i<inputs;i++) {
      uint64_t address=0, bytes=0; std::string file; input>>address>>bytes>>file;
      check(bool(input) && file==allowed[i] && bytes==sizes[i] && address%64==0 &&
            address>=meta && address+bytes<=scratch,"raw-only DDR initialization whitelist");
      for (const auto &s:initialSources) check(!overlap(address,address+bytes,s.address,s.address+s.bytes),"raw input alias");
      initialSources.push_back({address,bytes,-1}); load(fixture/file,address,bytes);
    }
    for (unsigned token=0;token<2;token++) {
      auto &l=launches[token];
      input>>l.token>>l.epoch>>l.cb>>l.cl>>l.commands>>l.db>>l.dl>>l.descriptors;
      check(bool(input) && l.token==token && l.epoch==9+token && l.commands==8 && l.descriptors==113 &&
            l.cl-l.cb==128 && l.dl-l.db==1856 && l.cb>=base && l.cl<=meta && l.db>=base && l.dl<=meta,
            "eight-command public table geometry");
      load(fixture/("host_commands"+std::to_string(token)+".bin"),l.cb,l.cl-l.cb);
      load(fixture/("host_descriptors"+std::to_string(token)+".bin"),l.db,l.dl-l.db);
      l.operations.resize(8); uint64_t records=0;
      const std::array<unsigned,8> expectedRecords={12,12,12,18,18,15,15,11};
      const std::array<unsigned,8> expectedReads={2,2,2,3,4,2,3,3};
      for (unsigned pc=0;pc<8;pc++) {
        auto &p=l.operations[pc]; unsigned nr=0,nw=0;
        input>>p.pc>>p.kind>>p.records>>p.engine>>p.wait>>p.signal>>p.destinationRoot>>nr>>nw;
        check(bool(input) && p.pc==pc && p.kind==pc && p.records==expectedRecords[pc] &&
              p.engine==(pc<3?2:3) && p.wait==pc && p.signal==pc+1 && p.destinationRoot<113 &&
              nr==expectedReads[pc] && nw==(pc==7?0:pc==3 || pc==5?2:1),"operation bindings");
        records+=p.records;
        for (unsigned i=0;i<nr;i++) {
          Source s; input>>s.address>>s.bytes>>s.producer;
          check(bool(input) && s.address%64==0 && s.bytes%64==0 && s.bytes && s.address>=meta &&
                s.address+s.bytes<=limit && s.producer<int(token*8+pc),"source geometry/dependency");
          if (s.producer<0) {
            check(std::any_of(initialSources.begin(),initialSources.end(),[&](const Source &x){return x.address==s.address && x.bytes==s.bytes;}),
                  "source is neither raw input nor an earlier actual producer");
          } else {
            const auto &producer=operation(unsigned(s.producer));
            check(std::any_of(producer.writes.begin(),producer.writes.end(),[&](const Span &x){return x.address==s.address && x.bytes==s.bytes;}),
                  "producer address does not match actual earlier output");
          }
          p.reads.push_back(s);
        }
        for (unsigned i=0;i<nw;i++) {
          Span s; input>>s.address>>s.bytes>>s.elementBytes>>s.name>>s.expectedFile>>s.nativeFile;
          check(bool(input) && s.address>=scratch && s.address%64==0 && s.bytes && s.bytes%64==0 &&
                s.address+s.bytes<=limit && (s.elementBytes==2 || s.elementBytes==4),"output physical geometry");
          std::string name=i==0?kinds[pc]:pc==3?"history":"state";
          uint64_t expectedBytes=i?pc==3?49152:1048576:pc==0 || pc==3?12288:pc==2?64:pc==4?25600:4096;
          unsigned elementBytes=pc==4 || (pc==5 && i==1)?4:2;
          auto suffix=std::to_string(token)+(elementBytes==4?".f32le":".bf16le");
          check(s.name==name && s.bytes==expectedBytes && s.elementBytes==elementBytes &&
                s.expectedFile=="expected_"+name+suffix && s.nativeFile=="native_"+name+suffix,"canonical stage geometry");
          for (const auto &prior:launches) for (const auto &op:prior.operations) for (const auto &span:op.writes)
            check(!overlap(s.address,s.address+s.bytes,span.address,span.address+span.bytes),"stage outputs must have distinct physical spans");
          s.reference=readBytes(fixture/s.expectedFile,s.bytes); s.native=readBytes(fixture/s.nativeFile,s.bytes);
          if (s.name=="conv") s.conditioned=readBytes(fixture/("conditioned_conv"+std::to_string(token)+".bf16le"),s.bytes);
          s.acknowledged.resize(s.bytes,0); p.writes.push_back(std::move(s));
        }
        if (pc<3) verifyDense(p); // Comparison only, no write into mem.
      }
      check(records==l.descriptors,"descriptor count");
    }
    check(launches[1].operations[3].reads[2].producer==3 && launches[1].operations[5].reads[1].producer==5,
          "second launch must carry actual first-token history/state");
    std::string extra; check(!(input>>extra),"unexpected fixture fields");
    initial=mem; // No writes to the physical RAM except accepted B responses below.
    check(!std::filesystem::exists(out) || std::filesystem::is_empty(out),"output must be fresh");
    std::filesystem::create_directories(out);
    d.clock=0; d.reset=1; d.io_launch_valid=0; d.io_completion_ready=0; d.io_result_ready=0;
    for (unsigned i=0;i<6;i++) step();
    d.reset=0;
    for (unsigned i=0;i<30;i++) step();
  }

  Launch &current() { return launches[runId]; }
  Operation &active() { check(completions<8,"operation after fence"); return current().operations[completions]; }
  Operation &operation(unsigned index) { return launches.at(index/8).operations.at(index%8); }
  static bool within(uint64_t a,uint64_t b,uint64_t lo,uint64_t hi) { return lo<=a && a<b && b<=hi; }
  static bool overlap(uint64_t a,uint64_t b,uint64_t lo,uint64_t hi) { return a<hi && lo<b; }
  size_t pos(uint64_t address) const {
    check(address>=base && address<limit && address%4==0,"DDR physical address"); return (address-base)/4;
  }
  uint16_t half(uint64_t address,size_t index) const {
    check(address+index*2+2<=limit,"DDR BF16 bound");
    return uint16_t(mem[pos(address)+index/2]>>((index%2)*16));
  }
  static std::vector<uint8_t> readBytes(const std::filesystem::path &path,size_t bytes) {
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    check(bool(file) && size_t(file.tellg())==bytes,"file size "+path.string());
    std::vector<uint8_t> result(bytes); file.seekg(0); file.read(reinterpret_cast<char *>(result.data()),bytes);
    check(bool(file),"file read "+path.string()); return result;
  }
  void load(const std::filesystem::path &path,uint64_t address,size_t bytes) {
    check(address+bytes<=limit,"fixture physical bounds"); auto raw=readBytes(path,bytes);
    std::memcpy(mem.data()+pos(address),raw.data(),bytes);
  }
  void dump(const std::string &name,const void *data,size_t bytes) const {
    check(!std::filesystem::exists(out/name),"refuse stale output "+name);
    std::ofstream file(out/name,std::ios::binary); file.write(reinterpret_cast<const char *>(data),bytes);
    check(bool(file),"output dump "+name);
  }
  void verifyDense(const Operation &p) const {
    const auto &target=p.writes.at(0); unsigned columns=target.bytes/2;
    check(p.reads[0].bytes==2048 && p.reads[1].bytes==1024*columns*2,"N32/N2048/N6144 Dense input geometry");
    for (unsigned column=0;column<columns;column++) {
      float sum=0;
      for (unsigned k=0;k<1024;k++) sum=std::fma(fp(uint32_t(half(p.reads[0].address,k))<<16),
          fp(uint32_t(half(p.reads[1].address,k*columns+column))<<16),sum);
      uint16_t expected=0; std::memcpy(&expected,target.reference.data()+column*2,2);
      check(std::isfinite(sum) && rne(sum)==expected,"C++ Dense terminal differs from shared integer/C oracle");
    }
  }
  unsigned random() { rng^=rng<<13; rng^=rng>>17; rng^=rng<<5; return rng; }
  static bool equal(const Beat &a,const Beat &b) {
    return a.address==b.address && a.id==b.id && a.mask==b.mask && a.data==b.data && a.total==b.total && a.last==b.last;
  }
  static unsigned strobeBytes(uint64_t mask) { return unsigned(__builtin_popcountll(mask)); }
  bool finalWrite() {
    const auto &p=active(); return !p.writes.empty() && p.acceptedBytes==p.bytes();
  }
  void readCheck(const Beat &beat) {
    auto &l=current(); auto &p=active(); auto last=beat.address+64*beat.total;
    bool table=within(beat.address,last,l.cb,l.cl) || within(beat.address,last,l.db,l.dl);
    bool source=false;
    for (const auto &s:p.reads) if (within(beat.address,last,s.address,s.address+s.bytes)) {
      source=true;
      if (s.producer>=0) {
        auto &producer=operation(unsigned(s.producer));
        check(producer.completed,"consumer read before producer completion/ACK");
        if (unsigned(s.producer)/8<runId) {
          check(launches[runId-1].fenced,"carried read before preceding fence commit");
          std::cout<<"HOST_BF16_GDN_CORE_CARRY_READ run="<<runId<<" pc="<<completions<<" cycle="<<ticks
            <<" address="<<beat.address<<" bytes="<<beat.total*64<<" producer="<<s.producer<<"\n";
        }
      }
    }
    check(table || source,"read outside actual command source spans");
    if (table) { check(beat.total==1,"metadata burst"); metadata++; }
  }
  void writeCheck(const Beat &beat) {
    auto &p=active(); bool allowed=false;
    for (const auto &s:p.writes) if (within(beat.address,beat.address+64,s.address,s.address+s.bytes)) {
      allowed=true;
      check(beat.mask==~0ULL || (p.kind==5 && s.name=="recurrent" &&
            (beat.mask==0xffffffffULL || beat.mask==0xffffffff00000000ULL)),"unexpected output strobe");
    }
    check(allowed,"write outside exact output/state spans or into guard");
  }
  void verifyMemory() const {
    for (const auto &l:launches) for (const auto &p:l.operations) if (p.completed)
      for (const auto &s:p.writes) {
        check(std::memcmp(mem.data()+pos(s.address),s.reference.data(),s.bytes)==0,
              "canonical bits/preserved output "+s.name+std::to_string(l.token));
      }
    for (size_t i=0;i<mem.size();i++) {
      auto address=base+i*4; bool writable=false;
      for (const auto &l:launches) for (const auto &p:l.operations) if (p.completed)
        for (const auto &s:p.writes) writable|=within(address,address+4,s.address,s.address+s.bytes);
      if (!writable) check(mem[i]==initial[i],"raw input, future output, or physical guard modified");
    }
  }
  void reportNative(const Span &s) {
    const auto *actual=reinterpret_cast<const uint8_t *>(mem.data()+pos(s.address));
    uint64_t mismatches=0, elements=s.bytes/s.elementBytes, conditionedUlp=0; double maximum=0,total=0;
    for (uint64_t i=0;i<elements;i++) {
      uint32_t a=0,b=0; std::memcpy(&a,actual+i*s.elementBytes,s.elementBytes);
      std::memcpy(&b,s.native.data()+i*s.elementBytes,s.elementBytes); mismatches+=a!=b;
      if (!s.conditioned.empty()) {
        uint16_t c=0; std::memcpy(&c,s.conditioned.data()+i*2,2);
        auto ordered=[](uint16_t value){return value&0x8000?0x8000-int(value&0x7fff):0x8000+int(value);};
        conditionedUlp=std::max(conditionedUlp,uint64_t(std::abs(ordered(uint16_t(a))-ordered(c))));
      }
      if (s.elementBytes==2) { a<<=16; b<<=16; }
      double delta=std::abs(double(fp(a))-double(fp(b)));
      check(std::isfinite(delta),"nonfinite native diagnostic"); maximum=std::max(maximum,delta); total+=delta;
    }
    bool fixed=s.name=="qkv" || s.name=="z" || s.name=="ab" || s.name=="conv";
    if (fixed) check(maximum<=.03125 && total/elements<=.005 && (s.conditioned.empty() || conditionedUlp<=1),
                     "unchanged native Dense/Conv/SiLU operator gate failed");
    std::cout<<"HOST_BF16_GDN_CORE_NATIVE run="<<runId<<" stage="<<s.name<<" elements="<<elements
      <<" element_bytes="<<s.elementBytes<<" bit_mismatches="<<mismatches<<" max_abs="<<maximum
      <<" mean_abs="<<total/elements<<" same_input_max_bf16_ulp="<<conditionedUlp
      <<" fixed_operator_gate="<<(fixed?"PASS":"UNASSIGNED")
      <<" acceptance="<<(fixed?"FROZEN_OPERATOR_THRESHOLDS":"UNASSIGNED_DIAGNOSTIC_ONLY")<<"\n";
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
    d.io_axi_r_bits_id=pending.id; d.io_axi_r_bits_resp=0; d.io_axi_r_bits_last=pending.remaining==1;
    d.io_axi_b_bits_id=pending.id; d.io_axi_b_bits_resp=0;
    for (unsigned i=0;i<16;i++) d.io_axi_r_bits_data[i]=pending.data[i];
    d.eval();
    bool ar=d.io_axi_ar_valid && d.io_axi_ar_ready, af=d.io_axi_aw_valid && d.io_axi_aw_ready;
    bool wf=d.io_axi_w_valid && d.io_axi_w_ready;
    bool ack=(d.io_axi_r_valid && d.io_axi_r_ready) || (d.io_axi_b_valid && d.io_axi_b_ready);
    bool cf=d.io_completion_valid && d.io_completion_ready;
    Beat address,data,read;
    if (d.io_axi_ar_valid) {
      read.valid=true; read.address=d.io_axi_ar_bits_addr; read.id=d.io_axi_ar_bits_id;
      read.total=read.remaining=d.io_axi_ar_bits_len+1;
      check(read.total<=16 && d.io_axi_ar_bits_size==6 && d.io_axi_ar_bits_burst==1 &&
            ((read.address&4095)+64*read.total)<=4096,"AR fields");
      if (arHeld) check(equal(read,heldAr),"AR changed under backpressure");
      heldAr=read; arHeld=!ar;
    } else check(!arHeld,"AR withdrawn");
    if (d.io_axi_aw_valid) {
      address.valid=true; address.address=d.io_axi_aw_bits_addr; address.id=d.io_axi_aw_bits_id;
      address.total=address.remaining=d.io_axi_aw_bits_len+1;
      check(address.total<=16 && d.io_axi_aw_bits_size==6 && d.io_axi_aw_bits_burst==1 &&
            ((address.address&4095)+64*address.total)<=4096,"AW fields");
      if (awHeld) check(equal(address,heldAw),"AW changed under backpressure");
      heldAw=address; awHeld=!af;
    } else check(!awHeld,"AW withdrawn");
    if (d.io_axi_w_valid) {
      data.valid=true; data.write=true; data.mask=d.io_axi_w_bits_strb; data.last=d.io_axi_w_bits_last;
      for (unsigned i=0;i<16;i++) data.data[i]=d.io_axi_w_bits_data[i];
      if (wHeld) check(equal(data,heldW),"W changed under backpressure");
      heldW=data; wHeld=!wf;
    } else check(!wHeld,"W withdrawn");
    if (!running) check(!address.valid && !data.valid && !read.valid,"traffic without Host launch");
    if (d.io_completion_valid) check(!address.valid && !data.valid && !read.valid,"traffic before held completion acceptance");
    if (af) { aw=address; writeBursts++; }
    if (wf) collected.push_back(data);
    Beat next;
    if (aw.valid && collected.size()==aw.total) {
      check(!pending.valid && !ar,"AXI overlap"); next=collected.back(); next.address=aw.address;
      next.id=aw.id; next.total=next.remaining=aw.total;
      for (unsigned i=0;i<aw.total;i++) {
        check(collected[i].last==(i+1==aw.total),"WLAST"); collected[i].address=aw.address+64*i; writeCheck(collected[i]);
      }
      for (const auto &w:collected) active().acceptedBytes+=strobeBytes(w.mask);
      check(active().acceptedBytes<=active().bytes(),"accepted output bytes exceed stage footprint");
      committing=collected; collected.clear(); aw={}; writeBeats+=next.total;
    } else if (ar) { check(!pending.valid,"overlap AR"); next=read; readCheck(next); readBursts++; reads+=read.total; }
    if (next.valid) {
      check(next.address%64==0,"unaligned AXI"); next.delay=1+random()%7;
      if (!next.write) for (unsigned i=0;i<16;i++) next.data[i]=mem[pos(next.address)+i];
      if (next.write && finalWrite()) next.delay=53;
      if (next.write) std::cout<<"HOST_BF16_GDN_CORE_WRITE_REQUEST run="<<runId<<" pc="<<completions<<" cycle="<<ticks
        <<" address="<<next.address<<" bus_bytes="<<next.total*64<<" final="<<finalWrite()<<"\n";
    }
    if (d.io_completion_valid) {
      check(completions<8 && !pending.valid && !aw.valid && collected.empty(),"completion before final memory ACK");
      uint64_t word=d.io_completion_bits; auto &p=active(); unsigned status=(word>>32)&255;
      check((word&((1ULL<<29)-1))==completions && ((word>>29)&7)==p.engine && (word>>40)==p.signal,
            "completion pc/engine/event identity");
      if (completionHeld) check(word==heldCompletion,"completion changed under backpressure");
      heldCompletion=word; completionHeld=!cf;
      check(status==0,"core command failed with status "+std::to_string(status));
      check(p.ackBytes==p.bytes() && p.acceptedBytes==p.ackBytes && p.finalAcks==(p.kind==7?0:1),
            "success before exact stage ACK bytes");
      for (const auto &s:p.writes) check(s.ackBytes==s.bytes && std::all_of(s.acknowledged.begin(),s.acknowledged.end(),
        [](uint8_t value){return value==1;}),"stage output omitted or duplicated a strobed byte");
      if (!cf) std::cout<<"HOST_BF16_GDN_CORE_COMPLETION_HOLD run="<<runId<<" pc="<<completions
                        <<" cycle="<<ticks<<" word="<<word<<"\n";
      if (cf) {
        p.completed=true; verifyMemory();
        if (p.kind==7) current().fenced=true;
        dump("writable_after_command"+std::to_string(completions)+".bin",mem.data()+pos(scratch),limit-scratch);
        for (const auto &s:p.writes) {
          auto extension=s.elementBytes==4?".f32le":".bf16le";
          dump("actual_"+s.name+std::to_string(runId)+extension,mem.data()+pos(s.address),s.bytes); reportNative(s);
        }
        std::cout<<"HOST_BF16_GDN_CORE_COMMAND run="<<runId<<" cycle="<<ticks<<" operation="<<kinds[p.kind]
          <<" pc="<<completions<<" status="<<status<<" signal="<<p.signal<<" write_ack_bytes="<<p.ackBytes
          <<" canonical_bit_mismatches=0 previous_outputs_preserved=1 guards_unchanged=1 persistent_commit="<<(p.kind==7)
          <<" expected_committed_generation="<<(runId+(p.kind==7?1:0))<<"\n";
        completions++; completionWait=11;
      }
    } else check(!completionHeld,"completion withdrawn");
    if (d.io_result_valid) check(d.io_result_bits_epoch==current().epoch && d.io_result_bits_failedPc==7 &&
      d.io_result_bits_completed==8 && d.io_result_bits_status==0,"result identity, including acceptance cycle");
    d.clock=1; d.eval(); ticks++;
    if (ack) {
      if (pending.write) {
        writeAck+=pending.total; auto &p=active();
        bool final=finalWrite(); if (final) p.finalAcks++;
        for (unsigned beat=0;beat<committing.size();beat++) {
          const auto &w=committing[beat];
          bool found=false;
          for (auto &s:p.writes) if (within(w.address,w.address+64,s.address,s.address+s.bytes)) {
            auto index=w.address-s.address;
            for (unsigned byte=0;byte<64;byte++) if ((w.mask>>byte)&1) {
              check(!s.acknowledged[index+byte],"duplicate physical output byte ACK");
              s.acknowledged[index+byte]=1; s.ackBytes++;
            }
            found=true;
          }
          check(found,"unbound physical ACK");
          // Preserve unstrobed bytes, including the other half of a recurrent
          // BF16 beat. Reference/native buffers cannot reach this write path.
          for (unsigned byte=0;byte<64;byte++) if ((w.mask>>byte)&1) {
            auto index=pos(w.address)+byte/4; unsigned shift=(byte%4)*8;
            auto value=(w.data[byte/4]>>shift)&255;
            mem[index]=(mem[index]&~(255U<<shift))|(value<<shift);
          }
          auto count=strobeBytes(w.mask); writeBytes+=count; p.ackBytes+=count;
          std::cout<<"HOST_BF16_GDN_CORE_WRITE_ACK run="<<runId<<" pc="<<completions<<" cycle="<<ticks
            <<" address="<<w.address<<" bus_bytes=64 write_bytes="<<count<<" mask="<<w.mask
            <<" error=0 final="<<(final && beat+1==committing.size())<<"\n";
        }
        committing.clear();
      } else readAck++;
      if (!pending.write && pending.remaining>1) {
        pending.address+=64; pending.remaining--; pending.delay=1+random()%7;
        for (unsigned i=0;i<16;i++) pending.data[i]=mem[pos(pending.address)+i];
      } else pending={};
    }
    if (next.valid) pending=next; else if (pending.valid && pending.delay) pending.delay--;
    d.clock=0; d.eval();
  }
  void launch() {
    auto &l=current();
    check(runId==0 || launches[runId-1].fenced,"second launch before cold fence");
    running=true; startTicks=ticks;
    dmaStart=d.io_idmaTransfers; metadataAcceptedStart=d.io_memoryAccepted_0; metadataReturnedStart=d.io_memoryReturned_0;
    std::cout<<"HOST_BF16_GDN_CORE_BEGIN run="<<runId<<" commands=8 epoch="<<l.epoch
      <<" mode="<<(runId?"carried":"cold")<<" same_dut=1 reset_between_launches=0\n";
    d.io_launch_bits_commandBase=l.cb; d.io_launch_bits_commandLimit=l.cl; d.io_launch_bits_commands=8;
    d.io_launch_bits_descriptorBase=l.db; d.io_launch_bits_descriptorLimit=l.dl;
    d.io_launch_bits_descriptors=l.descriptors; d.io_launch_bits_epoch=l.epoch;
    d.io_launch_bits_regions_0_base=base; d.io_launch_bits_regions_0_limit=meta;
    d.io_launch_bits_regions_0_read=1; d.io_launch_bits_regions_0_write=0;
    d.io_launch_bits_regions_1_base=meta; d.io_launch_bits_regions_1_limit=scratch;
    d.io_launch_bits_regions_1_read=1; d.io_launch_bits_regions_1_write=0;
    d.io_launch_bits_regions_2_base=scratch; d.io_launch_bits_regions_2_limit=limit;
    d.io_launch_bits_regions_2_read=1; d.io_launch_bits_regions_2_write=1;
    d.io_launch_bits_regions_3_base=0; d.io_launch_bits_regions_3_limit=0;
    d.io_launch_bits_regions_3_read=0; d.io_launch_bits_regions_3_write=0;
    check(d.io_launch_ready,"Host not ready"); d.io_launch_valid=1; step(); d.io_launch_valid=0;
    d.io_launch_bits_epoch=99; d.io_launch_bits_commandBase=0;
    while (!d.io_result_valid && ticks-startTicks<600000000ULL) step();
    check(d.io_result_valid,"watchdog");
    check(completions==8 && l.fenced && d.io_result_bits_epoch==l.epoch && d.io_result_bits_failedPc==7 &&
          d.io_result_bits_completed==8 && d.io_result_bits_status==0 && d.io_issuedJobs==7 && !d.io_resetRequired,
          "eight completions/seven owner jobs/fence lifecycle");
    check(reads==readAck && writeBeats==writeAck,"AXI accounting");
    check(d.io_idmaTransfers-dmaStart==readBursts+writeBursts,"single iDMA transfer accounting");
    uint64_t expectedMetadata=0,publishedBytes=0;
    for (const auto &p:l.operations) { expectedMetadata+=1+p.records; publishedBytes+=p.bytes(); }
    check(metadata==expectedMetadata && d.io_memoryAccepted_0-metadataAcceptedStart==expectedMetadata &&
          d.io_memoryReturned_0-metadataReturnedStart==expectedMetadata,"command/descriptor DDR ownership");
    check(writeBytes==publishedBytes && d.io_writeBytes==publishedBytes && d.io_usefulMacs==8421376,
          "exact Dense MACs and all-stage write accounting");
    check(completionBlocked>=88,"completion backpressure not exercised");
    verifyMemory(); dump("ddr_after.bin",mem.data(),mem.size()*4);
    for (unsigned i=0;i<7;i++) { step(); check(d.io_result_valid,"result withdrawn under backpressure"); }
    d.io_result_ready=1; step(); d.io_result_ready=0; running=false;
    std::cout<<"HOST_BF16_GDN_CORE_END run="<<runId<<" status=0 result_epoch="<<l.epoch
      <<" result_pc=7 completions=8 issued_jobs=7 metadata_reads="<<metadata<<" read_beats="<<reads
      <<" read_ack_beats="<<readAck<<" write_beats="<<writeBeats<<" write_ack_beats="<<writeAck
      <<" write_ack_bytes="<<writeBytes<<" published_bytes="<<publishedBytes<<" committed_generation="<<runId+1
      <<" canonical_bit_mismatches=0 frozen_operator_gate=PASS native_core_gate=UNASSIGNED_DIAGNOSTIC_ONLY full_block_supported=0\n";
  }
  void run() {
    auto root=out;
    for (runId=0;runId<2;runId++) {
      out=root/(runId?"carried":"cold"); std::filesystem::create_directory(out);
      reads=readAck=writeBeats=writeAck=writeBytes=readBursts=writeBursts=metadata=completionBlocked=0;
      completions=0; completionWait=11; completionHeld=false;
      launch(); // Deliberately no reset and no physical DDR initialization here.
    }
    out=root;
    std::cout<<"HOST_BF16_GDN_CORE_PASS scope=GDN_CORE_ONLY tokens=2 heads=16 commands=16 owner_jobs=14 fences=2"
      <<" canonical_bit_mismatches=0 actual_dense_macs=16842752 same_dut=1 reset_between_launches=0"
      <<" actual_ack_history_state_carry=1 expected_output_injection=0 logical_matrix_engines=1"
      <<" physical_matrix_slices=8 idma_instances=1 shared_scalar_services=1 input_norm_dut=0"
      <<" o_projection_dut=0 residual_dut=0 ffn_dut=0 native_core_gate=UNASSIGNED_DIAGNOSTIC_ONLY"
      <<" frozen_operator_gate=PASS native_full_block_gate=NOT_ESTABLISHED full_block_supported=0\n";
  }
};

int main(int argc,char **argv) {
  try {
    std::fesetround(FE_TONEAREST); Verilated::commandArgs(argc,argv); std::cout<<std::setprecision(17);
    check(argc==3,"FIXTURE OUTPUT (core cold/carry only; no fault/restore claim)");
    auto test=std::make_unique<Test>(argv[1],argv[2]); test->run(); return 0;
  } catch (const std::exception &error) {
    std::cerr<<"HOST_BF16_GDN_CORE_FAIL: "<<error.what()<<std::endl; return 1;
  }
}
