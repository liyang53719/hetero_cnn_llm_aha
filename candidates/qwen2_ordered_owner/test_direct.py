"""Original physical/direct driver reaches the new owner work state itself.

Host/Dense/Matrix endpoint remain explicitly synthetic controls, not fullblock
or native numerical evidence. Ordered lane calculations are exact reference.
"""
import argparse
import ast
import hashlib
import json
from dataclasses import asdict
import importlib.util
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace
import unittest

HERE=Path(__file__).resolve(strict=True).parent
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--source-root',required=True,type=Path)
parser.add_argument('--schedule-root',type=Path)
parser.add_argument('--direct-root',type=Path)
args,rest=parser.parse_known_args()
root=args.source_root.resolve(strict=True)
direct_root=args.direct_root or root/'candidates/qwen2_selected_direct_transport'

pins=json.loads((HERE/'SOURCE_PINS.json').read_text())
rel='candidates/qwen2_selected_direct_transport/direct_test_support.py'
if hashlib.sha256((direct_root/'direct_test_support.py').read_bytes()).hexdigest()!=pins['harness_and_composer_pins'][rel]:
    raise ValueError('direct fixture drift')

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
sys.argv[:]=[sys.argv[0],'--source-root',str(root),*rest]
s=module('_ordered_direct_fixture',direct_root/'direct_test_support.py')
sys.argv[:]=[sys.argv[0],'--source-root',str(root),*(['--schedule-root',str(args.schedule_root)] if args.schedule_root else []),*rest]
o=module('_ordered_direct_owner',HERE/'test_owner.py')
s.prior=o.prior
s.modules=SimpleNamespace(prefix=o.base.prefix,official=o.official,entry=o.entry,
                          routing=o.base.routing,selected=o.selected)
s.runtime=s.load_runtime()
new_direct=o.prior.definitions('production_qk16_model/direct_transport.py',
    source=(HERE/'postimage/production_qk16_model/direct_transport.py').read_text(),
    environment={'asdict':asdict,'install_schedule':o.entry.install,
                 'Qk16LegacyPvClient':o.base.routing.Qk16LegacyPvClient,
                 'execute_attention_owner':s.runtime.driver.execute_attention_owner})
sys.modules['candidates.qwen2_resident_matrix.production_qk16_model.direct_transport']=new_direct


def case():
    service=o.prior.RoutedScriptedService(acquired=False);service.words={}
    scalar=o.prior.ScalarControlAdapter()
    owner=o.official.OfficialAttentionOwner(service,scalar,max_tokens=128)
    job=o.base.prefix.Job('Attention',0x12340001,0x10000,0x20000,0x40000,2,1536,128,2*1536*4,c=0x30000)
    fixture=s.synthetic_fixture(job)
    readonly={name:(lambda offset:struct.pack('<16I',*([0x3f800000]*16))) for name in ('q','k','v')}
    physical=s.runtime.physical.PhysicalMemory(fixture,readonly)
    memory=physical.metadata_port()
    frontend=SimpleNamespace(memory=memory,port=SimpleNamespace(memory=memory),config=fixture.config,
                             launch=lambda host:host.state=='request')
    host,dense,trace=s.SyntheticHostControl(job),s.SyntheticIdleDense(),s.SyntheticTrace()
    prefix=o.base.prefix.PrefixOwner(scalar,max_tokens=128)
    x=s.runtime.public.PublicExecution(frontend,dense,trace,time.monotonic()+15,
        host=host,prefix_owner=prefix,attention_owner=owner,matrix_service=service)
    probe=s.TrafficProbe(owner,physical)
    return SimpleNamespace(owner=owner,job=job,physical=physical,service=service,scalar=scalar,
        host=host,dense=dense,prefix=prefix,x=x,probe=probe)


class DirectOwner(unittest.TestCase):
    def test_original_driver_handles_work_via_actual_owner_ticks(self):
        c=case();lanes=o.numeric.strict_lanes()
        result=new_direct.run(c.x,c.physical,c.job,ordered_fold=True,ordered_lanes=lanes,final_ack_stall=5)
        self.assertEqual(c.probe.accepted_jobs,[c.job])
        self.assertEqual(c.owner.ordered_adapter.events,dict(scan=384,add_stripe=384,scale=24,retire=36))
        self.assertEqual(lanes.calls,dict(add=576,mul=36,bf=72))
        self.assertEqual(len(c.probe.external_reads),768)
        self.assertEqual([kind for kind,_,_ in c.probe.write_events],['command','data','ack']*192)
        self.assertEqual([(q.write,q.address) for q in c.probe.core_requests],s.expected_requests(c.job))
        self.assertEqual((c.service.counts['owner_acquires'],c.service.counts['owner_releases']),(1,1))
        self.assertIsNone(c.x.attention_transport);self.assertIsNone(c.x.attention_transport_binding)
        self.assertEqual(c.probe.scratch_events,0)
        self.assertEqual(result['backend']['matrix_normal_fma_calls'],0) # endpoint is NOT native
        self.assertEqual(c.dense.clock,c.owner.clock)
        self.assertEqual(c.host.ticks,c.owner.clock)

    def test_published_direct_binding_guards_remain_exact(self):
        original=ast.parse((direct_root/'direct_transport.py').read_text())
        patched=ast.parse((HERE/'postimage/production_qk16_model/direct_transport.py').read_text())
        for name in ('require','dense_retired','no_scratch','DirectBinding'):
            a=next(n for n in original.body if getattr(n,'name',None)==name)
            b=next(n for n in patched.body if getattr(n,'name',None)==name)
            self.assertEqual(ast.dump(a,include_attributes=False),ast.dump(b,include_attributes=False))

    def test_default_direct_mode_does_not_allocate_work_adapter(self):
        c=case();new_direct.run(c.x,c.physical,c.job)
        self.assertIsNone(c.owner.ordered_adapter)
        self.assertEqual(len(c.probe.external_reads),768)

    def test_bad_opt_in_rejected_before_binding_or_job_accept(self):
        c=case()
        with self.assertRaises(ValueError):new_direct.bind(c.x,c.physical,c.job,ordered_fold=True)
        self.assertIsNone(getattr(c.x,'selected_direct_binding',None))
        self.assertIsNone(c.owner.packed_schedule)
        self.assertEqual(c.probe.accepted_jobs,[])
        self.assertEqual(c.service.counts['owner_acquires'],0)

if __name__=='__main__':unittest.main()
