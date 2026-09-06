import importlib.util
from pathlib import Path
import random
import pytest
p=Path(__file__).resolve().parents[1]/'scripts/memory_plan.py'
s=importlib.util.spec_from_file_location('memory_plan',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
W=[{'name':'test_fixture_not_real_weights','bytes':1024**3,'sha256':'b'*64}]
@pytest.mark.parametrize('name',m.PROFILES)
def test_no_alias_and_regions(name):
 r=m.plan(name,W,2**40)
 for x in r['allocations']:
  assert x['base']%4096==0
  region=next(z for z in r['regions'] if z['name']==x['region'])
  assert region['base']<=x['base']<x['limit']<=region['limit']
 for a,b in zip(r['allocations'],r['allocations'][1:]):assert a['limit']+a['guard_bytes']<=b['base']
 assert len(r['regions'])==4
 assert r['local_tile_partition']['c'][1]<=r['local_sram_bytes']
@pytest.mark.parametrize('key,kv,gdn',[('qwen2',28,0),('qwen35',20,60),('qwen38',24,108)])
def test_state_budgets(key,kv,gdn):
 b=m.budgets(key)['persistent'];assert b['kv_all_layers']==kv*1024**2
 assert b.get('gdn_all_layers_fp32',0)==gdn*1024**2
@pytest.mark.parametrize('weights,limit',[([],2**40),(W,2**32),([dict(W[0],bytes=-1)],2**40),([dict(W[0],sha256='x')],2**40),(W,2**57),(W,2**32+1024),(W*2,2**40)])
def test_reject(weights,limit):
 with pytest.raises(ValueError):m.plan('qwen2',weights,limit)
def test_random_allocations():
 rng=random.Random(60906)
 for _ in range(500):
  w=[dict(W[0],bytes=rng.randrange(1,2**36))]
  for key in m.PROFILES:
   r=m.plan(key,w,2**44)
   for a,b in zip(r['allocations'],r['allocations'][1:]):assert a['limit']<b['base']
