"""Portable private-data-free strict aggregate projection regression."""
from copy import deepcopy
import json
import unittest
from .public_summary import sanitize,NAMES,OFFERS,SCALAR

def sample():
    r=dict(status='PASS_SMALL_BANKED_KV_LOAN',m128_executed=False,fullblock_executed=False,rtl_executed=False,ci_executed=False,public21_executed=False,cases=[],comparisons=[])
    for i,name in enumerate(NAMES):
        fault=i>=5;rows=2 if i in (2,3,4) else 1;banked=i not in (0,2)
        cc=dict(leases=1,fill_requests=32*rows,fill_commits=32*rows,read_requests=160 if rows==1 else 512)
        cc.update(consume_acks=cc['fill_requests']+cc['read_requests'],bank_read_accesses=cc['read_requests']*2,bank_write_accesses=cc['fill_requests']*2,response_latency_edges=cc['fill_requests']+cc['read_requests'])
        c=dict(name=name,rows=rows,banked=banked,mode=name if fault else None,
          terminal=dict(status='Protocol' if fault else None,write_bytes=rows*6144),prefix_terminal=dict(status=None),prefix_ack_bytes=rows*2048,prefix_published_bytes=rows*2048,
          output_published=False,injected=fault,fault_debt_held=fault,
          matrix=dict(reset_required=fault,normal_fma_calls=73728 if rows==1 else 221184,counters=dict(owner_acquires=1,owner_releases=1,owner_responses=1,normal_steps=144 if rows==1 else 432,normal_results=144 if rows==1 else 432)),
          scalar_calls=dict(SCALAR[rows]),read_bytes=dict(q=rows*6144,k=rows*1024 if banked else 6144 if rows==1 else 18432,v=rows*1024 if banked else 6144 if rows==1 else 18432),
          external_denials=(39 if fault else 26) if banked else 0,local_hold_edges=1 if name=='M2_BANKED_STALLED' else 0,
          owner=dict(resident_cache=dict(outstanding=0,valid_lines=0,capacity_bytes=704512,kv_reserved_bytes=262144,valid_metadata_bytes=512,counts=cc)),loan=None)
        if banked:
            routefault=name=='bank_port_fault'
            c['loan']=dict(active=False,shared_payload_identity_unchanged=True,same_dense_tile_attention_banks=True,payload_bytearray_allocated=False,production_public_checkpoint_executed=False,rtl_executed=False,model_edges_are_hardware_cycles=False,authority='REAL_SYNTHETIC_KVAPPEND',
              loan_events=dict(edges=100,loans=1,releases=1,route_faults=int(routefault)),bank_events=dict(bank_edges=101+int(routefault),read_accesses=cc['bank_read_accesses'],write_accesses=cc['bank_write_accesses']),blocked_offers={k:3 if fault else 2 for k in OFFERS})
        r['cases'].append(c)
    for i in range(2):
        r['comparisons'].append(dict(case=('M1','M2')[i],output_bit_diff_count=0,intermediate_bit_diff_count=0,observed_fields=10,old_external_read_bytes=(18432,49152)[i],banked_external_read_bytes=(8192,16384)[i],old_kv_read_bytes=(12288,36864)[i],banked_kv_read_bytes=(2048,4096)[i]))
    return r

def paths(x,root=()):
    if type(x) is dict:
        for k,v in x.items():yield from paths(v,root+(k,))
    elif type(x) is list:
        for i,v in enumerate(x):yield from paths(v,root+(i,))
    else:yield root

def put(x,path,value):
    for k in path[:-1]:x=x[k]
    x[path[-1]]=value

class Safe(unittest.TestCase):
    def test_valid_and_private_metadata_ignored(self):
        r=sample();r['source_sha256']='/PRIVATE/PATH';r['cases'][0]['output_sha256']={'secret':'payload'}
        text=json.dumps(sanitize(r),allow_nan=False);self.assertNotIn('/PRIVATE',text);self.assertNotIn('secret',text)
        s=sanitize(r);self.assertEqual(s['released_loans'],9);self.assertEqual(s['rejected_direct_offers'],312)
    def test_every_scalar_string_replacement_cannot_escape(self):
        original=sample()
        for path in paths(original):
            r=deepcopy(original);put(r,path,'/PRIVATE/UNPUBLISHABLE')
            try:text=json.dumps(sanitize(r),allow_nan=False)
            except (ValueError,KeyError,TypeError):continue
            self.assertNotIn('/PRIVATE',text,path)
    def test_numeric_and_bool_malformations(self):
        targets=[('comparisons',0,'old_external_read_bytes'),('cases',1,'external_denials'),('cases',1,'loan','loan_events','edges'),('cases',1,'owner','resident_cache','counts','read_requests'),('cases',1,'scalar_calls','add')]
        for path in targets:
            for value in ('private',{'nested':'private'},[1],float('nan'),float('inf'),True,-1,10**30,1.0):
                r=sample();put(r,path,value)
                with self.assertRaises((ValueError,TypeError)):sanitize(r)
        for path in (('m128_executed',),('cases',1,'loan','active'),('cases',1,'injected')):
            r=sample();put(r,path,0)
            with self.assertRaises(ValueError):sanitize(r)
    def test_missing_selected_extra_count_and_changed_status(self):
        r=sample();r['cases'].pop()
        with self.assertRaises(ValueError):sanitize(r)
        r=sample();r['cases'].reverse()
        with self.assertRaises(ValueError):sanitize(r)
        r=sample();r['cases'][1]['loan']['bank_events']['unexpected']=0
        with self.assertRaises(ValueError):sanitize(r)
        r=sample();r['cases'][5]['terminal']['status']=None
        with self.assertRaises(ValueError):sanitize(r)
    def test_invalid_relations_are_rejected(self):
        for path,value in ((('cases',1,'loan','loan_events','releases'),0),(('cases',1,'loan','bank_events','bank_edges'),1),(('cases',1,'owner','resident_cache','counts','consume_acks'),0),(('cases',4,'local_hold_edges'),0),(('cases',1,'loan','same_dense_tile_attention_banks'),False)):
            r=sample();put(r,path,value)
            with self.assertRaises(ValueError):sanitize(r)
if __name__=='__main__':unittest.main()
