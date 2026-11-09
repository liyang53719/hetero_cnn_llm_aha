"""Deterministic synthetic source-order samples; generated arrays stay local."""
import pathlib,hashlib,json
R=pathlib.Path(__file__).resolve().parent
source=(R/'scalar_core.py').read_bytes()
assert hashlib.sha256(source).hexdigest()==json.loads((R/'ORACLE_PINS.json').read_text())['scalar_core.py']
n={};exec(compile(source,str(R/'scalar_core.py'),'exec'),n)
bits,word,cumulative,sub,exp=(n[k] for k in ('bits','word','cumulative','sub','exp_negative'))
g=n['fixture']()[3]; cases=[]; pool_records=[]
for policy in (0,1):
 pool=[]
 for chunk in (0,1):
  c=cumulative(g[chunk*64:chunk*64+64],policy)
  pool += [(chunk,'cumulative',i,-1,x) for i,x in enumerate(c)]
  pool += [(chunk,'remain',i,63,sub(c[-1],x)) for i,x in enumerate(c)]
  pool += [(chunk,'decay',63,-1,c[-1])]
  pool += [(chunk,'pair',i,j,sub(c[i],c[j])) for i in range(64) for j in range(i+1)]
 # Stratify independently in each class/chunk, including endpoints.
 for chunk in (0,1):
  for kind in ('cumulative','remain','decay','pair'):
   group=[x for x in pool if x[:2]==(chunk,kind)]
   for idx in sorted(set(round(i*(len(group)-1)/4) for i in range(5))):
    ch,k,i,j,x=group[idx]; cases.append((policy,bits(x),bits(exp(x,policy))))
    pool_records.append(dict(policy=policy,chunk=ch,kind=k,row=i,column=j,input_hex=f'{bits(x):08x}',expected_hex=f'{bits(exp(x,policy)):08x}'))
# Explicit finite-domain numerical stress, independent of the synthetic sequence.
for policy in (0,1):
 for u in (0,0x80000000,0x80000001,0xc29fffff,0xc2a00000,0xc2a00001,0xc2aeac50,0xc2b72752,0xc2cff1b4,0xc2cff1b5,0xc2d00000,0xff7fffff):
  cases.append((policy,u,bits(exp(word(u),policy))))
(R/'Fixture.scala').write_text('object Fixture { val cases=Vector(\n'+',\n'.join(f'({p},{a}L,{b}L)' for p,a,b in cases)+'\n) }\n')
(R/'results/FIXTURE_SUMMARY.json').write_text(json.dumps(dict(synthetic=True,source_order_pool_calls_per_policy=4418,sampled_fixture_calls=len(pool_records),stress_calls=len(cases)-len(pool_records),total_calls=len(cases),samples=pool_records),indent=2)+'\n')
