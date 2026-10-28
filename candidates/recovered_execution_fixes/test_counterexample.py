import pathlib,json,sys,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'five_profile_byte_provider'))
import emit_cold128_programs as emit
out=[]
def overlap(x,y):return x[0]<y[1] and y[0]<x[1]
for p in (3,4):
 b,_=emit.common(p);cb,db,m=b.finish();r=m['launch']['regions'][3];w=(r['base'],r['limit']);M=128;K=2048;N=256
 a=m['tensors']['post_norm'];weight=m['tensors']['moe_weight_0'];dst=r['base']+65536
 spans=[(a['address'],a['address']+M*K*2),(weight['address'],weight['address']+K*N*2),(dst,dst+M*N*2)]
 alias=any(overlap(w,s) for s in spans)
 assert alias and not (K>2560 and alias)
 assert not overlap(spans[0],spans[2]) and not overlap(spans[1],spans[2])
 out.append(dict(profile=p,pc=next(x['pc'] for x in m['schedule'] if x['name']=='moe_full'),workspace=w,router_A_W_D=spans,old_prefixAlias_reject=alias,candidate_prefixAlias_reject=K>2560 and alias))
# Complete legal K/split domain. Trace the source's normal Down chunkBase,
# chunkDepth, savingPrefix and restoring transitions, not numerical operations.
cases=0
for split in range(128,2561,128):
 for k in range(32,8961,32):
  base=0;restoring=False;read=False;write=False
  while True:
   end=base+min(k-base,split);saving=end<k
   read |= restoring;write |= saving
   if not saving:break
   base=end;restoring=True
  assert (read or write)==(k>split)
  for aliases in (False,True):
   old=aliases;new=k>split and aliases
   if k>split:assert old==new
  cases+=1
import os
p=pathlib.Path(os.environ['FIXTURE_WORK'])
(p/'COUNTEREXAMPLE.json').write_text(json.dumps({'scope':'SOURCE_PREDICATE_AND_CONTROL_TRACE_ONLY_NOT_CHISEL_EXECUTION','router_counterexamples':out,'legal_k_split_cases':cases,'fullblock_pass':0,'rtl_pass':0},indent=2)+'\n')
print('PASS predicate/control only:',cases,'legal K/split combinations; 2 exact metadata router counterexamples')
