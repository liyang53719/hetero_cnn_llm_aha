"""Bit-oriented fused-SiLU edge vectors and producer/consumer envelope."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib,json,math,random,struct


def bits_to_f32(bits:int)->float:return struct.unpack('<f',int(bits&0xffffffff).to_bytes(4,'little'))[0]
def f32_to_bits(value:float)->int:
 value=float(value)
 if math.isfinite(value) and abs(value)>3.4028234663852886e38:value=math.copysign(math.inf,value)
 return int.from_bytes(struct.pack('<f',value),'little')
def bf16_to_f32(bits:int)->float:return bits_to_f32((int(bits)&0xffff)<<16)
def f32_to_bf16_rne(value:float)->int:
 word=f32_to_bits(value);exponent=(word>>23)&0xff;fraction=word&0x7fffff
 if exponent==0xff and fraction:return ((word>>16)&0xffff)|0x40
 return ((word+0x7fff+((word>>16)&1))&0xffffffff)>>16
def fp16_bits(value:float)->int:return int.from_bytes(struct.pack('<e',float(value)),'little')
def fp16_to_f32(bits:int)->float:return struct.unpack('<e',int(bits&0xffff).to_bytes(2,'little'))[0]
def classify_bf16(bits:int)->str:
 exponent=(bits>>7)&0xff;fraction=bits&0x7f
 if exponent==0xff:return 'nan' if fraction else ('-inf' if bits&0x8000 else '+inf')
 if exponent==0:return ('-zero' if bits&0x8000 else '+zero') if fraction==0 else 'subnormal'
 return 'normal'
def silu(value:float)->float:
 if math.isnan(value):return value
 if value==math.inf:return math.inf
 if value==-math.inf:return 0.0
 if value>=0:return value/(1.0+math.exp(-value))
 expv=math.exp(value);return value*expv/(1.0+expv)
def build_lut()->tuple[int,...]:return tuple(fp16_bits(silu(-8.0+16.0*i/127.0)) for i in range(128))
LUT=build_lut()
def bf16_to_q12_sat(bits:int)->int:
 exponent=(bits>>7)&0xff;fraction=bits&0x7f;significand=128+fraction
 if exponent==255:magnitude=32768
 elif exponent==0:magnitude=0
 else:
  shift=exponent-122
  if shift>=0:magnitude=significand<<shift
  else:
   right=-shift;magnitude=0 if right>=16 else (significand+(1<<(right-1)))>>right
  magnitude=min(magnitude,32768)
 return -magnitude if bits&0x8000 else magnitude
def hardware_silu(gate_bits:int)->float:
 gate=bf16_to_f32(gate_bits);exponent=(gate_bits>>7)&0xff;fraction=gate_bits&0x7f
 if exponent==0xff and fraction:return float('nan')
 q12=bf16_to_q12_sat(gate_bits)
 if (gate_bits&0x7fff)==0 or q12<=-32768:return 0.0
 if q12==0:return gate*.5
 if q12>=32768:return gate
 shifted=q12+32768;position_q12=(shifted*127)>>4;index=(position_q12>>12)&0x7f
 if index>=127:index=126
 fraction_q12=position_q12&0xfff;y0=fp16_to_f32(LUT[index]);y1=fp16_to_f32(LUT[index+1])
 return float(y0+(y1-y0)*(fraction_q12/4096.0))
def hardware_fused(gate_bits:int,up_bits:int)->int:return f32_to_bf16_rne(hardware_silu(gate_bits)*bf16_to_f32(up_bits))
def reference_fused(gate_bits:int,up_bits:int)->int:return f32_to_bf16_rne(silu(bf16_to_f32(gate_bits))*bf16_to_f32(up_bits))
def _edge_bits()->tuple[int,...]:
 values={0x0000,0x8000,0x0001,0x007f,0x0080,0x8080,0x3f80,0xbf80,0x4100,0xc100,0x40ff,0x4101,0xc0ff,0xc101,0x7f7f,0xff7f,0x7f80,0xff80,0x7fc0,0xffc1,0x7f81}
 for value in (-8.,-7.999,-4.,-1.,-.125,.125,1.,4.,7.999,8.):values.add(f32_to_bf16_rne(value))
 return tuple(sorted(values))
def special_vector_report()->dict[str,object]:
 gates=_edge_bits();ups=_edge_bits();records=[];finite_max_abs=0.;nan_gate_failures=0;open_edges=[];digest=hashlib.sha256()
 for gate in gates:
  for up in ups:
   actual=hardware_fused(gate,up);reference=reference_fused(gate,up);ac=classify_bf16(actual);rc=classify_bf16(reference);gc=classify_bf16(gate);uc=classify_bf16(up)
   if gc=='nan':accepted=ac=='nan';nan_gate_failures+=int(not accepted);policy='nan_gate_must_produce_nan_class'
   elif gc in ('+inf','-inf') or uc in ('+inf','-inf','nan'):
    accepted=ac==rc or (rc=='nan' and ac=='nan');policy='special_class_review'
    if not accepted:open_edges.append({'gate_bits':f'{gate:04x}','up_bits':f'{up:04x}','actual_class':ac,'reference_class':rc})
   else:
    accepted=True;policy='finite_approximation'
    if ac not in ('nan','+inf','-inf') and rc not in ('nan','+inf','-inf'):finite_max_abs=max(finite_max_abs,abs(bf16_to_f32(actual)-bf16_to_f32(reference)))
   digest.update(struct.pack('<HHHH',gate,up,actual,reference));records.append({'gate_bits':f'{gate:04x}','up_bits':f'{up:04x}','actual_bits':f'{actual:04x}','reference_bits':f'{reference:04x}','gate_class':gc,'up_class':uc,'actual_class':ac,'reference_class':rc,'policy':policy,'accepted_by_current_test_policy':accepted})
 if nan_gate_failures:raise AssertionError(nan_gate_failures)
 tiny=[]
 for gate in (0x0001,0x007f,0x0080,0x8001,0x807f,0x8080):
  actual=hardware_fused(gate,0x3f80);reference=reference_fused(gate,0x3f80);tiny.append({'gate_bits':f'{gate:04x}','actual':bf16_to_f32(actual),'reference':bf16_to_f32(reference),'actual_bits':f'{actual:04x}','reference_bits':f'{reference:04x}'})
 return {'status':'PASS','schema_version':1,'evidence_class':'fused_SiLU_special_vector_E0_not_RTL_E1','edge_policy_status':'REQUIRES_LOCAL_RTL_DECISION','gate_values':len(gates),'up_values':len(ups),'vectors':len(records),'finite_max_abs_vs_exact_silu_bf16':finite_max_abs,'nan_checked_by_class_not_payload':True,'open_special_class_cases':len(open_edges),'open_special_examples':open_edges[:32],'tiny_zero_bin_bias':tiny,'required_decisions':['Define finite gate <= -8 behavior for infinite up operands; current zero clamp can produce NaN.','Define q12==0 nonzero BF16 behavior; current even-sized LUT midpoint has about 1e-3 zero-bin bias.','Keep NaN comparison class-based rather than payload-bit-exact.'],'sha256':digest.hexdigest(),'records':records}
@dataclass(frozen=True)
class StallScenario:
 lanes:int;queue_depth:int;producer_width:int;tile_pairs:int=512;mean_interval_cycles:int=6;consumer_stall_probability:float=0.;tiles:int=64;seed:int=0x51a7
@dataclass(frozen=True)
class StallResult:
 produced:int;consumed:int;producer_stalled_pairs:int;producer_stall_cycles:int;max_queue:int;cycles:int
 @property
 def producer_stall_fraction(self)->float:return self.producer_stalled_pairs/max(self.produced+self.producer_stalled_pairs,1)
def simulate_stall(s:StallScenario)->StallResult:
 if min(s.lanes,s.queue_depth,s.producer_width,s.tile_pairs,s.mean_interval_cycles,s.tiles)<=0:raise ValueError('scenario geometry')
 rng=random.Random(s.seed);queue=0;produced=consumed=stalled_pairs=stall_cycles=max_queue=0;cycle=0;next_tile_cycle=0;active_remaining=0;total_pairs=s.tile_pairs*s.tiles
 while consumed<total_pairs:
  if active_remaining==0 and produced<total_pairs and cycle>=next_tile_cycle:active_remaining=min(s.tile_pairs,total_pairs-produced);next_tile_cycle+=s.tile_pairs*s.mean_interval_cycles
  offer=min(s.producer_width,active_remaining);accepted=min(offer,s.queue_depth-queue)
  if offer>accepted:stalled_pairs+=offer-accepted;stall_cycles+=1
  active_remaining-=accepted;queue+=accepted;produced+=accepted
  if rng.random()>=s.consumer_stall_probability:take=min(s.lanes,queue);queue-=take;consumed+=take
  max_queue=max(max_queue,queue);cycle+=1
  if cycle>total_pairs*s.mean_interval_cycles*20:raise RuntimeError('stall model did not drain')
 return StallResult(produced,consumed,stalled_pairs,stall_cycles,max_queue,cycle)
def stall_envelope_report()->dict[str,object]:
 results=[]
 for lanes in (1,2):
  for queue_depth in (8,16,32,64,512):
   for producer_width in (1,4,16,32):
    for backpressure in (0.,.05,.10,.20):
     scenario=StallScenario(lanes,queue_depth,producer_width,consumer_stall_probability=backpressure);result=simulate_stall(scenario);results.append({'scenario':asdict(scenario),'result':{**asdict(result),'producer_stall_fraction':result.producer_stall_fraction}})
 average=next(x for x in results if x['scenario']['lanes']==1 and x['scenario']['queue_depth']==8 and x['scenario']['producer_width']==1 and x['scenario']['consumer_stall_probability']==0.)
 if average['result']['producer_stall_fraction']!=0:raise AssertionError(average)
 digest=hashlib.sha256(json.dumps(results,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return {'schema_version':1,'status':'PASS','evidence_class':'producer_stall_envelope_E0_not_measured_integration','scenarios':len(results),'results':results,'sha256':digest,'decision':'Do not select one versus two lanes from average rate alone; local integration must report burst width, queue high-water and producer stall.','local_required_counters':['pairs_offered','pairs_accepted','producer_stall_cycles','producer_stalled_pairs','queue_high_water','consumer_backpressure_cycles']}
def combined_report()->dict[str,object]:return {'schema_version':1,'status':'PASS','special_vectors':special_vector_report(),'stall_envelope':stall_envelope_report()}
