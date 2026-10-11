// SOFTWARE MODEL ONLY. DDR is address-indexed external memory, never SRAM.
// One sweep-wide epoch and bitmap suffice because the K-outer schedule is serial.
struct PrefixTransport {
  static constexpr uint64_t base=0x100000000ULL;
  static constexpr unsigned tileBytes=16384, capacity=48, sentinel=0x7fc00001u;
  std::vector<uint32_t> memory; // EXTERNAL DDR: exactly 786432 bytes.
  uint32_t payload[16];        // The sole 64-byte DDR seed/write staging payload.
  uint64_t ackBitmap=0,readBitmap=0,jobGeneration=0,pendingGeneration=0;
  uint32_t owner=0, epoch=0, nextEpoch=0, contexts=0;
  uint32_t pendingOwner=0,pendingContext=0,pendingEnd=0,beats=0;
  bool pending=false,reading=false,holdLive=false;
  mutable bool poisoned=false;
  uint64_t readBytes=0,writeBytes=0,ackCount=0;
  PrefixTransport(uint32_t who,unsigned count,uint64_t generation):memory(capacity*tileBytes/4,sentinel),jobGeneration(generation),owner(who),contexts(count) {
    need(generation && who && count && count<=capacity,"prefix configuration");
    std::fill(std::begin(payload),std::end(payload),sentinel);
  }
  void healthy() const {need(!poisoned,"prefix job poisoned; reset and full raw-input replay required");}
  void check(bool ok,const char* message)const{if(!ok){poisoned=true;need(false,message);}}
  uint64_t address(unsigned ctx,unsigned beat) const {
    check(ctx<contexts && beat<256,"prefix address bounds");
    return base+uint64_t(ctx)*tileBytes+uint64_t(beat)*64;
  }
  void startSweep(unsigned end) {
    healthy();check(!pending && !reading && !holdLive && !nextEpoch && !ackBitmap && !readBitmap && end>epoch,"prefix sweep lifecycle");nextEpoch=end;
  }
  void beginWrite(uint64_t generation,unsigned who,unsigned ctx,unsigned end) {
    healthy();check(!pending && !reading && !holdLive && generation==jobGeneration && nextEpoch==end && who==owner && ctx<contexts &&
      !(ackBitmap&(1ULL<<ctx)) && (!epoch || (readBitmap&(1ULL<<ctx))),"prefix write identity/reuse");
    pending=true;pendingGeneration=generation;pendingOwner=who;pendingContext=ctx;pendingEnd=end;beats=0;
  }
  void writeBeat(uint64_t generation,unsigned who,unsigned ctx,unsigned end,uint64_t addr,unsigned beat) {
    healthy();check(pending && !holdLive && generation==jobGeneration && generation==pendingGeneration && who==pendingOwner && ctx==pendingContext && end==pendingEnd && beat==beats && addr==address(pendingContext,beat),"prefix write address/sequence");
    for(unsigned j=0;j<16;j++)memory.at((addr-base)/4+j)=payload[j];
    beats++;writeBytes+=64;
  }
  void acknowledge(uint64_t generation,unsigned who,unsigned ctx,unsigned end,bool success) {
    healthy();check(pending && generation==jobGeneration && generation==pendingGeneration && who==pendingOwner && ctx==pendingContext && end==pendingEnd && beats==256,
      "prefix ACK identity/completeness");
    if(!success){poisoned=true;need(false,"prefix failed ACK: whole job poisoned");}
    ackBitmap|=1ULL<<ctx;pending=false;ackCount++;
  }
  void reusable() const {healthy();check(!pending && !reading && !holdLive,"reuse before prefix ACK/seed consumption");}
  void beginRead(uint64_t generation,unsigned who,unsigned ctx,unsigned end){
    healthy();check(!pending&&!reading&&!holdLive&&generation==jobGeneration&&who==owner&&ctx<contexts&&epoch&&end==epoch&&
      !(ackBitmap&(1ULL<<ctx))&&!(readBitmap&(1ULL<<ctx)),"stale/aliased/uncommitted prefix read");
    reading=true;pendingGeneration=generation;pendingOwner=who;pendingContext=ctx;pendingEnd=end;beats=0;
  }
  void readBeat(uint64_t generation,unsigned who,unsigned ctx,unsigned end,uint64_t addr,unsigned beat) {
    healthy();check(reading&&!pending&&!holdLive&&generation==jobGeneration&&generation==pendingGeneration&&
      who==pendingOwner&&ctx==pendingContext&&end==pendingEnd&&beat==beats&&addr==address(ctx,beat),"prefix restore identity/address/sequence");
    for(unsigned j=0;j<16;j++){
      payload[j]=memory.at((addr-base)/4+j);check(payload[j]!=sentinel,"unwritten prefix DDR sentinel");
      check(std::isfinite(fp(payload[j])),"nonfinite prefix restore");
    }
    holdLive=true;readBytes+=64;
  }
  void consumed(){healthy();check(reading&&holdLive,"seed hold consumed twice");holdLive=false;
    if(++beats==256){reading=false;readBitmap|=1ULL<<pendingContext;}
  }
  void finishSweep(){
    reusable();check(nextEpoch && ackBitmap==((1ULL<<contexts)-1),"prefix sweep missing ACKs");
    epoch=nextEpoch;nextEpoch=0;ackBitmap=0;readBitmap=0;
  }
};
static_assert(sizeof(PrefixTransport::payload)==64,"explicit 64B seed staging");

// Control model for ACK-gated publication. A failed write can modify external
// scratch/output bytes, but never publish a successful tensor or resume prefixes.
struct Publication {
  uint64_t generation=0;
  unsigned terminalK=0,expected=0,acked=0,expectedWords=0,written=0;
  bool pending=false,poisoned=false,published=false;
  Publication(unsigned k,unsigned count,uint64_t job):generation(job),terminalK(k),expected(count){need(job&&count,"publication admission");}
  void check(bool ok,const char* message){if(!ok){poisoned=true;need(false,message);}}
  void begin(unsigned end,unsigned ordinal,unsigned words){check(!poisoned&&!published&&!pending&&end==terminalK&&ordinal==acked&&acked<expected&&words,
    "early/out-of-order final output or reuse before ACK");pending=true;expectedWords=words;written=0;}
  void wrote(uint64_t job,unsigned ordinal,unsigned word){check(!poisoned&&pending&&job==generation&&ordinal==acked&&word==written&&written<expectedWords,
    "final payload identity/extent/order");written++;}
  void ack(uint64_t job,unsigned ordinal,bool ok){check(!poisoned&&pending&&job==generation&&ordinal==acked&&written==expectedWords,
    "final ACK identity/lifetime/extent");if(!ok){poisoned=true;need(false,"failed final ACK");}pending=false;acked++;}
  void publish(){check(!poisoned&&!pending&&!published&&acked==expected,"incomplete final publication");published=true;}
};

// Software job admission allocator. Generation is part of the proposed control
// contract and advances on every construction/restart within this process.
// Real reset-domain persistence/late-response fencing remains a hardware task.
static uint64_t allocateJobGeneration(){static uint64_t generation=0;need(generation!=UINT64_MAX,"job generation exhausted");return ++generation;}
