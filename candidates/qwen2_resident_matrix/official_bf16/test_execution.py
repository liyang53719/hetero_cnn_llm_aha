"""Small public-policy/observation guards; no full checkpoint execution."""
from array import array
import ctypes as C
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from . import execution as p
from . import dense_silu
from ..ffn_public.fixture import make_qwen2_21_fixture
from ..ffn_public import model as public
from ..ffn_public import prefix_execution as prefix
from ..ffn_public.prefix_arithmetic import ScalarService
from ..ffn_public.execute_numeric import numeric
from ..ffn_public.prefix_owners import Job
from .test_owners import verified_library


def expected_job(f, pc):
    kind,a,b,d = p.JOBS[pc]
    s=f.specs; rows=s['x'][1][0]
    c=(s['rope'][0]+1024*64*4 if kind=='Rope' else s['cache_v'][0] if kind=='Attention' else 0)
    return Job(kind,(f.config.epoch<<16)|pc,s[a][0],s[b][0],s[d][0],rows,
               256 if pc==9 else s[d][1][-1],128 if pc==12 else s[a][1][-1],
               f.allocations[d].storage_bytes,c=c,weight_bf16=kind=='Dense')


class PolicyExecutionTests(unittest.TestCase):
    def test_role_binding_covers_all_actual_jobs_and_rejects_changed_identity(self):
        for rows in (16,128):
            f=make_qwen2_21_fixture(rows)
            for pc in p.JOBS:
                job=expected_job(f,pc)
                self.assertEqual(p.validate_job(f,job),pc)
                for bad in (replace(job,a=job.a+64), replace(job,b=job.b+64),
                            replace(job,dst=job.dst+64), replace(job,tag=job.tag+(1<<16)),
                            replace(job,m=job.m+16),replace(job,write_bytes=job.write_bytes+64),
                            replace(job,activation_bf16=True),replace(job,output_bf16=True),
                            replace(job,c=job.c+64)):
                    with self.assertRaises(ValueError): p.validate_job(f,bad)

    def test_public_norm_uses_actual_command_and_ack_then_publication(self):
        import time
        f=make_qwen2_21_fixture(16)
        def ones(offset): return bytes.fromhex('0000803f')*16
        providers={name:ones for name,a in f.allocations.items() if a.readonly}
        physical=prefix.PhysicalMemory(f,providers)
        r=f.config.regions[3]
        owner=numeric.model.FfnDrainOwnerModel(numeric.model.PrefixWorkspace(r.base,r.limit-r.base,
            f.config.epoch+1,2560),enable_ffn_window=True,enable_ffn_tiles=True,enable_ffn_drain=True)
        lib=verified_library(); self.assertEqual(lib.td_reset(),0)
        service=dense_silu.OfficialMatrixService(lib); scalar=ScalarService()
        x=p.OfficialPublicExecution(public.PublicFrontend(physical.metadata_port(),f.config),
            owner,numeric.CappedTrace(),time.monotonic()+20,fixture=f,
            host=public.group.HostControl(enabled=True,legacy_prefix=True,legacy_attention=True),
            prefix_owner=p.OfficialPrefixOwner(scalar),
            attention_owner=p.OfficialAttentionOwner(service,scalar),matrix_service=service)
        job=x.advance_to_request()['ordinary_request']
        self.assertEqual(asdict(job),asdict(expected_job(f,0)))
        result=prefix.execute_prefix_owner(x,physical,job)
        self.assertIsNone(result['result']['status'])
        self.assertEqual(x.host.completed,0)
        self.assertFalse(physical.regions['n0']['published'])
        x.publish_completions((0,))
        physical.publish(job,x.host)
        self.assertEqual(x.host.completed,1)
        self.assertEqual(physical.raw(job.dst,job.write_bytes),bytes.fromhex('0000803f')*(16*1536))
        next_job=x.advance_to_request()['ordinary_request']
        self.assertEqual(next_job.tag&0xffff,1)
        self.assertEqual(service.bindings[next_job.tag].role,'q_raw')
        self.assertFalse(service.bindings[next_job.tag].materializes(0,1536))
        self.assertIsNone(x.launch_result)

    def test_reference_gate_blocks_all_candidate_payload_forms_until_terminal(self):
        gate=p.WholeReferenceGate({'comparison_only':{}})
        for name in ('work/new/raw_stages/x.f32le','work/new/references/official/y.f32le',
                     'work/new/tensors/x.f32le','work/new/candidate_scores.f32le'):
            with self.assertRaises(ValueError): gate.audit('open',(name,'r',0))
        for name in ('candidate','software_recipe','prefix_recipe'):
            with self.assertRaises(ValueError): gate.audit('subprocess.Popen',(name,[name],None,None))
        wrapped=gate.library(NS(sf_reference_bf16_v1=1))
        with self.assertRaises(ValueError): wrapped.sf_reference_bf16_v1
        gate.audit('open',('work/new/actual_n0.f32le','w',0))
        gate.opened=True
        gate.audit('open',('work/new/references/x.f32le','r',0))
        self.assertEqual(wrapped.sf_reference_bf16_v1,1)

    def test_silu_observations_require_complete_actual_product_identity(self):
        class Library:
            def sf_vector(self,g,u,out,phase,flags,errors):
                for lane in range(16):
                    phase[64+lane]=g[lane];out[lane]=u[lane]
                return 0
        observer=p.ObservedSiluLibrary(Library(),16)
        g,u,out=(C.c_uint32*16)(*range(16)),(C.c_uint32*16)(*range(16,32)),(C.c_uint32*16)()
        phases,flags,errors=(C.c_uint32*96)(),(C.c_uint32*96)(),(C.c_uint32*16)()
        observer.sf_vector(g,u,out,phases,flags,errors)
        with self.assertRaises(ValueError): observer.seal(observer.product.tobytes())
        for _ in range(56*160-1): observer.sf_vector(g,u,out,phases,flags,errors)
        self.assertEqual(observer.seal(observer.product.tobytes()),observer.silu.tobytes())
        bad=array('I',observer.product);bad[0]^=1
        with self.assertRaises(ValueError): observer.seal(bad.tobytes())
        with self.assertRaises(ValueError): observer.sf_vector(g,u,out,phases,flags,errors)


if __name__=='__main__': unittest.main()
