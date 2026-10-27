// SPDX-License-Identifier: Apache-2.0
// Real generated original/adapted storage states are the DUTs. image is only
// a prior observed output snapshot for hold assertions, never a DUT response.
#include "VHostDenseAccCalibration.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>

struct Fixture {
  VerilatedContext ctx;
  VHostDenseAccCalibration dut;
  std::array<uint32_t,4096> image{};
  uint64_t cycles=0, scans=0, pair_checks=0, witness_checks=0, alias_checks=0;
  enum Witness { Zero, Input, Prior };
  static VerilatedContext* configure(VerilatedContext& c) { c.threads(1); c.randReset(0); return &c; }
  Fixture(): dut(configure(ctx)) {}
  [[noreturn]] void fail(const char* what,unsigned row,unsigned beat,unsigned lane,
                        uint32_t a,uint32_t b) {
    std::fprintf(stderr,"FAIL_DENSEACC %s cycle=%llu scan=%llu row=%u beat=%u lane=%u a=%08x b=%08x\n",
      what,(unsigned long long)cycles,(unsigned long long)scans,row,beat,lane,a,b);
    std::abort();
  }
  void eval() { dut.eval(); if(ctx.gotFinish()) fail("unexpected-finish",0,0,0,0,0); }
  void pattern(uint32_t seed) {
    // Odd multiplication is bijective mod2^32: all4096 coordinate words differ.
    for(unsigned j=0;j<4096;++j) dut.payload[j]=seed^((j+1U)*UINT32_C(0x9e3779b9));
  }
  void scan(Witness mode) {
    std::array<uint32_t,4096> observed{};
    for(unsigned row=0;row<32;++row) for(unsigned beat=0;beat<16;++beat) {
      dut.denseRow=row; dut.denseBeat=beat; eval();
      for(unsigned i=0;i<16;++i) {
        const unsigned j=(row&15U)*256U+beat*16U+i;
        const uint32_t a=dut.original[i], b=dut.adapted[i];
        ++pair_checks; if(a!=b) fail("actual-original-versus-adapted",row,beat,i,a,b);
        const uint32_t expected=mode==Zero?0U:mode==Input?dut.payload[j]:image[j];
        ++witness_checks; if(a!=expected) fail("input-zero-or-prior-observation-witness",row,beat,i,a,expected);
        if(row<16) observed[j]=a;
        else { ++alias_checks; if(a!=observed[j]) fail("original-high-row-bit-alias",row,beat,i,a,observed[j]); }
      }
    }
    image=observed; ++scans;
  }
  void transaction(unsigned mask,uint32_t seed,bool reset) {
    if(dut.clock!=0 || mask>7) fail("fixture-transaction-precondition",0,0,0,dut.clock,mask);
    pattern(seed); dut.capture=mask&1U; dut.clearFirst=(mask>>1U)&1U;
    dut.clearSecond=(mask>>2U)&1U; dut.reset=reset; eval();
    scan(Prior); // New inputs/predicates cannot change stored data before the edge.
    dut.clock=1; ctx.timeInc(1); eval(); ++cycles;
    scan((mask&6U)?Zero:(mask&1U)?Input:Prior);
    dut.clock=0; ctx.timeInc(1); eval(); scan(Prior);
  }
  void run() {
    dut.clock=0;dut.reset=0;dut.capture=0;dut.clearFirst=0;dut.clearSecond=0;
    dut.denseRow=0;dut.denseBeat=0;pattern(0x10203040U);eval();
    // Explicit no-clock reset assertion; storage itself has original reset0.
    dut.reset=1;eval();
    for(unsigned n=0;n<2;++n){dut.clock=1;ctx.timeInc(1);eval();++cycles;dut.clock=0;ctx.timeInc(1);eval();}
    dut.reset=0;eval();scan(Zero); // Fixed two-state randReset(0), not hardware init.
    transaction(1,0x12345678U,false);
    for(unsigned mask=0;mask<8;++mask) transaction(mask,0xa55a0000U^(mask*0x01010101U),false);
    // First restore nonzero state, so reset hold is not a vacuous all-zero check.
    transaction(1,0x87654321U,false);
    transaction(0,0x77aa3300U,true);dut.reset=0;eval();scan(Prior);
    transaction(1,0x55aacc33U,true);dut.reset=0;eval();scan(Prior);
    transaction(2,0x00ff00ffU,true);dut.reset=0;eval();scan(Prior);
    transaction(0,0x13579bdfU,false);transaction(0,0x2468ace0U,false);
    dut.capture=0;dut.clearFirst=0;dut.clearSecond=0;eval();
    if(cycles!=17 || scans!=49 || pair_checks!=401408 || witness_checks!=401408 || alias_checks!=200704)
      fail("exact-full-capacity-fixture-count",0,0,0,(uint32_t)cycles,(uint32_t)scans);
    dut.final();
    std::puts("DENSEACC_CALIBRATION_SCOPE actual-original-AST_vs-actual-transformed-AST; full4096; no-Host-control-or-block-qualification");
    std::printf("DENSEACC_CALIBRATION_COUNTS clocked_cycles=%llu scans=%llu row_domain=32 beat_domain=16 words_per_read=16 write_masks=8 pair_checks=%llu witness_checks=%llu alias_checks=%llu\n",
      (unsigned long long)cycles,(unsigned long long)scans,(unsigned long long)pair_checks,(unsigned long long)witness_checks,(unsigned long long)alias_checks);
    std::puts("DENSEACC_CALIBRATION_INITIALIZATION fixed-two-state-randReset0-only; original-unreset-storage; no-hardware-zero-init-claim");
    std::puts("COMPLETE_DENSEACC_ACTUAL_STORAGE_EQUIVALENCE_CALIBRATION_NOT_HOST_NUMERIC_OR_PROVIDER_RTL");
  }
};
int main(int argc,char**) {
  if(argc!=1){std::fputs("no arguments admitted\n",stderr);return 2;}
  Fixture fixture;fixture.run();return 0;
}
