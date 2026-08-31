"""Shared 16-value quant-frontend K-tail scheduler and regression model."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,math,random

BEAT_VALUES=16
FORMAT_BLOCK_BEATS={"FP16":1,"Q8_0":2,"Q6_K":16,"Q3_K":16}
@dataclass(frozen=True)
class TailBeat:
 format:str;global_beat:int;block_index:int;group_index:int;value_offset:int;valid_count:int;block_first:bool;block_last:bool;last:bool
def schedule_tail(k_values:int,format_name:str)->tuple[TailBeat,...]:
 if format_name not in FORMAT_BLOCK_BEATS:raise ValueError(format_name)
 if k_values<0:raise ValueError('k_values')
 total=math.ceil(k_values/BEAT_VALUES);block_beats=FORMAT_BLOCK_BEATS[format_name];beats=[]
 for beat in range(total):
  block=beat//block_beats;group=beat%block_beats;remaining=k_values-beat*BEAT_VALUES;valid=min(BEAT_VALUES,remaining);last=beat+1==total
  beats.append(TailBeat(format_name,beat,block,group,beat*BEAT_VALUES,valid,group==0,group+1==block_beats or last,last))
 return tuple(beats)
def validate_schedule(k_values:int,format_name:str)->None:
 beats=schedule_tail(k_values,format_name)
 if k_values==0:
  if beats:raise AssertionError('zero K')
  return
 if sum(b.valid_count for b in beats)!=k_values:raise AssertionError('coverage')
 covered=[]
 for beat in beats:
  if not 1<=beat.valid_count<=BEAT_VALUES:raise AssertionError('valid count')
  covered.extend(range(beat.value_offset,beat.value_offset+beat.valid_count))
  if beat.block_first!=(beat.group_index==0):raise AssertionError('block first')
 if covered!=list(range(k_values)):raise AssertionError('duplicate/gap')
 if sum(b.last for b in beats)!=1 or not beats[-1].last:raise AssertionError('last')
 for index,beat in enumerate(beats[:-1]):
  if beat.valid_count!=BEAT_VALUES:raise AssertionError('non-final partial beat')
  if beat.global_beat!=index:raise AssertionError('beat order')
def scheduled_dot(k_values:int,format_name:str,seed:int)->tuple[float,float]:
 rng=random.Random(seed);weights=[rng.randint(-32,31) for _ in range(k_values)];activations=[rng.uniform(-2.,2.) for _ in range(k_values)];block_beats=FORMAT_BLOCK_BEATS[format_name];blocks=math.ceil(len(schedule_tail(k_values,format_name))/block_beats) if k_values else 0;block_scale=[rng.uniform(.001,.2) for _ in range(blocks)];subscale=[rng.randint(-31,31) or 1 for _ in range(math.ceil(k_values/BEAT_VALUES))];direct=scheduled=0.
 for index in range(k_values):
  beat=index//BEAT_VALUES;block=beat//block_beats;scale=block_scale[block]
  if format_name in ('Q6_K','Q3_K'):scale*=subscale[beat]
  direct+=weights[index]*activations[index]*scale
 for beat in schedule_tail(k_values,format_name):
  scale=block_scale[beat.block_index]
  if format_name in ('Q6_K','Q3_K'):scale*=subscale[beat.global_beat]
  partial=sum(weights[i]*activations[i] for i in range(beat.value_offset,beat.value_offset+beat.valid_count));scheduled+=partial*scale
 return direct,scheduled
def tail_report(cases_per_format:int=2048,seed:int=0x6a17,dot_cases_per_format:int=512)->dict[str,object]:
 rng=random.Random(seed);boundaries=(0,1,15,16,17,31,32,33,255,256,257,511,512,513,1023,1024,1025,4095,4096,4097);results={};digest=hashlib.sha256();max_error=0.;total_cases=0
 for format_name in FORMAT_BLOCK_BEATS:
  lengths=list(boundaries);lengths.extend(rng.randrange(0,8193) for _ in range(max(0,cases_per_format-len(lengths))));max_beats=max_blocks=partial_cases=0
  for case,k_values in enumerate(lengths):
   validate_schedule(k_values,format_name);beats=schedule_tail(k_values,format_name);max_beats=max(max_beats,len(beats));max_blocks=max(max_blocks,max((b.block_index for b in beats),default=-1)+1);partial_cases+=int(bool(beats) and beats[-1].valid_count!=BEAT_VALUES)
   if case<dot_cases_per_format:
    direct,scheduled=scheduled_dot(k_values,format_name,seed^(case*0x9e37)^len(format_name));error=abs(direct-scheduled);max_error=max(max_error,error)
    if error>1e-8*max(1.,abs(direct)):raise AssertionError((format_name,k_values,direct,scheduled))
   digest.update(format_name.encode());digest.update(k_values.to_bytes(4,'little'))
   for beat in beats:digest.update(beat.global_beat.to_bytes(4,'little'));digest.update(beat.block_index.to_bytes(4,'little'));digest.update(bytes((beat.group_index,beat.valid_count,int(beat.block_first),int(beat.block_last),int(beat.last))))
   total_cases+=1
  results[format_name]={'cases':len(lengths),'block_beats':FORMAT_BLOCK_BEATS[format_name],'max_beats':max_beats,'max_blocks':max_blocks,'partial_tail_cases':partial_cases}
 return {'schema_version':1,'status':'PASS','evidence_class':'quant_K_tail_schedule_E0_not_RTL_E1','beat_values':BEAT_VALUES,'cases':total_cases,'dot_cases_per_format':dot_cases_per_format,'formats':results,'maximum_dot_difference':max_error,'sha256':digest.hexdigest(),'hardware_contract':{'shared_dot_lanes':True,'format_specific_multiplier_array':False,'tail_behavior':'zero_mask_invalid_values_and_accumulate_only_valid_count','required_counters':['beats_issued','valid_values','masked_values','blocks_completed']}}
