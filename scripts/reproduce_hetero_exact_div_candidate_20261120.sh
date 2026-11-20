#!/usr/bin/env bash
# Isolated fixed exact Div leaf + BF16 first-PC scheduler study.
# Usage: bash scripts/reproduce_hetero_exact_div_candidate_20261120.sh WORKSPACE [--execute]
# This stages source only by default. --execute needs pinned prior tool receipts,
# local Scala/CIRCT/Verilator provisioning and CPU1; no download or weight input.
# This does not run original Host or build/replay the unified five-block RTL.
set -euo pipefail
[[ $# -ge 1 && $# -le 2 && ( ${2:-} == "" || ${2:-} == --execute ) ]] || exit 2
cd -P -- "$1"
root=$(pwd -P)
mkdir -p round_20261120T1333
stage=round_20261120T1333/sfu_repro_$(date -u +%Y%m%dT%H%M%S)_$$
mkdir -m 700 -- "$stage"
cat > "$stage/PipelinedExactFp32DivV2.scala" <<'PINNED_SOURCE_EOF'
// SPDX-License-Identifier: Apache-2.0
package heteronpu.continuous

import chisel3._
import chisel3.util._

class PipelinedExactDivRequestV2 extends Bundle {
  val identity = new UnifiedSharedOperationTagV3
  val a = UInt(32.W)
  val b = UInt(32.W)
}
class PipelinedExactDivResultV2 extends Bundle {
  val identity = new UnifiedSharedOperationTagV3
  val value = UInt(32.W)
  val error = Bool()
}

/** Opt-in standalone candidate for the single shared exact scalar Div path.
  * 26 restoring quotient digits (one digit per stage), no quotient approximation,
  * no flush-to-zero shortcut, no FMA. This does not replace the existing sqrt
  * or install the divider in a top. Numbers reflect source latency, not timing.
  * Credit covers every accepted op through output retirement; no loss on stall.
  * Reset invalidates in-flight requests and therefore requires owner isolation.
  */
class PipelinedExactFp32DivV2 extends Module {
  private val digits = 26
  private val capacity = 32
  val io = IO(new Bundle {
    val request = Flipped(Decoupled(new PipelinedExactDivRequestV2))
    val result = Decoupled(new PipelinedExactDivResultV2)
    val drained = Output(Bool())
  })
  class Step extends Bundle {
    val identity = new UnifiedSharedOperationTagV3
    val sign = Bool()
    val zeroNumerator = Bool()
    val invalid = Bool()
    val exponent = SInt(10.W)
    val divisor = UInt(24.W)
    val remainder = UInt(24.W)
    val quotient = UInt(27.W)
  }
  def normalized(x: UInt): (UInt,SInt,Bool,Bool) = {
    val e = x(30,23)
    val f = x(22,0)
    val sub = e === 0.U
    val mant = Cat(!sub, f)
    val sh = PriorityEncoder(Reverse(mant))
    val norm = (mant << sh)(23,0)
    val bias = Mux(sub, -126.S(10.W) - sh.zext, e.zext - 127.S(10.W))
    (norm, bias, !mant.orR, e.andR)
  }

  val steps = Reg(Vec(digits+1, new Step))
  val valid = RegInit(VecInit(Seq.fill(digits+1)(false.B)))
  val queue = Module(new Queue(new PipelinedExactDivResultV2, capacity, pipe=false, flow=false))
  val debt = RegInit(0.U(log2Ceil(capacity+1).W))
  val retire = io.result.fire
  io.request.ready := debt < capacity.U || retire
  io.drained := debt === 0.U
  io.result <> queue.io.deq

  val (am,ae,az,an) = normalized(io.request.bits.a)
  val (bm,be,bz,bn) = normalized(io.request.bits.b)
  val needShift = am < bm
  val numerator = Mux(needShift, Cat(am,0.U(1.W)), am.pad(25))
  valid(0) := io.request.fire
  when(io.request.fire) {
    steps(0).identity := io.request.bits.identity
    steps(0).sign := io.request.bits.a(31) ^ io.request.bits.b(31)
    steps(0).zeroNumerator := az
    steps(0).invalid := an || bn || bz
    steps(0).exponent := ae - be - needShift.asUInt.zext
    steps(0).divisor := bm
    steps(0).remainder := (numerator-bm.pad(25))(23,0)
    steps(0).quotient := 1.U
  }
  for(i <- 1 to digits) {
    val prev = steps(i-1)
    val twice = Cat(prev.remainder,0.U(1.W))
    val d = prev.divisor.pad(25)
    val bit = twice >= d
    valid(i) := valid(i-1)
    when(valid(i-1)) {
      steps(i) := prev
      steps(i).remainder := Mux(bit,twice-d,twice)(23,0)
      steps(i).quotient := Cat(prev.quotient(25,0),bit)
    }
  }

  val last = steps(digits)
  val e = last.exponent
  val huge = e > 127.S
  val tinySubnormal = e < -150.S
  val subnormal = e < -126.S
  val delta = (-126.S(10.W) - e).asUInt
  // Numeric branch that can round: shift 3 (normal) through 27 (half minsub).
  val shift = Mux(!subnormal,3.U(5.W),Mux(tinySubnormal,27.U(5.W),(delta+3.U)(4,0)))
  val guardAt = shift-1.U
  val q = last.quotient
  val qKeep = (q >> shift)(23,0)
  val guard = (q >> guardAt)(0)
  val belowGuard = ((1.U(27.W) << guardAt) - 1.U)(26,0)
  val sticky = (q & belowGuard).orR || last.remainder.orR
  val inexact = guard || sticky
  val roundUp = guard && (sticky || qKeep(0))
  val rounded = qKeep +& roundUp.asUInt
  val carry = rounded(24)
  val afterExp = e + carry.asUInt.zext
  val overflow = huge || (!subnormal && afterExp > 127.S)
  // Legacy HardFloat tininess-after-rounding uses the precision of a
  // normal significand with *unbounded exponents*. Do not substitute "encoded
  // result is subnormal": an inexact result can encode min-normal but stay
  // tiny by this rule (0x00ffffff / 0x40000000 is the tie witness).
  val unboundedCarry = q(26,3).andR && q(2)
  val tinyAfterUnboundedRound = subnormal && !(e === -127.S && unboundedCarry)
  val underflow = tinySubnormal || (tinyAfterUnboundedRound && inexact)
  val normalExponent = (afterExp+127.S).asUInt
  val fraction = rounded(22,0)
  val subEncoding = Cat(0.U(7.W),rounded(23),fraction)
  val normalEncoding = Cat(normalExponent(7,0), Mux(carry,0.U(23.W),fraction))
  val bad = last.invalid || (!last.zeroNumerator && (underflow || overflow))
  val magnitude = Mux(last.zeroNumerator || bad,0.U(31.W),Mux(subnormal,subEncoding,normalEncoding))
  queue.io.enq.valid := valid(digits)
  queue.io.enq.bits.identity := last.identity
  queue.io.enq.bits.value := Cat(last.sign,magnitude)
  queue.io.enq.bits.error := bad

  when(io.request.fire && !retire) { debt := debt + 1.U }
  when(!io.request.fire && retire) { debt := debt - 1.U }
  assert(debt === PopCount(valid) +& queue.io.count, "exact div credit conservation")
  assert(!queue.io.enq.valid || queue.io.enq.ready, "exact div output credit reserved")
  assert(!(retire && debt === 0.U), "exact div retired without debt")
}
PINNED_SOURCE_EOF
cat > "$stage/EmitExactDivV2.scala" <<'PINNED_SOURCE_EOF'
package heteronpu.continuous
import circt.stage.ChiselStage
import java.nio.file.{Files, Paths}
object EmitExactDivV2 {
  def main(args: Array[String]): Unit = {
    require(args.length == 1)
    val fir = ChiselStage.emitCHIRRTL(new PipelinedExactFp32DivV2)
    Files.write(Paths.get(args(0)), fir.getBytes("UTF-8"))
  }
}
PINNED_SOURCE_EOF
cat > "$stage/build.py" <<'PINNED_SOURCE_EOF'
import hashlib,json,os,shlex,subprocess
from pathlib import Path
d=Path(__file__).resolve().parent;r=d.parents[1];old=r/'round_20261120T1133/big'
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pinned(p,expected):
 if h(p)!=expected:raise RuntimeError('artifact pin mismatch '+str(p))
 return json.loads(p.read_text())
a=pinned(old/'SCALA_COMPILE.json','44e50704395c665dc7509735935d10a4454bef3c344e7bf7d5923ae6d3d3e6be')['argv']
b=pinned(old/'l0-and-l3_ELAB.json','a2db435a432c8836c2f52da9e1b1abd1c780bb4b0943ad589424ab1a93e6ba25')['argv']
old_root=a[5].split('=',1)[1].rsplit('/round_20261120T1133/',1)[0]
if not old_root.startswith('/') or old_root=='/': raise RuntimeError('historical workspace path')
a=[x.replace(old_root+'/',str(r)+'/') for x in a]
b=[x.replace(old_root+'/',str(r)+'/') for x in b]
def go(name,cmd,cap=120,env=None):
 with (d/(name+'.log')).open('x') as f:
  print(shlex.join(cmd),file=f,flush=True)
  run=subprocess.run(cmd,cwd=d,stdout=f,stderr=subprocess.STDOUT,timeout=cap,env=env)
  if run.returncode:raise RuntimeError(name+' exit '+str(run.returncode))
m=d/'classes';m.mkdir();tmp=d/'java_tmp';tmp.mkdir()
a[2]='-Xmx768m';a[5]='-Djava.io.tmpdir='+str(tmp);a[13]=str(m)
go('SCALA',a[:14]+[str(d/'PipelinedExactFp32DivV2.scala'),str(d/'EmitExactDivV2.scala')])
b[2]='-Xmx768m';b[5]=a[5];b[7]=str(m)+os.pathsep+b[7]
f=d/'ExactDiv.fir';v=d/'ExactDiv.sv'
go('CHISEL',b[:8]+['heteronpu.continuous.EmitExactDivV2',str(f)])
fir=r/'round_20261119T1033/toolchain/circt/firtool-1.163.0/bin/firtool'
go('FIRTOOL',[str(fir),str(f),'-disable-all-randomization','-o',str(v)],cap=100)
with (d/'BUILD.json').open('x') as z:json.dump({'scope':'standalone exact Div candidate, no original Host or unified RTL', 'sha':{p.name:h(p) for p in [f,v,d/'PipelinedExactFp32DivV2.scala',fir]}},z,indent=2)
PINNED_SOURCE_EOF
cat > "$stage/vectors.py" <<'PINNED_SOURCE_EOF'
"""Independent Fraction test stimulus for exact IEEE binary32 division policy."""
from pathlib import Path
import hashlib,random,sys
s=Path(__file__).resolve(); r=s.parents[2]
src=r/'round_20261120T1133/sfu/exact_sfu.py'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0,str(src.parent))
from exact_sfu import finite, MAX, INF, SIGN, nearest, value, sgn
from fractions import Fraction

def ref_div(a,b):
 if not finite(a) or not finite(b) or not value(b):
  return None, True
 x=abs(value(a)/value(b))
 z,inexact=nearest(lambda r:sgn(x-r))
 # Independently derive tininess at binary24 significant-precision RNE before
 # constraining the exponent. Around 2**-126 the prior normal in this
 # unbounded lattice is 2**-126 - 2**-150. Tie rounds to the even min-normal.
 midpoint_to_least_normal=Fraction(2)**-126-Fraction(2)**-151
 error=z==INF or (x<midpoint_to_least_normal and inexact)
 return z|((a^b)&SIGN),error
sg=0x80000000
pairs=[(0,0x3f800000),(sg,0x3f800000),(0,0xbf800000),(sg,0xbf800000),(0,0),(0,sg),
 (0x3f800000,0),(0x3f800000,sg),(0x7f800000,0x3f800000),(0x7fc10101,0x3f800000),
 (0x3f800000,0xffc10101),(1,0x40000000),(3,0x40000000),(2,0x40000000),
 (0x00800000,0x40000000),(0x7f7fffff,0x3f000000),(0x3f800000,0x40400000),
 (0x00800000,0x40000001),(0x00ffffff,0x40000000),(0x00800000,0x3f800000),
 (0x007fffff,0x3f800000),(0x007fffff,0x3f7fffff),(0x00800001,0x40000000),
 (0x007fffff,0x3f400001),(0x7f7fffff,0x3f7fffff),(1,1),(1,0x007fffff),
 (0x007fffff,1),(0x7f7fffff,0x007fffff),(0x007fffff,0x7f7fffff)]
rng=random.Random(202611201333)
def sign():return sg if rng.getrandbits(1) else 0
def random_finite():return sign() | (rng.randrange(255)<<23) | rng.getrandbits(23)
def mix(e):return sign() | (e<<23) | rng.getrandbits(23)
for i in range(1800):
 pairs.append((random_finite(),random_finite()))
for i in range(800):
 ea=rng.randrange(255); eb=max(0,min(254,ea+rng.choice([-130,-128,-127,-126,-125,-124,-1,0,1,125,126,127,128,149,150,151])))
 pairs.append((mix(ea),mix(eb)))
for i in range(150):
 # Dense near gradual and half-minsub boundaries, not random-normal only.
 pairs.append((sign()|rng.randrange(1,1<<23),mix(rng.choice([1,2,125,126,127,128,129,143,148,150,151]))))
for a,b in pairs:
 value_bits,err=ref_div(a,b)
 print(f'{a:08x} {b:08x} {0 if err else value_bits:08x} {int(err)}')
print('oracle source SHA256 '+sha(src),file=sys.stderr)
PINNED_SOURCE_EOF
cat > "$stage/test_div.cpp" <<'PINNED_SOURCE_EOF'
#include "VPipelinedExactFp32DivV2.h"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <array>
using T=VPipelinedExactFp32DivV2;
struct V{uint32_t a,b,gold;unsigned err;};
void need(bool c,const char*m){if(!c)throw std::runtime_error(m);}
using Tag=std::array<uint64_t,10>;
Tag tag(uint32_t i){return {uint64_t(i)*0xb776d208cf12a071ULL+0xade17b11afe4195cULL,
  i^0x7193db41U,(i+9)&255,(i+2)&31,(i+5)&31,(i>>1)&1,
  (i*1103515245U)^0xafff8001U,(i*23)&65535,i&3,i^0x83aad989U};}
void put(T&d,uint32_t i){
 const auto t=tag(i);
 d.io_request_bits_identity_owner_transactionId=t[0];
 d.io_request_bits_identity_owner_ownerSequence=t[1];
 d.io_request_bits_identity_owner_stage=t[2];d.io_request_bits_identity_owner_phase=t[3];
 d.io_request_bits_identity_owner_head=t[4];d.io_request_bits_identity_owner_chunk=t[5];
 d.io_request_bits_identity_owner_token=t[6];d.io_request_bits_identity_owner_tileOrdinal=t[7];
 d.io_request_bits_identity_resource=t[8];d.io_request_bits_identity_serial=t[9];
}
Tag get(const T&d){
 return {d.io_result_bits_identity_owner_transactionId,d.io_result_bits_identity_owner_ownerSequence,
 d.io_result_bits_identity_owner_stage,d.io_result_bits_identity_owner_phase,
 d.io_result_bits_identity_owner_head,d.io_result_bits_identity_owner_chunk,
 d.io_result_bits_identity_owner_token,d.io_result_bits_identity_owner_tileOrdinal,
 d.io_result_bits_identity_resource,d.io_result_bits_identity_serial};
}
int main(int argc,char**argv){try{
 need(argc==2,"test requires an independent stimulus file");
 std::vector<V>vv;V v;
 std::ifstream f(argv[1]);
 while(f>>std::hex>>v.a>>v.b>>v.gold>>v.err){need(v.err<=1,"oracle policy bit");vv.push_back(v);}
 need(f.eof()&&vv.size()==2780,"complete oracle vector file");
 for(unsigned mode=0;mode<2;mode++){
  T dut;unsigned accepted=0,retired=0,peak=0,stalls=0,errors=0;
  dut.reset=1;dut.clock=0;dut.io_request_valid=0;dut.io_result_ready=0;dut.eval();dut.clock=1;dut.eval();dut.reset=0;
  std::vector<unsigned>cycleByAcceptance;
  bool held=false;Tag heldTag{};uint32_t heldValue=0;bool heldError=false;
  unsigned cyc=0;
  for(;cyc<25000&&retired<vv.size();cyc++){
   dut.clock=0;dut.io_request_valid=accepted<vv.size();
   if(accepted<vv.size()){const auto &in=vv[accepted];dut.io_request_bits_a=in.a;dut.io_request_bits_b=in.b;put(dut,accepted);}
   const bool ready=mode==0||((cyc%223)>=103&&(cyc%11)!=6);
   dut.io_result_ready=ready;dut.eval();
   need(bool(dut.io_drained)==(accepted==retired),"drained qualification during live debt");
   if(held)need(dut.io_result_valid&&heldTag==get(dut)&&heldValue==dut.io_result_bits_value&&heldError==dut.io_result_bits_error,"tag/payload mutated under stall");
   held=dut.io_result_valid&&!ready;
   if(held){heldTag=get(dut);heldValue=dut.io_result_bits_value;heldError=dut.io_result_bits_error;}
   if(dut.io_request_valid&&dut.io_request_ready){
    if(mode==0)need(accepted==cyc,"unblocked candidate does not sustain input II=1");
    ++accepted;cycleByAcceptance.push_back(cyc);
   }else if(dut.io_request_valid)++stalls;
   if(dut.io_result_valid&&ready){
    need(retired<accepted&&get(dut)==tag(retired),"invalid tag or order");
    const auto &in=vv[retired];
    if(dut.io_result_bits_error!=in.err||(!in.err&&dut.io_result_bits_value!=in.gold)){
     std::cerr<<"mismatch index="<<retired<<" mode="<<mode<<std::hex<<" a="<<in.a<<" b="<<in.b
       <<" value="<<dut.io_result_bits_value<<" e="<<unsigned(dut.io_result_bits_error)
       <<" expected="<<in.gold<<" err="<<in.err<<'\n';return 1;
    }
    if(mode==0)need(cyc-cycleByAcceptance[retired]==28,"nonconstant candidate unblocked latency");
    ++retired;errors+=in.err;
   }
   if(accepted-retired>peak)peak=accepted-retired;
   dut.clock=1;dut.eval();
  }
  dut.clock=0;dut.io_request_valid=0;dut.io_result_ready=1;dut.eval();
  need(retired==vv.size()&&accepted==retired&&dut.io_drained&&!dut.io_result_valid,"missing terminal drain");
  need((mode==0&&stalls==0&&peak==28)||(mode==1&&stalls>0&&peak==32),"unexpected capacity/credit behavior");
  std::cout<<"PASS candidate-only mode="<<mode<<" accepted="<<accepted<<" retired="<<retired<<" policy_errors="<<errors
   <<" peak_debt="<<peak<<" input_stall_cycles="<<stalls<<" model_ticks="<<cyc<<"\n";
 }
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
PINNED_SOURCE_EOF
cat > "$stage/EmitLegacyPolicyV2.scala" <<'PINNED_SOURCE_EOF'
package heteronpu.continuous
import circt.stage.ChiselStage
import java.nio.file.{Files, Paths}
object EmitLegacyPolicyV2 {
  def main(args: Array[String]): Unit = {
    require(args.length == 1)
    val f = ChiselStage.emitCHIRRTL(new BlockScalarFloatPolicyV2)
    Files.write(Paths.get(args(0)), f.getBytes("UTF-8"))
  }
}
PINNED_SOURCE_EOF
cat > "$stage/build_legacy.py" <<'PINNED_SOURCE_EOF'
import hashlib,json,os,shlex,subprocess
from pathlib import Path
d=Path(__file__).resolve().parent;r=d.parents[1];old=r/'round_20261120T1133/big'
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pinned(p,expected):
 if h(p)!=expected:raise RuntimeError('artifact pin mismatch '+str(p))
 return json.loads(p.read_text())
a=pinned(old/'SCALA_COMPILE.json','44e50704395c665dc7509735935d10a4454bef3c344e7bf7d5923ae6d3d3e6be')['argv']
b=pinned(old/'l0-and-l3_ELAB.json','a2db435a432c8836c2f52da9e1b1abd1c780bb4b0943ad589424ab1a93e6ba25')['argv']
old_root=a[5].split('=',1)[1].rsplit('/round_20261120T1133/',1)[0]
if not old_root.startswith('/') or old_root=='/': raise RuntimeError('historical workspace path')
a=[x.replace(old_root+'/',str(r)+'/') for x in a]
b=[x.replace(old_root+'/',str(r)+'/') for x in b]
def go(name,cmd,cap=120,env=None):
 with (d/(name+'.log')).open('x') as f:
  print(shlex.join(cmd),file=f,flush=True)
  run=subprocess.run(cmd,cwd=d,stdout=f,stderr=subprocess.STDOUT,timeout=cap,env=env)
  if run.returncode:raise RuntimeError(name+' exit '+str(run.returncode))
m=d/'legacy_classes';m.mkdir();tmp=d/'legacy_java_tmp';tmp.mkdir()
a[2]='-Xmx768m';a[5]='-Djava.io.tmpdir='+str(tmp);a[13]=str(m)
go('LEGACY_SCALA',a[:14]+[str(d/'EmitLegacyPolicyV2.scala')])
b[2]='-Xmx768m';b[5]=a[5];b[7]=str(m)+os.pathsep+b[7]
f=d/'OriginalScalarPolicy.fir';v=d/'OriginalScalarPolicy.sv'
go('LEGACY_CHISEL',b[:8]+['heteronpu.continuous.EmitLegacyPolicyV2',str(f)])
fir=r/'round_20261119T1033/toolchain/circt/firtool-1.163.0/bin/firtool'
go('LEGACY_FIRTOOL',[str(fir),str(f),'-disable-all-randomization','-o',str(v)],cap=100)
with (d/'LEGACY_BUILD.json').open('x') as z:json.dump({'scope':'unchanged isolated legacy BlockScalarFloatPolicyV2; differential oracle fixture, no original Host', 'sha':{p.name:h(p) for p in [f,v,d/'EmitLegacyPolicyV2.scala',fir]}},z,indent=2)
PINNED_SOURCE_EOF
cat > "$stage/test_legacy.cpp" <<'PINNED_SOURCE_EOF'
#include "VBlockScalarFloatPolicyV2.h"
#include <fstream>
#include <iostream>
#include <vector>
#include <cstdint>
#include <stdexcept>
void need(bool b,const char*m){if(!b)throw std::runtime_error(m);}
int main(int argc,char**argv){try{
 need(argc==4,"usage: test_legacy DIV_VECTORS SQRT_VECTORS DIFFERENCE_LOG");
 VBlockScalarFloatPolicyV2 d;d.clock=0;d.reset=1;d.io_request_valid=0;d.io_result_ready=0;d.eval();d.clock=1;d.eval();d.reset=0;
 auto edge=[&]{d.clock=1;d.eval();};
 auto low=[&]{d.clock=0;d.eval();};
 std::ofstream out(argv[3]);
 unsigned allDiff=0;
 // Opcode is passed through the elaborated ScalarOp definition. Keep old division and sqrt isolated.
 constexpr unsigned divOp=2,sqrtOp=3;
 for(unsigned k=0;k<2;k++){
  std::ifstream f(argv[k+1]);uint32_t a,b,value;unsigned e,nn=0,errors=0,delta=0,minL=999,maxL=0;
  while(f>>std::hex>>a>>b>>value>>e){
   d.io_request_valid=1;d.io_request_bits_policy=0;d.io_request_bits_payload_op=k?sqrtOp:divOp;
   d.io_request_bits_payload_a=a;d.io_request_bits_payload_b=b;d.io_result_ready=0;
   low();need(d.io_request_ready,"legacy ready before stimulus");edge();d.io_request_valid=0;
   unsigned lat=0;
   for(;;){
    ++lat;low();
    if(d.io_result_valid)break;
    need(lat<100,"legacy response timeout");edge();
   }
   need(d.io_result_bits_policy==0&&!d.io_result_bits_primitiveFlagsValid,"wrong legacy primitive/policy flags");
   if(unsigned(d.io_result_bits_error)!=e||(!e&&d.io_result_bits_value!=value)){
    ++delta;
    out<<k<<' '<<nn<<std::hex<<' '<<a<<' '<<b<<' '<<d.io_result_bits_value<<' '<<unsigned(d.io_result_bits_error)
       <<' '<<value<<' '<<e<<std::dec<<'\n';
   }
   minL=lat<minL?lat:minL;maxL=lat>maxL?lat:maxL;
   ++nn;errors+=d.io_result_bits_error;
   // Hold one cycle before accepting; error and bits must not disappear.
   const auto v=d.io_result_bits_value;const auto err=d.io_result_bits_error;
   edge();d.io_result_ready=1;low();
   need(d.io_result_valid&&v==d.io_result_bits_value&&err==d.io_result_bits_error,"old payload unstable under stall");edge();
  }
  need(f.eof()&&nn==(k?108u:2780u),"incomplete legacy stimulus input");
  std::cout<<"legacy op="<<(k?"sqrt":"div")<<" tested="<<nn<<" policy_errors="<<errors<<" diff_vs_exact_rational="<<delta
   <<" latency_bounds_on_this_mix="<<minL<<".."<<maxL<<" cycles\n";
  allDiff+=delta;
 }
 return allDiff?2:0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
PINNED_SOURCE_EOF
cat > "$stage/rms_whole_pc0_study.py" <<'PINNED_SOURCE_EOF'
"""Block PC0 resource/calendar experiment, NOT the hardware, matrix or RTL.
Preserves original Qwen3.5 ordered BF16 RMS reduction DAG. Synthetic memory,
fixed stage latencies, fixed row slots. 64-wide option means 64 physical lanes
packing up to two independent 32-lane operations with the same opcode,
accepting at most once per two cycles; not merely renaming a 32-wide bank.
"""
import argparse,json,heapq
from collections import defaultdict
from dataclasses import dataclass

def require(ok,msg):
 if not ok: raise ValueError(msg)
@dataclass(frozen=True)
class Node:
 row:int
 kind:str
 op:str
 width:int
 parents:tuple

def graph(h,rows,slots):
 require(h in (1024,2048) and 1<=slots<=8 and rows==128,'reviewed scope')
 nodes=[]; reads=[]; store=[]
 def n(r,k,o,w,*deps):
  require(all(0<=p<len(nodes) for p in deps),'topological construction')
  nodes.append(Node(r,k,o,w,tuple(deps)));return len(nodes)-1
 beats=h//32
 gamma=[n(-1,'mem','gamma',32) for _ in range(beats)]
 for r in range(rows):
  free=(store[r-slots],) if r>=slots else ()
  x=[n(r,'mem','x',32,*free) for _ in range(beats)]
  reads.extend(x)
  lastRes=None
  for b in range(h//512):
   lastAcc=None
   for t in range(16):
    xx=x[16*b+t]
    sq=n(r,'v','mul',32,xx)
    lastAcc=n(r,'v','add',32,sq,*(() if lastAcc is None else (lastAcc,)))
   lastRes=n(r,'v','add',32,lastAcc,*(() if lastRes is None else (lastRes,)))
  # Preserve ascending 4-residue order inside every one of eight lanes.
  fold=None
  for _ in range(4):
   fold=n(r,'v','add',8,lastRes,*(() if fold is None else (fold,)))
  # Preserve original left fold across eight lanes, including initial +0.
  lastLane=None
  for _ in range(8):
   lastLane=n(r,'v','add',1,fold,*(() if lastLane is None else (lastLane,)))
  mu=n(r,'v','mul',1,lastLane)
  ep=n(r,'v','add',1,mu)
  rt=n(r,'sqrt','sqrt',1,ep)
  inv=n(r,'div','div',1,rt)
  wg=[]
  for b in range(beats):
   a=n(r,'v','mul',32,inv,x[b])
   # hoisted physical issue only; same independent +1 root, no fused reassociation
   g=n(r,'v','add',32,gamma[b],*free)
   m=n(r,'v','mul',32,a,g)
   material=n(r,'v','format',32,m)
   wg.append(n(r,'mem','store',32,material))
  store.append(n(r,'join','retireRow',0,*wg))
 return nodes

def simulate(h,lanes,*,slots=4,mem_interval=1,mem_latency=12,mem_credits=24,
             arith_latency=6,sqrt_latency=27,div_latency=28,vec_credits=None):
 require((lanes,mem_interval) in [(l,m) for l in (32,64) for m in (1,2,4)],'candidate cadence')
 vII=lanes//32
 credits={'v':vec_credits if vec_credits is not None else (arith_latency+vII-1)//vII+2,
          'mem':mem_credits,'sqrt':1,'div':32}
 intervals={'v':vII,'mem':mem_interval,'sqrt':sqrt_latency,'div':1}
 latency={'v':arith_latency,'mem':mem_latency,'sqrt':sqrt_latency,'div':div_latency}
 require(all(v>0 for v in (*credits.values(),*latency.values(),*intervals.values())),'nonpositive service')
 nodes=graph(h,128,slots); remaining=[len(x.parents) for x in nodes]
 depend=defaultdict(list)
 for i,x in enumerate(nodes):
  for p in x.parents:depend[p].append(i)
 ready=defaultdict(list);events=[]
 for i,x in enumerate(nodes):
  if remaining[i]==0:heapq.heappush(ready[(x.kind,x.op)],i)
 nextIssue=defaultdict(int); debt=defaultdict(int); peak=defaultdict(int)
 counts=defaultdict(int);retAt=[-1]*len(nodes);units=defaultdict(int); lane_work=0; rowret=[]
 issuedAt=[-1]*len(nodes); seq=0; completed=0
 opkeys={kind:sorted({(n.kind,n.op) for n in nodes if n.kind==kind}) for kind in (*credits,'join')}
 def issue(c,kind,indices,delay):
  nonlocal seq
  for i in indices:
   require(issuedAt[i]<0 and all(0<=retAt[p]<=c for p in nodes[i].parents),'dependency/order')
   issuedAt[i]=c
  seq+=1;heapq.heappush(events,(c+delay,seq,kind,indices))
  debt[kind]+=1;peak[kind]=max(peak[kind],debt[kind]);counts[kind]+=1
  if kind!='join': require(debt[kind]<=credits[kind],'credit overflow')
 def drain(c):
  nonlocal completed
  while events and events[0][0]==c:
   _,_,kind,ids=heapq.heappop(events);debt[kind]-=1
   for i in ids:
    require(retAt[i]<0,'duplicate retirement');retAt[i]=c;completed+=1
    if kind=='join':rowret.append(c)
    for child in depend[i]:
     remaining[child]-=1
     if remaining[child]==0:heapq.heappush(ready[(nodes[child].kind,nodes[child].op)],child)
 c=0
 while completed<len(nodes):
  drain(c)
  while ready[('join','retireRow')]:
   issue(c,'join',[heapq.heappop(ready[('join','retireRow')])],0)
   drain(c)
  for k in credits:
   q=[key for key in opkeys[k] if ready[key]]
   if not q or nextIssue[k]>c or debt[k]>=credits[k]:continue
   key=min(q,key=lambda key:ready[key][0])
   i=heapq.heappop(ready[key]);ids=[i]
   if k=='v' and lanes==64 and ready[key] and nodes[i].width+nodes[ready[key][0]].width<=64:
    ids.append(heapq.heappop(ready[key]))
   # Restrict 64-wide packing to two tags, even for partial 8/1-lane waves.
   if k=='v': lane_work+=sum(nodes[j].width for j in ids)
   for j in ids:units[nodes[j].op]+=1
   issue(c,k,ids,latency[k]);nextIssue[k]=c+intervals[k]
  c+=1;require(c<2_000_000,'unbounded incomplete schedule')
 require(not any(debt.values()) and not events and len(rowret)==128 and min(retAt)>=0,'not fully retired')
 require(units['gamma']==h//32 and units['x']==units['store']==128*h//32 and units['sqrt']==units['div']==128,'incorrect work totals')
 # "data-only" lower estimate: slot x buffers + once-resident gamma + row
 # output per slot + separate 32-FP32 residue/partial bank per 512 block.
 # Does not count credit payloads, masks/tags, room for source/destination data
 # overlap, banking or RAM implementation. Uses BF16 at original materialization.
 bits=16*(h*(2*slots+1))+32*32*(h//512+1)*slots
 return dict(H=h,physical_vector_lanes=lanes,issue_II=vII,vector_credit=credits['v'],row_slots=slots,
             PC0_prediction_cycles=max(rowret)+1,first_row_cycle=min(rowret),
             resident_data_bytes_lower_estimate=bits//8,lane_work=lane_work,
             vector_physical_slots_issued=counts['v']*lanes,
             vector_issue_ops=counts['v'],peak_outstanding=dict(sorted(peak.items())),
             per_op_transactions=dict(sorted(units.items())),
             memory_arrows=dict(read_beats=units['gamma']+units['x'],write_beats=units['store']),
             mem_interval=mem_interval,mem_latency=mem_latency,mem_credits=mem_credits,
             arith_latency=arith_latency,sqrt_latency=sqrt_latency,div_latency=div_latency,
             blocked_slot_release_requires_all_store_acks=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');a=parser.parse_args()
 rows=[]
 for h in ((1024,) if a.quick else (1024,2048)):
  for s in ((4,) if a.quick else (1,4)):
   for lanes in (32,64):
    for mem in ((1,) if a.quick else (1,4)):
     rows.append(simulate(h,lanes,slots=s,mem_interval=mem))
 print(json.dumps(dict(scope='SOURCE_DEPENDENCY_PC0_CYCLE_PREDICTION_ONLY',
   notes=['Single unified element issue port; packed 64 lane mode has two independent sub-tags; both lanes shapes retain current 4096 Matrix unchanged.',
   'Max one posted memory request per interval and finite credits. Synthetic models both, not DDR timing or a measured value.',
   'Sqrt/Div bounds sampled for the standalone leaves; 6-cycle Vector arithmetic latency is hypothetical. No matrix, no Qwen2 FP32, no full prefill utilization.',
   'Original gate/order includes exact +0 starts; each packed lane result must be separately RNE. No FMA, no arithmetic approximation.'],
   rows=rows),indent=2,sort_keys=True))
PINNED_SOURCE_EOF
cat > "$stage/test_rms.py" <<'PINNED_SOURCE_EOF'
import json, unittest
from pathlib import Path
from rms_whole_pc0_study import graph, simulate
d=Path(__file__).resolve().parent
class RmsStudy(unittest.TestCase):
 def test_exact_source_work(self):
  for h,count in ((1024,5228),(2048,10412)):
   n=graph(h,128,4)
   for r in (0,33,127):
    a=[x for x in n if x.row==r and x.op in ('add','mul','sqrt','div')]
    self.assertEqual(count,sum(v.width for v in a))
    self.assertEqual(sum(v.width for v in n if v.row==r and v.op=='format'),h)
 def test_write_acks_gate_reuse(self):
  h=2048;n=graph(h,128,4)
  for x in n:
   if x.op=='x' and x.row>=4:self.assertEqual([(x.row-4,'retireRow')],[(n[p].row,n[p].op) for p in x.parents])
   if x.op=='retireRow':self.assertEqual(len(x.parents),h//32);self.assertTrue(all(n[p].op=='store' for p in x.parents))
 def test_pressure_is_not_ideal(self):
  cases=json.loads((d/'RESULT.json').read_text())['rows']
  c={(x['H'],x['row_slots'],x['physical_vector_lanes'],x['mem_interval']):x for x in cases}
  for h in (1024,2048):
   for s in (1,4):
    for width in (32,64):
     a,b=c[h,s,width,1],c[h,s,width,4]
     self.assertEqual(a['lane_work'],b['lane_work'])
     self.assertLess(a['PC0_prediction_cycles'],b['PC0_prediction_cycles'])
     self.assertEqual(a['memory_arrows']['read_beats'],(128+1)*h//32)
    self.assertEqual(c[h,s,32,1]['lane_work'],c[h,s,64,1]['lane_work'])
 def test_credit_undersizing(self):
  a=simulate(1024,32,slots=4,vec_credits=1)
  b=simulate(1024,32,slots=4,vec_credits=8)
  self.assertGreater(a['PC0_prediction_cycles'],b['PC0_prediction_cycles'])
  self.assertEqual(a['lane_work'],b['lane_work']);self.assertEqual(a['peak_outstanding']['v'],1)
 def test_illegal_geometry(self):
  with self.assertRaisesRegex(ValueError,'reviewed scope'):graph(1536,128,4)
  with self.assertRaisesRegex(ValueError,'cadence'):simulate(1024,48)
if __name__=='__main__':unittest.main()
PINNED_SOURCE_EOF
printf 'Staged source %s\n' "$stage"
if [[ ${2:-} != --execute ]]; then exit 0; fi
sha256sum --check --strict <<'PINNED_TOOLS_AND_ORACLES'
44e50704395c665dc7509735935d10a4454bef3c344e7bf7d5923ae6d3d3e6be  round_20261120T1133/big/SCALA_COMPILE.json
a2db435a432c8836c2f52da9e1b1abd1c780bb4b0943ad589424ab1a93e6ba25  round_20261120T1133/big/l0-and-l3_ELAB.json
e117832a91c7e797c0659c8aede1a1cba9e1bff9735f52072ec34e8016fde93a  round_20261120T1133/sfu/exact_sfu.py
4cf7186648545162c5d4be93015f7d7244255f2709f5fbe7f7891e6d145a0482  round_20261120T1133/sfu/RESULT.json
25b61c42cd0a1b46a7dc68f3ede15a349e4ff2e629ab2dbef34fb4e3c83f8c03  round_20261119T1233/host/source/BlockScalarFloatPolicyV2.scala
31cdb3be147471d52e721f14914031c19b915bd7aaffe5c0e333393a0c7fb67d  round_20261119T1233/host/source/RoundAnyRawFNToRecFN.scala
9a6252ec84ddfd5816b7c34e2b37c3c477f91184537669fc28029737d2842157  round_20261119T1033/toolchain/circt/firtool-1.163.0/bin/firtool
619464a17a8c212219abceeeee23f529b72801ef594814ae32f4b9747fd38703  round_20261119T1433/idma/tools/verilator_runtime/usr/bin/verilator_bin
PINNED_TOOLS_AND_ORACLES
stage=$(realpath "$stage")
verilator="$root/round_20261119T1433/idma/tools/verilator_runtime/usr/bin/verilator"
unset VERILATOR_ROOT
taskset -c 1 python -B "$stage/vectors.py" > "$stage/STIM.txt" 2> "$stage/ORACLE.log"
python - <<'SQRT' > "$stage/SQRT_STIM.txt"
from pathlib import Path
import json
rows=json.loads(Path('round_20261120T1133/sfu/RESULT.json').read_text())['vectors']
for x in rows:
 if x['op']=='sqrt': print(x['a'],x['b'],x['expected_bits'] or '00000000',int(x['error']))
SQRT
taskset -c 1 python -B "$stage/build.py"
taskset -c 1 python -B "$stage/build_legacy.py"
cd -- "$stage"
taskset -c 1 "$verilator" --cc --exe --build -j 1 --assert --top-module PipelinedExactFp32DivV2 --Mdir "$stage/obj_dir" -CFLAGS '-O2' "$stage/ExactDiv.sv" "$stage/test_div.cpp" > "$stage/VERILATOR.log" 2>&1
taskset -c 1 "$stage/obj_dir/VPipelinedExactFp32DivV2" "$stage/STIM.txt" | tee "$stage/TEST.log"
taskset -c 1 "$verilator" --cc --exe --build -j 1 --assert --top-module BlockScalarFloatPolicyV2 --Mdir "$stage/legacy_obj" "$stage/OriginalScalarPolicy.sv" "$stage/test_legacy.cpp" > "$stage/LEGACY_VERILATOR.log" 2>&1
taskset -c 1 "$stage/legacy_obj/VBlockScalarFloatPolicyV2" "$stage/STIM.txt" "$stage/SQRT_STIM.txt" "$stage/LEGACY_DIFF.txt" | tee "$stage/LEGACY_TEST.log"
taskset -c 1 python -B "$stage/rms_whole_pc0_study.py" > "$stage/RESULT.json"
taskset -c 1 python -B "$stage/test_rms.py"
taskset -c 1 python -OB "$stage/test_rms.py"
sha256sum "$stage/ExactDiv.sv" "$stage/OriginalScalarPolicy.sv" "$stage/STIM.txt" "$stage/RESULT.json"
