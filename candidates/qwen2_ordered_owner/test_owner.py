"""Actual owner.tick + actual clients; bounded pure-Python Matrix endpoint only.

No generator-yield swallowing: the owner hooks execute every work transition.
No native/RTL/fullblock claim. Matrix endpoint is existing scripted protocol.
"""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import struct
import unittest

HERE=Path(__file__).resolve(strict=True).parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root',required=True,type=Path)
parser.add_argument('--schedule-root',type=Path)
args,rest=parser.parse_known_args()
root=args.source_root.resolve(strict=True)
schedule_root=args.schedule_root or root/'candidates/qwen2_ordered_schedule'
pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
for rel,pin in pins['inputs'].items():
    if hashlib.sha256((HERE/'postimage'/rel).read_bytes()).hexdigest()!=pin['after_sha256']:
        raise ValueError('candidate postimage drift: '+rel)
for rel,pin in pins['raw_sources'].items():
    data=(root/rel).read_bytes()
    if len(data)!=pin['bytes'] or hashlib.sha256(data).hexdigest()!=pin['sha256']:
        raise ValueError('raw source drift: '+rel)
for rel,sha in pins['harness_and_composer_pins'].items():
    if 'selected_direct_transport' in rel:continue
    path=schedule_root/Path(rel).name if 'qwen2_ordered_schedule/' in rel else root/rel
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('harness drift: '+rel)
for name,key in [('schedule.py','ordered_schedule_sha256'),('ordered_work.py','ordered_work_sha256')]:
    if hashlib.sha256((schedule_root/name).read_bytes()).hexdigest()!=pins[key]:raise ValueError('frozen work drift')

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

sys.argv[:]=[sys.argv[0],'--source-root',str(root),*rest]
prior=module('_ordered_owner_prior',root/'candidates/qwen2_selected_scala_model/routing_test_support.py')
base=prior.load_owner_modules()
sys.argv[:]=[sys.argv[0],'--source-root',str(root),*rest]
numeric=module('_ordered_owner_numeric',schedule_root/'test_numeric.py')
w=numeric.w
# In-memory AST definitions retain their exact method bodies. The package
# aliases support original local imports, without executing native preludes.
selected=prior.definitions('production_qk16_model/schedule.py',source=(schedule_root/'schedule.py').read_text(),environment={**vars(base.packed_schedule),**vars(prior.client),**vars(base.prefix),**vars(base.recipe),**vars(w)})
ordered=prior.definitions('production_qk16_model/ordered_owner.py',source=(HERE/'ordered_owner.py').read_text(),environment={**vars(w),'PrefixFault':base.prefix.PrefixFault})
hooks=prior.definitions('attention_packed_owner/hooks.py',source=(HERE/'postimage/attention_packed_owner/hooks.py').read_text(),environment={**vars(prior.protocol),**vars(base.packed_schedule),**vars(selected),**vars(base.routing),**vars(prior.client),**vars(base.prefix),'ordered_owner':ordered})
attention=prior.definitions('ffn_attention/attention_owner.py',source=(HERE/'postimage/ffn_attention/attention_owner.py').read_text(),environment={**vars(prior.arithmetic),**vars(base.prefix),**vars(prior.matrix),**vars(base.recipe),'packed':hooks})
official=prior.definitions('official_bf16/owners.py',('OfficialAttentionOwner',),source=prior.patched_owner_source('official_bf16/owners.py'),environment={**vars(prior.arithmetic),**vars(base.prefix),**vars(attention),**vars(base.recipe)})
entry=prior.definitions('production_qk16_model/entry.py',source=(HERE/'postimage/production_qk16_model/entry.py').read_text(),environment={**vars(selected),**vars(w),'hooks':hooks})


def make(m=1,*,enabled=True,words=None):
    service=prior.RoutedScriptedService(acquired=False)
    service.words={} if words is None else words
    scalar=prior.ScalarControlAdapter()
    owner=official.OfficialAttentionOwner(service,scalar,max_tokens=128)
    lanes=numeric.strict_lanes() if enabled else None
    entry.install(owner,ordered_fold=enabled,ordered_lanes=lanes)
    job=base.prefix.Job('Attention',0x12340001,0x10000,0x20000,0x40000,m,1536,128,m*1536*4,c=0x30000)
    return owner,service,scalar,job


class Driver:
    def __init__(self,owner,job):
        self.owner,self.job=owner,job;self.pending=None;self.writes=[];self.edges=[]
        if not owner.tick(job=job)['job_fire']:raise AssertionError('owner not admitted')
    def step(self,**overrides):
        inputs=dict(memory_ready=True,memory_response=self.pending,response_ready=False)
        inputs.update(overrides)
        p=self.owner.tick(**inputs);self.edges.append(p)
        if p['memory_response_fire']:self.pending=None
        if p['memory_fire']:
            if self.pending is not None:raise AssertionError('overlapping memory debt')
            q=p['memory']
            if q.write:self.writes.append(q.data)
            self.pending=base.prefix.MemoryResponse(q.tag,None if q.write else (0,)*16)
        return p
    def until(self,predicate,limit=12000):
        for _ in range(limit):
            if predicate():return
            self.step()
        raise AssertionError('owner budget exhausted '+self.owner.state+' '+str(self.owner.detail))
    def ordered(self,phase=None,key=None):
        self.until(lambda:self.owner.state=='ordered_fold' and
                   (phase is None or self.owner.ordered_work.state==phase) and
                   (key is None or self.owner.ordered_work.key==key))


class OwnerHooks(unittest.TestCase):
    def test_actual_owner_progresses_work_then_original_ack_and_terminal(self):
        for m in (1,2):
            owner,service,scalar,job=make(m)
            d=Driver(owner,job);d.ordered();work=owner.ordered_work;held=service.result
            calls=scalar.calls.copy();steps=owner.ordered_adapter.events.copy()
            for _ in range(10):
                d.step();self.assertIs(service.result,held);self.assertEqual(scalar.calls,calls)
            self.assertGreater(owner.ordered_adapter.events['scan'],steps['scan'])
            d.until(lambda:owner.state=='finish')
            self.assertIsNone(owner.status);self.assertEqual(len(d.writes),m*96)
            count=12*m*(m+1)//2
            self.assertEqual(owner.ordered_adapter.lanes.calls,dict(add=16*count,mul=count,bf=2*count))
            self.assertEqual(service.counts['owner_acquires'],1)
            self.assertEqual(service.counts['owner_releases'],0)
            p=d.step(response_ready=True);self.assertTrue(p['response_fire'])
            self.assertEqual(service.counts['owner_releases'],1);self.assertIsNone(scalar.client)
            self.assertIsNone(service.owner)

    def test_default_path_outputs_and_shared_identity_unchanged(self):
        runs=[]
        for enabled in (False,True):
            owner,service,scalar,job=make(enabled=enabled);ids=(id(service),service.resource_address,id(scalar))
            d=Driver(owner,job);d.until(lambda:owner.state=='finish');runs.append((d.writes,scalar.calls.copy()))
            self.assertEqual(ids,(id(owner.matrix),owner.matrix.resource_address,id(owner.scalar)))
            self.assertEqual(owner.ordered_adapter is None,not enabled)
        self.assertEqual(runs[0][0],runs[1][0])
        self.assertEqual(runs[0][1]['add']-runs[1][1]['add'],192)
        self.assertEqual(runs[0][1]['mul']-runs[1][1]['mul'],12)

    def test_no_scan_on_same_edge_as_final_result_delivery(self):
        owner,service,scalar,job=make();d=Driver(owner,job);d.ordered()
        self.assertEqual(owner.ordered_adapter.events['scan'],0)
        self.assertEqual(owner.ordered_work.row,0)
        self.assertTrue(d.edges[-1]['matrix_result_fire'])

    def test_early_matching_done_at_every_phase_never_commits_score(self):
        for phase in ('scan','fold','scale','retire','reply'):
            owner,service,scalar,job=make();d=Driver(owner,job);d.ordered(phase)
            work=owner.ordered_work;before=tuple(owner.program.gi_frame.f_locals.get('scores',()))
            tag=owner.matrix_client.packed.tag
            service._done=prior.matrix.MatrixDone(tag.group,False,tag.ticket,tag.epoch)
            d.step(service_result_ready=False,service_done_ready=False)
            self.assertTrue(owner.poison);self.assertEqual(owner.state,'drain')
            self.assertEqual(work.state,'cancelled');self.assertIsNotNone(service.result)
            self.assertEqual(before,())
            self.assertEqual(service.counts['packed_cancel_acks'],0)
            d.until(lambda:owner.state=='finish')
            self.assertEqual(owner.status,'Protocol');self.assertEqual(d.writes,[])

    def test_foreign_done_cannot_clear_current_group_debt(self):
        owner,service,scalar,job=make();d=Driver(owner,job);d.ordered('retire')
        tag=owner.matrix_client.packed.tag
        foreign=prior.matrix.MatrixDone(tag.group+1,False,tag.ticket,tag.epoch)
        service._done=foreign
        for _ in range(5):d.step()
        self.assertTrue(owner.poison);self.assertEqual(owner.state,'drain')
        self.assertIs(service.done,foreign);self.assertIsNotNone(service.group)
        self.assertEqual(service.counts['normal_done'],0);self.assertEqual(service.counts['owner_releases'],0)

    def test_override_without_real_done_is_not_an_early_valid(self):
        owner,service,scalar,job=make();d=Driver(owner,job);d.ordered()
        tag=owner.matrix_client.packed.tag
        override=prior.matrix.MatrixDone(tag.group,False,tag.ticket,tag.epoch)
        self.assertIsNone(service.done)
        d.step(done_override=override)
        self.assertFalse(owner.poison);self.assertEqual(owner.ordered_work.row,1)

    def test_reset_each_phase_waits_real_result_done_drain(self):
        for phase in ('scan','fold','scale','retire','reply'):
            owner,service,scalar,job=make();d=Driver(owner,job);d.ordered(phase)
            held=service.result
            d.step(local_reset=True,service_result_ready=False,service_done_ready=False)
            self.assertTrue(owner.poison);self.assertIs(service.result,held)
            self.assertIsNone(owner.ordered_work);self.assertEqual(owner.state,'drain')
            d.until(lambda:owner.state=='finish');self.assertEqual(owner.status,'Protocol')
            self.assertEqual(d.writes,[])

    def test_error_retirement_does_not_resume_softmax(self):
        owner,service,scalar,job=make();d=Driver(owner,job)
        d.until(lambda:owner.matrix_client is not None and owner.matrix_client.packed.state=='wait_done')
        done=service.done;service._done=prior.matrix.MatrixDone(done.tag,True,done.ticket,done.epoch)
        calls=scalar.calls.copy()
        d.until(lambda:owner.state=='finish')
        self.assertEqual(owner.status,'Protocol');self.assertEqual(scalar.calls,calls)
        self.assertEqual(d.writes,[])

    def test_later_key_numerical_fault_preserves_prefix_without_group_ack(self):
        owner,service,scalar,job=make(2,words={16:0x7fc00000})
        d=Driver(owner,job)
        d.until(lambda:owner.state=='ordered_fold' and owner.ordered_work.count==2 and
                owner.ordered_work.key==1 and owner.ordered_work.state=='retire')
        work=owner.ordered_work
        self.assertEqual(work.faults[:2],[False,True])
        program=owner.program
        while 'scores' not in program.gi_frame.f_locals:program=program.gi_yieldfrom
        self.assertEqual(len(program.gi_frame.f_locals['scores']),1)
        retired_before=service.counts['normal_results'];calls=scalar.calls.copy()
        d.step();d.step(service_result_ready=False,service_done_ready=False)
        self.assertEqual(owner.status,'Numerical');self.assertTrue(owner.poison)
        self.assertEqual(service.counts['normal_results'],retired_before)
        self.assertEqual(scalar.calls,calls)
        self.assertEqual(len(d.writes),96) # only completed token0 output
        d.until(lambda:owner.state=='finish');self.assertEqual(owner.status,'Numerical')

    def test_bad_matrix_result_rejected_before_work_creation(self):
        owner,service,scalar,job=make();d=Driver(owner,job)
        d.until(lambda:service.result is not None)
        service.result=replace(service.result,error=True)
        d.until(lambda:owner.state=='finish')
        self.assertEqual(owner.status,'Protocol')
        self.assertEqual(owner.ordered_adapter.events['scan'],0)
        self.assertEqual(d.writes,[])

    def test_early_done_retains_accepted_memory_until_matching_response(self):
        owner,service,scalar,job=make();d=Driver(owner,job)
        d.until(lambda:owner.matrix_client is not None and owner.matrix_client.packed.active and owner.memory_pending)
        pending=d.pending;tag=owner.matrix_client.packed.tag
        service._done=prior.matrix.MatrixDone(tag.group,False,tag.ticket,tag.epoch)
        p=d.step(memory_response=None,service_done_ready=False)
        self.assertFalse(p['memory_fire']);self.assertTrue(owner.memory_pending)
        self.assertEqual(owner.request.tag,pending.tag)
        bad=base.prefix.MemoryResponse(pending.tag+1,(0,)*16)
        p=d.step(memory_response=bad)
        self.assertFalse(p['memory_response_fire']);self.assertTrue(owner.memory_pending)
        self.assertEqual(owner.state,'drain');self.assertEqual(service.counts['owner_releases'],0)
        d.until(lambda:owner.state=='finish')
        self.assertFalse(owner.memory_pending);self.assertEqual(owner.status,'Protocol')

    def test_early_done_masks_old_unaccepted_memory_offer(self):
        owner,service,scalar,job=make();d=Driver(owner,job)
        d.until(lambda:owner.matrix_client is not None and owner.matrix_client.packed.active and owner.state=='issue')
        tag=owner.matrix_client.packed.tag
        service._done=prior.matrix.MatrixDone(tag.group,False,tag.ticket,tag.epoch)
        p=d.step()
        self.assertFalse(p['memory_fire']);self.assertIsNone(p['memory'])
        self.assertTrue(owner.poison)

    def test_early_done_after_final_score_before_ack_is_not_success(self):
        owner,service,scalar,job=make();d=Driver(owner,job)
        d.until(lambda:owner.state=='matrix_issue' and type(owner.matrix_request) is prior.client.PackedConsumerAck)
        tag=owner.matrix_client.packed.tag
        self.assertEqual(owner.ordered_adapter.events['retire'],1)
        service._done=prior.matrix.MatrixDone(tag.group,False,tag.ticket,tag.epoch)
        p=d.step(service_result_ready=False,service_done_ready=False)
        self.assertFalse(p['matrix_request_fire']);self.assertTrue(owner.poison)
        self.assertEqual(owner.status,'Protocol');self.assertIsNotNone(service.result)
        d.until(lambda:owner.state=='finish');self.assertEqual(d.writes,[])

    def test_pv_error_and_nonfinite_keep_original_numerical_priority(self):
        for enabled in (False,True):
            owner,service,scalar,job=make(enabled=enabled);d=Driver(owner,job)
            d.until(lambda:owner.matrix_client is not None and
                    owner.matrix_client.active is owner.matrix_client.legacy and service.result is not None)
            raw=bytearray(16384);struct.pack_into('<I',raw,0,0x7fc00000)
            service.result=replace(service.result,value=prior.matrix.MatrixValue(raw),error=True)
            d.until(lambda:owner.state=='finish')
            self.assertEqual(owner.status,'Numerical')
            self.assertEqual(d.writes,[])

    def test_opt_in_requires_strict_backend_before_mutation(self):
        service=prior.RoutedScriptedService(acquired=False);scalar=prior.ScalarControlAdapter()
        owner=official.OfficialAttentionOwner(service,scalar,max_tokens=128)
        with self.assertRaises(ValueError):entry.install(owner,ordered_fold=True)
        self.assertIsNone(owner.packed_schedule);self.assertIsNone(service.owner)
        with self.assertRaises(ValueError):entry.install(owner,ordered_lanes=numeric.strict_lanes())
        self.assertIsNone(owner.packed_schedule)

if __name__=='__main__':unittest.main()
