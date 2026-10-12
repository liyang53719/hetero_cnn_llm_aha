// SPDX-License-Identifier: Apache-2.0
// HOST MODEL ONLY. One inherited accum[5][16][256], shared by Dense and QK/PV.
// No RTL, hardware timing, or synthesized resource claim is made here.
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>

static uint64_t denseFmas=0, normalFmas=0;
static unsigned countArithmetic=0;
// Observe actual fmaf invocations, including an operation that later faults.
// The included arithmetic expressions, operand order and rounding are intact.
namespace matrix_observed_std {
using std::memcpy; using std::memset; using std::fesetround; using std::isfinite;
// Preserve the public libm operand order, including two-NaN payload selection.
// A direct compiler builtin may commute a/b when surrounding control changes.
// This only pins the host call ABI; the same FP32 fused operation is retained.
static float (*volatile orderedFmaf)(float,float,float)=::fmaf;
static float fma(float a,float b,float c){
  if(countArithmetic==1)++denseFmas;
  if(countArithmetic==2)++normalFmas;
  return orderedFmaf(a,b,c);
}
}
#define std matrix_observed_std
#define td_reset __attribute__((visibility("hidden"))) private_td_reset
#define td_group __attribute__((visibility("hidden"))) private_td_group
#define td_seed_begin __attribute__((visibility("hidden"))) private_td_seed_begin
#define td_seed_beat __attribute__((visibility("hidden"))) private_td_seed_beat
#define td_seed_commit __attribute__((visibility("hidden"))) private_td_seed_commit
#define td_step __attribute__((visibility("hidden"))) private_td_step
#define td_reference __attribute__((visibility("hidden"))) private_td_reference
#include "../transposed_down/numeric_smoke.cpp"
#undef td_reset
#undef td_group
#undef td_seed_begin
#undef td_seed_beat
#undef td_seed_commit
#undef td_step
#undef td_reference
#undef std

namespace {
// Mode 0 is unowned, 1 is transposed Dense, 2 is normal QK/PV.
unsigned mode=0, normalOpcode=0, normalCount=0, normalNext=0, normalProfile=0;
bool guarded=false, pristine=false, poisoned=false, groupOpen=false;
bool endIssued=false, ownerPending=false, replyPending=false, replyLast=false;
bool doneRetired=false, seedPending[5]={};
uint64_t ownerTag=0, ticket=0, nextTicket=1;
uint32_t groupTag=0;
struct Meta {unsigned context,last;};
Meta returned[8]; unsigned returnHead=0, returnCount=0;

bool seedsPending(){for(bool p:seedPending)if(p)return true;return false;}
bool quiescent(){return !groupOpen&&!returnCount&&!replyPending&&!seedsPending();}
int fault(){poisoned=true;endIssued=true;return -1;}
void beginGroup(uint32_t tag){
  groupOpen=true;endIssued=false;doneRetired=false;groupTag=tag;
  ticket=nextTicket++;returnHead=returnCount=0;
}
void pushResult(unsigned context,unsigned last){
  returned[(returnHead+returnCount)%8]={context,last};++returnCount;
}
}

extern "C" int td_reset(){
  int rc=private_td_reset();if(rc)return rc;
  mode=normalOpcode=normalCount=normalNext=normalProfile=0;
  pristine=true;poisoned=groupOpen=endIssued=ownerPending=replyPending=replyLast=doneRetired=false;
  ownerTag=ticket=0;groupTag=0;returnHead=returnCount=0;
  std::memset(seedPending,0,sizeof(seedPending));denseFmas=normalFmas=0;countArithmetic=0;
  // The monotonic ticket is deliberately not reset: late responses stay stale.
  return 0;
}

extern "C" int matrix_guard_enable(){
  if(guarded)return 0;
  if(!pristine||mode||!quiescent())return -4;
  guarded=true;return 0;
}
extern "C" int matrix_acquire(unsigned selected,uint64_t tag){
  if(!guarded||poisoned||mode||!quiescent()||(selected!=1&&selected!=2))return -4;
  mode=selected;ownerTag=tag;ownerPending=true;return 0;
}
extern "C" int matrix_owner_reply_retire(unsigned selected,uint64_t tag){
  if(selected!=mode||tag!=ownerTag||!ownerPending||!quiescent())return -4;
  ownerPending=false;return 0;
}
extern "C" int matrix_release(unsigned selected,uint64_t tag){
  if(selected!=mode||tag!=ownerTag||ownerPending||!quiescent())return -4;
  mode=0;ownerTag=0;return 0;
}
extern "C" uint64_t matrix_ticket(){return ticket;}
extern "C" uint64_t matrix_dense_fmas(){return denseFmas;}
extern "C" uint64_t matrix_normal_fmas(){return normalFmas;}
extern "C" uintptr_t matrix_accumulator_address(){return reinterpret_cast<uintptr_t>(accum);}
extern "C" unsigned matrix_accumulator_bytes(){return sizeof(accum);}
extern "C" unsigned matrix_state(){
  return mode|(unsigned(groupOpen)<<2)|(unsigned(returnCount!=0)<<3)|
    (unsigned(endIssued&&!doneRetired)<<4)|(unsigned(replyPending)<<5)|
    (unsigned(seedsPending())<<6)|(unsigned(ownerPending)<<7)|(unsigned(poisoned)<<8);
}
extern "C" int matrix_abort(){
  if(!guarded||!mode)return -4;
  poisoned=true;if(groupOpen)endIssued=true;return 0;
}
extern "C" int matrix_done_ready(){return groupOpen&&endIssued&&!returnCount;}
extern "C" int matrix_result_retire(uint64_t id,unsigned context,unsigned last){
  if(id!=ticket||!returnCount)return -1;
  const Meta m=returned[returnHead];
  if(m.context!=context||m.last!=last)return -1;
  returnHead=(returnHead+1)%8;--returnCount;return 0;
}
extern "C" int matrix_done_retire(uint64_t id,uint32_t tag,unsigned error){
  if(id!=ticket||!groupOpen||!endIssued||returnCount)return -4;
  if(tag!=groupTag||error)poisoned=true;
  groupOpen=false;doneRetired=true;return 0;
}
extern "C" int matrix_seed_ack(uint64_t id,unsigned context,unsigned error){
  if(id!=ticket||context>=5||!seedPending[context])return -1;
  if(!error&&(seedOpen[context]||!bankValid[context]))return -1;
  seedPending[context]=false;
  if(error){seedOpen[context]=false;poisoned=true;endIssued=true;}
  return 0;
}
extern "C" int matrix_legacy_reply_retire(uint64_t id){
  if(id!=ticket||!replyPending||returnCount||(replyLast&&!doneRetired))return -4;
  replyPending=false;replyLast=false;return 0;
}

// Standalone callers retain the historical td_* API and arithmetic. The new
// full-chain service enables the guard before the first accepted group.
extern "C" int td_group(unsigned start,unsigned end,unsigned count){
  if(guarded&&(mode!=1||poisoned||!ownerPending||!quiescent()))return -4;
  int rc=private_td_group(start,end,count);
  if(!rc){pristine=false;if(guarded)beginGroup(uint32_t(ownerTag));}
  return rc;
}
extern "C" int td_seed_begin(unsigned context){
  if(guarded&&(mode!=1||!groupOpen||poisoned||endIssued||context>=5||seedPending[context]))return -4;
  int rc=private_td_seed_begin(context);
  if(!rc&&guarded)seedPending[context]=true;
  return rc;
}
extern "C" int td_seed_beat(unsigned context,unsigned index,const uint32_t* words){
  if(!words)return -1;
  if(guarded&&(mode!=1||!groupOpen||poisoned||endIssued))return -4;
  int rc=private_td_seed_beat(context,index,words);
  if(rc&&guarded)fault();return rc;
}
extern "C" int td_seed_commit(unsigned context){
  if(guarded&&(mode!=1||!groupOpen||poisoned||endIssued))return -4;
  int rc=private_td_seed_commit(context);
  if(rc&&guarded)fault();return rc;
}
extern "C" int td_step(unsigned k,unsigned context,unsigned clear,unsigned last,
                         unsigned finish,unsigned emit,const uint16_t* a,const uint16_t* b,uint32_t* out){
  if(!a||!b||(last&&!out))return -1;
  if(guarded&&(mode!=1||!groupOpen||poisoned||endIssued||context>=5||seedPending[context]||returnCount==8))return -4;
  // Unlike the standalone arithmetic helper, the shared service also owns the
  // declared group's completion obligation. Never close over missing contexts.
  if(guarded&&finish)for(unsigned c=0;c<contexts;c++)
    if(c!=context&&nextK[c]!=chunkEnd)return fault();
  countArithmetic=1;
  int rc=private_td_step(k,context,clear,last,finish,emit,a,b,out);
  countArithmetic=0;
  if(guarded){
    if(rc<0)fault();
    else{if(rc)pushResult(context,last);if(finish)endIssued=true;}
  }
  return rc;
}
extern "C" int td_reference(const uint32_t* a,const uint16_t* w,uint32_t* out,unsigned columns){
  if(guarded&&(mode||!quiescent()||poisoned))return -4;
  return private_td_reference(a,w,out,columns);
}

// Explicit host admission profile; no extra accumulator or hardware command.
// Profile0 retains the old Qwen2 per-step reply. Profile1 maps the existing
// Bf16CausalGqaOwner stream: QK K256/slice0, PV keys<=256/all8, emit-last only.
extern "C" int matrix_normal_group_v1(unsigned opcode,unsigned count,uint32_t tag,unsigned mask,unsigned profile){
  if(!guarded||mode!=2||!ownerPending||poisoned||!quiescent())return -4;
  beginGroup(tag);normalOpcode=opcode;normalCount=count;normalNext=0;normalProfile=profile;
  if(profile==0){
    if(mask!=1||(opcode!=0x23&&opcode!=0x24)||
       (opcode==0x23&&count!=8)||(opcode==0x24&&(!count||count>1024)))return fault();
  }else if(profile==1){
    if((opcode==0x23&&(count!=256||mask!=1))||
       (opcode==0x24&&(!count||count>256||mask!=255))||
       (opcode!=0x23&&opcode!=0x24))return fault();
  }else return fault();
  // Erase the SAME inherited resource; no normal-mode accumulator exists.
  for(unsigned c=0;c<5;c++)for(unsigned r=0;r<16;r++)
    for(unsigned col=0;col<256;col++)accum[c][r][col]=fp(0x7fc00001);
  return 0;
}
extern "C" int matrix_normal_group(unsigned opcode,unsigned count,uint32_t tag,unsigned mask){
  return matrix_normal_group_v1(opcode,count,tag,mask,0);
}
extern "C" int matrix_normal_step(unsigned index,unsigned context,unsigned clear,unsigned last,
                                   unsigned finish,unsigned emit,const uint16_t* a,const uint16_t* b,uint32_t* out){
  if(mode!=2||!groupOpen||poisoned||endIssued||returnCount||replyPending)return -4;
  if(normalProfile==1){
    if(!a||!b||!out||context||index!=normalNext||index>=normalCount||
       clear!=(index==0)||last!=(index+1==normalCount)||finish!=last||emit!=last)return fault();
    if(last)std::memset(out,0,4096*sizeof(uint32_t));
    const unsigned columns=normalOpcode==0x23?32:256;
    countArithmetic=2;
    for(unsigned r=0;r<16;r++)for(unsigned col=0;col<columns;col++){
      float& x=accum[0][r][col];if(clear)x=0.0f;
      x=matrix_observed_std::fma(fp(uint32_t(a[r])<<16),fp(uint32_t(b[col])<<16),x);
      if(last)out[r*256+col]=bits(x);
    }
    countArithmetic=0;++normalNext;
    if(last){pushResult(0,1);endIssued=true;return 1;}
    return 0;
  }
  replyPending=true;replyLast=bool(last);
  if(!a||!b||!out||context||index!=normalNext||index>=normalCount||
     clear!=(index==0)||last!=(index+1==normalCount)||finish!=last||emit!=1){replyLast=true;return fault();}
  // The endpoint leaves exception_flags_o unused. Neither special operands
  // nor nonfinite UNSELECTED cells are a Matrix protocol fault. Return every
  // computed word; Qwen2Block's owner checks only fmOut (QK diagonal/PV row0).
  // Owner packet construction supplies source padding; the generic service
  // computes all of selected slice zero and ignores the other seven slices.
  std::memset(out,0,4096*sizeof(uint32_t));
  countArithmetic=2;
  for(unsigned r=0;r<16;r++)for(unsigned col=0;col<32;col++){
    float& x=accum[0][r][col];if(clear)x=0.0f;
    x=matrix_observed_std::fma(fp(uint32_t(a[r])<<16),fp(uint32_t(b[col])<<16),x);
    out[r*256+col]=bits(x);
  }
  countArithmetic=0;++normalNext;
  pushResult(0,last);if(finish)endIssued=true;
  return 1; // Legacy emits every step, including non-last steps.
}
