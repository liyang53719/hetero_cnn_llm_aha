"""Strict schema negative tests; stored numerical work is optional and read-only."""
from copy import deepcopy
import unittest
from .public_summary import PLAN,project

def fixture():
    r=dict(scope='DIAGNOSTIC_SOFTWARE_OWNER',hardware_mapping='NOT_IMPLEMENTED',performance='NO_GO',
      public21='NOT_EXECUTED',profiled_dense_binding='NOT_EXECUTED',reservation_service='ORIGINAL_BASE_MATRIX_SERVICE',cases=[])
    for name,fma,adds,ack,success,drain,quarantine in PLAN:
        r['cases'].append(dict(name=name,terminal=dict(status=None if success else 'Protocol',useful_macs=fma,executed_macs=fma,write_bytes=ack),
          owner=dict(kernel_delta=dict(fmas=fma,adds=adds),write_bytes=ack),bit_diff_count=0 if success else None,
          matrix=dict(dense_fma_calls=0,normal_fma_calls=0),fault_injected=not success,drain_observed=drain,
          physical_pending_retained=quarantine,matrix_lease_retained=quarantine,a_lease_retained=quarantine,
          final_ack_hold_ticks=5 if success else 0,last_successful_ack_tick=10,terminal_tick=11))
    return r
class Safe(unittest.TestCase):
    def test_fixed_aggregate(self):
        r=project(fixture());self.assertEqual(r['case_count'],8);self.assertEqual(r['bit_diff_count'],0)
        self.assertEqual(sum(c['actual_fma_count'] for c in r['cases']),r['actual_fma_count'])
        self.assertEqual(sum(c['actual_add_count'] for c in r['cases']),r['actual_add_count'])
    def test_all_consumed_scalars_reject_injection(self):
        source=fixture()
        def paths(x,p=()):
            if isinstance(x,dict):
                for k,v in x.items():yield from paths(v,p+(k,))
            elif isinstance(x,list):
                for i,v in enumerate(x):yield from paths(v,p+(i,))
            else:yield p
        for path in paths(source):
            # Failed-case timing is deliberately not projected/validated.
            if len(path)>2 and path[1]>=3 and path[-1] in ('last_successful_ack_tick','terminal_tick'):continue
            for attack in ('private/path',{},[],float('nan'),float('inf'),-1,True):
                value=deepcopy(source);at=value
                for k in path[:-1]:at=at[k]
                old=at[path[-1]];at[path[-1]]=attack
                if type(old) is type(attack) and old==attack:continue
                with self.assertRaises(ValueError,msg=str(path)):project(value)
    def test_all_cases_required(self):
        r=fixture();r['cases'].pop()
        with self.assertRaises(ValueError):project(r)
    def test_private_extra_not_projected(self):
        r=fixture();r['private']='private/path';self.assertNotIn('private',project(r))
if __name__=='__main__':unittest.main()
