// SPDX-License-Identifier: Apache-2.0
// Additional AXI-only tests of the frozen Chisel + real pinned iDMA DUT.
// Reuse the original service; do not replace arithmetic or transport with mocks.
#define main initial_weight_burst_probe_main
#include "idma_weight_burst.cpp"
#undef main

static uint64_t expectedBursts(uint64_t base, unsigned beats) {
  uint64_t cursor=base, end=base+uint64_t(beats)*64, total=0;
  while(cursor<end) {
    const uint64_t line=16-((cursor-base)/64)%16;
    const uint64_t physical=16-(cursor/64)%16;
    const uint64_t n=std::min({line,physical,(end-cursor)/64});
    check(n>0,"empty oracle burst");cursor+=64*n;++total;
  }
  return total;
}
int main(int argc,char**argv) {try {
  Verilated::commandArgs(argc,argv);
  unsigned cases=0;uint64_t compared=0,readBeats=0,transfers=0;
  for(unsigned offset=0;offset<16;++offset) for(unsigned n=1;n<=33;++n) {
    auto t=std::make_unique<Bench>();t->rng=0x12345+offset*41+n;
    const uint64_t a=0x100010000ULL+64*offset;t->window(a,a+64*n);
    for(unsigned i=0;i<n;++i){t->transfer(a+64*i);compared+=16;}
    const auto count=expectedBursts(a,n);
    check(t->r==n && t->ar==count && t->d.io_transfers==count,"aligned/tail transfer count");
    check(t->d.io_cacheHits==n-count,"cache must only serve fetched beats");
    readBeats+=t->r;transfers+=count;++cases;
  }
  // Prefix byte stores must preserve every unmasked byte, including 1/63-byte tails.
  for(unsigned bytes=1;bytes<=64;++bytes) {
    auto t=std::make_unique<Bench>();const uint64_t a=0x100020000ULL;
    Data expected=t->get(a);uint64_t mask=bytes==64?~0ULL:(1ULL<<bytes)-1;
    t->window(a,a+1024);t->transfer(a);t->transfer(a,true,mask);
    Data written;for(unsigned i=0;i<16;++i)written[i]=uint32_t(t->tag*257+i);
    auto dst=reinterpret_cast<unsigned char*>(expected.data());
    auto src=reinterpret_cast<const unsigned char*>(written.data());
    for(unsigned i=0;i<bytes;++i)dst[i]=src[i];
    check(t->get(a)==expected,"masked store corrupted unmasked bytes");
    t->transfer(a);check(t->d.io_transfers==3,"store did not invalidate read mailbox");
    compared+=32;++cases;
  }
  for(uint64_t mask:{0ULL,2ULL,10ULL,0x8000000000000000ULL,0xfffffffffffffffeULL}) {
    auto t=std::make_unique<Bench>();t->transfer(0x100030000ULL,true,mask,true);
    check(!t->aw&&!t->ar&&!t->w,"invalid mask caused bus activity");++cases;
  }
  // Highest permitted address: exactly at the exclusive 56-bit limit, no wrap.
  {auto t=std::make_unique<Bench>();const uint64_t end=1ULL<<56,a=end-1024;
   t->window(a,end);for(unsigned i=0;i<16;++i){t->transfer(a+64*i);compared+=16;}
   check(t->r==16&&t->ar==1,"top address range crossed");++cases;}
  // A cache line must not supply out-of-window data or survive an explicit flush.
  {auto t=std::make_unique<Bench>();const uint64_t a=0x1234567890000ULL;
   t->window(a,a+1024);t->transfer(a);auto before=t->d.io_transfers;
   t->transfer(a-64);check(t->d.io_transfers==before+1,"outside-window read hit mailbox");
   before=t->d.io_transfers;t->transfer(a);check(t->d.io_transfers==before+1,"miss did not invalidate mailbox");
   Data next=t->get(a);next[15]^=0x80000001u;t->memory[a]=next;
   t->window(a,a+1024);check(t->transfer(a)==next,"flushed line retained old request data");
   compared+=64;++cases;}
  check(cases==599,"edge case coverage");
  std::cout<<"IDMA_WEIGHT_BURST_EDGES_PASS cases="<<cases
    <<" read_alignment_tail_cases=528 prefix_write_cases=64 invalid_mask_cases=5"
    <<" compared_u32="<<compared<<" alignment_read_beats="<<readBeats
    <<" alignment_transfers="<<transfers
    <<" data_mismatches=0 real_pinned_idma=1 frozen_dut=1"<<std::endl;
  return 0;
} catch(const std::exception&e){std::cerr<<"IDMA_WEIGHT_BURST_EDGES_FAIL: "<<e.what()<<std::endl;return 1;}}
