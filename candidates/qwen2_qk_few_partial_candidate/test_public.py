import copy
import json
import unittest
from candidates.qwen2_qk_few_partial_candidate import public_summary as public

def fixture():
    def stage(count):return {'metrics':dict(max_abs=0.0,mean_abs=0.0,count=count,different=0,bit_diff_count=0),'verdict':'PASS'}
    cases=[]
    for case in public.CASES:
      for P in (2,4):
        cases.append(dict(case=case,partials=P,status='COMPLETE_NUMERIC_PASS',failed_stages=[],
          prefix={n:stage(32768 if n in ('kr','k') else 196608) for n in public.STAGES},
          scores=stage(99072),probability=stage(99072),probability_positions=99072,
          projection_fmas=352321536,projection_adds=229376*P,qk_native_fmas=405798912))
    return {'public':dict(status='SIX_CASE_SCREEN_COMPLETE',completed_cases=6,registered_cases=6,cases=cases,
      boundaries=[dict(partials=P,case=n,status='PASS',fmas=393216) for P in (2,4) for n in public.BOUNDARIES],
      gate_policy='UNCHANGED',selection='NO_POSTHOC_GRAPH_OR_SEED_SELECTION',rtl='NOT_EXECUTED',
      fullblock='NOT_EXECUTED',ci='NOT_EXECUTED',hardware_mapping='CONDITIONAL_NOT_IMPLEMENTED')}

class PublicTests(unittest.TestCase):
    def test_valid(self):self.assertEqual(public.sanitize(fixture())['completed_cases'],6)
    def test_all_scalar_strings_rejected(self):
        base=fixture()
        def paths(x,path=()):
            if isinstance(x,dict):
                for k,v in x.items():yield from paths(v,path+(k,))
            elif isinstance(x,list):
                for i,v in enumerate(x):yield from paths(v,path+(i,))
            else:yield path
        for path in paths(base):
            r=copy.deepcopy(base);node=r
            for key in path[:-1]:node=node[key]
            node[path[-1]]='private/path'
            with self.subTest(path=path),self.assertRaises((ValueError,TypeError,KeyError)):public.sanitize(r)
    def test_metric_invalid_values(self):
        for key in ('max_abs','mean_abs','count','different','bit_diff_count'):
            for bad in ('private/path',{'secret':'x'},['private'],None,True,False,float('inf'),float('nan'),-1):
                r=fixture();r['public']['cases'][0]['scores']['metrics'][key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises((ValueError,TypeError)):public.sanitize(r)
    def test_count_and_metric_relations(self):
        for values in ({'different':99073,'bit_diff_count':99073},{'different':2,'bit_diff_count':1},
                       {'max_abs':1,'mean_abs':2,'different':1,'bit_diff_count':1}, {'count':99071},
                       {'count':1<<40}):
            r=fixture();r['public']['cases'][0]['scores']['metrics'].update(values)
            with self.assertRaises(ValueError):public.sanitize(r)
    def test_missing_extra_and_selected_cases(self):
        for cases in (fixture()['public']['cases'][:5],fixture()['public']['cases'][::-1]):
            r=fixture();r['public']['cases']=cases
            with self.assertRaises(ValueError):public.sanitize(r)
        r=fixture();r['public']['cases'][0]['scores']['metrics']['path']='private/path'
        with self.assertRaises(ValueError):public.sanitize(r)
    def test_inconsistent_verdict_and_bool_count(self):
        for name,value in [('status','COMPLETE_NUMERIC_FAIL'),('projection_fmas',True),('partials',True),('failed_stages',['scores'])]:
            r=fixture();r['public']['cases'][0][name]=value
            with self.assertRaises(ValueError):public.sanitize(r)
        r=fixture();r['public']['cases'][0]['scores']['verdict']=True
        with self.assertRaises(ValueError):public.sanitize(r)
    def test_unselected_private_material_omitted(self):
        r=fixture();r['private']={'path':'private/path'};r['public']['pilot']={'secret':'private/path'}
        self.assertNotIn('private',json.dumps(public.sanitize(r)))
    def test_cold_default(self):self.assertEqual(public.run(),{'status':'NOT_EXECUTED'})
if __name__=='__main__':unittest.main()
