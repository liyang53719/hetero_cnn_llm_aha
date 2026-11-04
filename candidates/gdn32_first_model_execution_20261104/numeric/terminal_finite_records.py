"""Bounded host classification projection, never numerical or causal acceptance.
Caller must bind the V2 readonly contract, actual source pins and closed log.
"""
import hashlib,json,re
from pathlib import Path
SCHEMA_SHA256='10ef123a49d3490454b9f62ceb2ec63a1ac7325eb688cb001729b68af3c1fde4'
PREFIX='HOST_TERMINAL_FINITE_SUMMARY_V1'
LIMIT=1024
SCHEMA_REL='candidates/model_candidate_build_20261101/TERMINAL_FINITE_RECORD_SCHEMA.json'
def need(v,s):
 if not v:raise ValueError(s)
def schema(path):
 raw=Path(path).read_bytes();need(len(raw)<=16384 and hashlib.sha256(raw).hexdigest()==SCHEMA_SHA256,'fixed terminal record schema');return json.loads(raw)
def parse_records(lines,schema_path):
 s=schema(schema_path);records=[];size=0
 for line in lines:
  need(type(line)is str,'text line')
  if not line.startswith('HOST_TERMINAL_FINITE'):continue
  need(not records and line.isascii()and len(line)<=LIMIT,'one bounded ASCII terminal record')
  size+=len(line.encode('ascii'));need(size<=LIMIT,'bounded terminal records')
  text=line[:-1]if line.endswith('\n')else line
  need('\n'not in text and '\r'not in text,'single LF terminal record')
  parts=text.split(' ');need(parts[0]==PREFIX and len(parts)==1+len(s['record_proposed_fields']),'exact terminal prefix/cardinality')
  r={}
  enums={'mapping':s['mapping_enum'],'first_nonfinite_kind':s['kind_enum'],'first_nonfinite_region':s['region_enum']}
  for key,token in zip(s['record_proposed_fields'],parts[1:]):
   need(token.startswith(key+'=')and token.count('=')==1,'exact ordered terminal field');value=token[len(key)+1:]
   if key=='schema_sha256':need(value==SCHEMA_SHA256,'terminal schema identity');r[key]=value
   elif key in enums:need(value in enums[key],'terminal enum');r[key]=value
   else:
    need(len(value)<=20 and re.fullmatch(r'(0|[1-9][0-9]*)',value)is not None,'canonical terminal integer');n=int(value);need(n<(1<<64),'terminal uint64');r[key]=n
  for key in ('sample_valid','result_last','result_error','fault_at_target_pc'):need(r[key]in(0,1),'terminal boolean')
  need(r['fault_at_target_pc']==int(r['fault_pc']==1),'fault PC annotation, not causality')
  if not r['sample_valid']:
   nonzero={'schema_sha256','mapping','first_nonfinite_kind','first_nonfinite_region','first_nonfinite_index','fault_pc','fault_at_target_pc'}
   need(all(v==0 for k,v in r.items()if k not in nonzero)and r['first_nonfinite_index']==4096 and all(r[k]=='NONE'for k in enums),'canonical empty terminal sample')
  else:
   need(r['accepted_samples']>0 and r['pc']==1 and r['completions']==1 and r['active_cycle']<=r['cycle'],'accepted target sample counters')
   need(r['ng']<(1<<16)and r['context']<(1<<3),'actual scalar field widths')
   counts=('finite','nan','positive_infinity','negative_infinity','effective_words','padding_words','unknown_region_words','nonfinite_effective','nonfinite_padding','nonfinite_unknown_region')
   need(r['words']==4096 and all(r[k]<=4096 for k in counts),'fixed terminal word counts')
   nf=sum(r[k]for k in ('nan','positive_infinity','negative_infinity'))
   need(r['finite']+nf==4096,'IEEE count partition')
   need(sum(r[k]for k in ('effective_words','padding_words','unknown_region_words'))==4096,'region count partition')
   need(sum(r[k]for k in ('nonfinite_effective','nonfinite_padding','nonfinite_unknown_region'))==nf,'nonfinite region partition')
   for a,b in (('nonfinite_effective','effective_words'),('nonfinite_padding','padding_words'),('nonfinite_unknown_region','unknown_region_words')):need(r[a]<=r[b],'nonfinite region bound')
   ng=r['ng'];context=r['context'];cols=min(160,1536-ng)if ng<1536 else 0
   supported=ng<1536 and ng%160==0 and context<(cols+31)//32
   need(r['mapping']==('SUPPORTED'if supported else'UNSUPPORTED_MAPPING'),'mapping predicate')
   def region(i):
    row,col=divmod(i,256);n=ng+32*context+16*(col//128)+row
    return 'UNKNOWN'if not supported else('EFFECTIVE'if col%128<128 and n<1536 and n<ng+cols else'PADDING')
   actual={x:0 for x in ('EFFECTIVE','PADDING','UNKNOWN')}
   for i in range(4096):actual[region(i)]+=1
   need((r['effective_words'],r['padding_words'],r['unknown_region_words'])==(actual['EFFECTIVE'],actual['PADDING'],actual['UNKNOWN']),'exact logical region counts')
   first=r['first_nonfinite_index'];kind=r['first_nonfinite_kind'];reg=r['first_nonfinite_region']
   if nf==0:need(first==4096 and kind=='NONE'and reg=='NONE','empty nonfinite index')
   else:
    need(first<4096 and kind in ('NAN','POS_INF','NEG_INF')and reg==region(first),'first nonfinite classification')
    need(r[{'NAN':'nan','POS_INF':'positive_infinity','NEG_INF':'negative_infinity'}[kind]]>0,'first kind has count')
    need(r[{'EFFECTIVE':'nonfinite_effective','PADDING':'nonfinite_padding','UNKNOWN':'nonfinite_unknown_region'}[reg]]>0,'first region has count')
    need(nf<=4096-first,'first nonfinite positional bound')
  records.append(r)
 return dict(schema='FINITE_TERMINAL_CLASSIFICATION_LOG_PROJECTION_V1',status='PRESENT_VALID'if records else'ABSENT',schema_sha256=SCHEMA_SHA256,record_count=len(records),record_bytes=size,sample=records[0]if records else None,fault_cause_established=False,numerical_pass=False,root_cause_inferred=False,scope='LAST_ACCEPTED_PC1_TERMINAL_CLASSIFICATION_NOT_CAUSAL_OR_NUMERICAL_ACCEPTANCE')
